import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database.session import get_db
from app.repositories.repositories import app_setting_repo
from app.schemas.schemas import (
    RCARequest,
    RCAStructuredResponse,
    LogAnalysisResponse,
    DiagnoseCodebaseResponse,
    CodebaseCandidateFile,
    AskAiRequest,
    AskAiResponse,
    CodeFixSuggestion,
    GitlabFixDefaultsResponse,
    GitlabFixPushRequest,
    GitlabFixPushResponse,
)
from app.services.rca.rca_agent import rca_agent, LogNotFoundError
from app.services.rca.codebase_diagnostics import parse_stack_trace_frames, search_codebase_for_candidates
from app.services.rca.code_fix import build_file_context, parse_fix_response, build_fix
from app.services.rca.ai_providers import get_ai_suggestion, AiProviderError
from app.services.gitlab.fix_publisher import get_publish_defaults, publish_fix, FixPublishError
from app.api.endpoints.settings import TARGET_CODEBASE_PATH_KEY
from app.models.models import Log

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILES_SENT_TO_AI = 3


def _get_configured_codebase_path(db: Session) -> str:
    path = app_setting_repo.get(db, TARGET_CODEBASE_PATH_KEY)
    if not path:
        raise HTTPException(
            status_code=400,
            detail="Target codebase path is not configured. Set it on the Settings page first."
        )
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail=f"Configured target codebase path is unreachable: {path}"
        )
    return path


def _diagnose(db: Session, log_id: int) -> DiagnoseCodebaseResponse:
    analysis = rca_agent.get_analysis(db, log_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"No RCA analysis found for log_id={log_id}")

    target_path = _get_configured_codebase_path(db)
    log = analysis.log

    frames = parse_stack_trace_frames(log.stacktrace, log.message)
    keywords = (
        [analysis.root_cause_category]
        + [s.service_name for s in analysis.services]
        + [d.dependency for d in analysis.dependencies]
    )
    candidates, truncated = search_codebase_for_candidates(target_path, frames, keywords)

    return DiagnoseCodebaseResponse(
        log_id=log_id,
        target_path=target_path,
        stack_frames_parsed=[f"{f['file']}:{f['line']}" for f in frames],
        candidates=[CodebaseCandidateFile(**c) for c in candidates],
        truncated=truncated
    )


@router.post("/analyze/{log_id}", response_model=LogAnalysisResponse)
def trigger_analysis(
    log_id: int,
    request: Optional[RCARequest] = None,
    db: Session = Depends(get_db),
):
    """
    Trigger a Root Cause Analysis for a specific log entry.

    The agent will:
    1. Fetch surrounding logs (50 before, 20 after) for context
    2. Build a rich prompt with service metadata
    3. Call whichever AI provider is currently configured (Claude/Gemini/Ollama)
    4. Persist results to the database
    5. Return the analysis result

    Pass request.force_new=true to regenerate a fresh analysis even if one
    already exists (e.g. after switching AI provider), instead of getting
    back the same cached known-issue solution.
    """
    try:
        result = rca_agent.analyze(db, log_id, metadata=request, force_new=bool(request and request.force_new))
        analysis = result["analysis"]
        rca_detail = result["rca_detail"]

        # Build the response manually to include rca_detail
        return LogAnalysisResponse(
            id=analysis.id,
            log_id=analysis.log_id,
            root_cause=analysis.root_cause,
            root_cause_category=analysis.root_cause_category,
            severity=analysis.severity,
            business_impact=analysis.business_impact,
            technical_impact=analysis.technical_impact,
            confidence_score=analysis.confidence_score,
            recommendation=analysis.recommendation,
            summary=analysis.summary,
            created_at=analysis.created_at,
            patterns=[{"id": p.id, "pattern": p.pattern} for p in analysis.patterns],
            dependencies=[{"id": d.id, "dependency": d.dependency} for d in analysis.dependencies],
            services=[{"id": s.id, "service_name": s.service_name} for s in analysis.services],
            rca_detail=rca_detail,
            incident_group_id=analysis.incident_group_id,
            is_recurring=analysis.is_recurring,
            match_score=analysis.match_score,
            ai_provider=analysis.ai_provider,
            ai_model=analysis.ai_model,
        )
    except LogNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AiProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RCA analysis failed: {str(e)}"
        )


@router.get("/analysis/{log_id}", response_model=LogAnalysisResponse)
def get_analysis(
    log_id: int,
    db: Session = Depends(get_db),
):
    """
    Fetch the most recent Root Cause Analysis for a specific log entry.
    """
    analysis = rca_agent.get_analysis(db, log_id)
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for log_id={log_id}"
        )
    return analysis


@router.get("/analyses", response_model=List[LogAnalysisResponse])
def get_all_analyses(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Fetch all historical RCA analyses (for dashboard/RAG views).
    """
    analyses = rca_agent.get_all_analyses(db, skip=skip, limit=limit)
    return analyses


@router.post("/{log_id}/diagnose-codebase", response_model=DiagnoseCodebaseResponse)
def diagnose_codebase(log_id: int, db: Session = Depends(get_db)):
    """
    Read-only: searches the configured target codebase for files likely
    responsible for this log's error, using its RCA's stack trace and
    affected services/dependencies. Never writes to the target repo.
    """
    return _diagnose(db, log_id)


@router.post("/{log_id}/ask-ai", response_model=AskAiResponse)
def ask_ai_for_fix(log_id: int, payload: Optional[AskAiRequest] = None, db: Session = Depends(get_db)):
    """
    Sends the RCA context plus the top candidate files' content to whichever
    AI provider is currently configured (Claude / Gemini / local Ollama) and
    returns a structured fix plus a unified diff against the current file
    for the user to review. Never writes the suggestion back to the target
    codebase -- pushing it to GitLab is a separate, explicit step
    (POST /{log_id}/gitlab-fix).
    """
    analysis = rca_agent.get_analysis(db, log_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"No RCA analysis found for log_id={log_id}")
    log = analysis.log

    requested_paths = payload.candidate_file_paths if payload else None
    target_path = _get_configured_codebase_path(db)
    if requested_paths:
        candidate_paths = requested_paths
    else:
        diagnosis = _diagnose(db, log_id)
        candidate_paths = [c.file_path for c in diagnosis.candidates]

    if not candidate_paths:
        raise HTTPException(
            status_code=400,
            detail='No candidate files found to send to the AI. Run "Diagnose in Codebase" first.'
        )

    # Stack-trace line per file name, so each file is sent as a window around
    # the failing line instead of just its first few KB.
    frame_lines = {}
    for f in parse_stack_trace_frames(log.stacktrace, log.message):
        frame_lines.setdefault(f["file"].lower(), f["line"])

    file_sections = []
    files_used = []
    matched_lines = {}
    for file_path in candidate_paths[:MAX_FILES_SENT_TO_AI]:
        matched_line = frame_lines.get(os.path.basename(file_path).lower())
        try:
            context = build_file_context(file_path, matched_line)
        except Exception as e:
            logger.warning(f"Could not read {file_path} for AI prompt: {e}")
            continue
        header = f"--- {file_path} ---"
        if matched_line:
            header += f" (stack trace points at line {matched_line})"
        file_sections.append(f"{header}\n{context}")
        files_used.append(file_path)
        matched_lines[file_path] = matched_line

    if not file_sections:
        raise HTTPException(status_code=400, detail="Candidate files could not be read (unreachable or permission denied).")

    prompt = f"""You are helping diagnose and fix a production application bug.

Root cause analysis:
- Category: {analysis.root_cause_category}
- Severity: {analysis.severity}
- Root cause: {analysis.root_cause}
- Summary: {analysis.summary or "N/A"}
- Recommendation: {analysis.recommendation or "N/A"}

Log message:
{log.message}

Stack trace:
{log.stacktrace or "N/A"}

Candidate source files from the application codebase (most likely responsible, based on the stack trace / RCA).
Each line is prefixed with its line number and " | " -- that prefix is NOT part of the code:

{chr(10).join(file_sections)}

Identify the bug and propose a minimal, targeted code fix. Respond with ONLY a JSON object, no other text, in this exact shape:
{{
  "explanation": "What is going wrong and why, and how the fix addresses it (plain text, a few sentences).",
  "fixes": [
    {{
      "file_path": "<one of the file paths above, exactly as given>",
      "rationale": "Why this specific change is needed.",
      "original": "<the exact current lines to replace, copied verbatim from the file WITHOUT the line-number prefix, including original indentation; 3-15 whole lines>",
      "replacement": "<the full new code that replaces those lines, with correct indentation>"
    }}
  ]
}}
Rules: "original" must match the current file character-for-character so it can be located and diffed. Keep each fix as small as possible; use several entries for edits in separate places. Do not include unrelated refactoring. If no code change is appropriate (e.g. it is a configuration or data issue), return an empty "fixes" list and explain why.
"""

    try:
        provider, model, raw_text = get_ai_suggestion(db, prompt)
    except AiProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"AI provider call failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI provider call failed: {str(e)}")

    parsed = parse_fix_response(raw_text)
    if not parsed:
        # Model ignored the JSON format -- still show what it said.
        return AskAiResponse(log_id=log_id, provider=provider, model=model, suggestion=raw_text, files_used=files_used)

    fixes = []
    for item in parsed.get("fixes") or []:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "")
        replacement = str(item.get("replacement") or "")
        requested = str(item.get("file_path") or "")
        # Only ever diff against files we actually sent; match loosely in
        # case the model shortened or re-slashed the path.
        file_path = next(
            (p for p in files_used if os.path.normcase(p) == os.path.normcase(requested)),
            next((p for p in files_used if os.path.basename(p).lower() == os.path.basename(requested).lower()), None)
        )
        if not file_path or not original.strip():
            continue
        fix = build_fix(file_path, original, replacement, target_path, matched_lines.get(file_path))
        fixes.append(CodeFixSuggestion(rationale=item.get("rationale"), **fix))

    combined_patch = "".join(f.diff for f in fixes if f.applied and f.diff) or None

    return AskAiResponse(
        log_id=log_id,
        provider=provider,
        model=model,
        suggestion=str(parsed.get("explanation") or ""),
        files_used=files_used,
        fixes=fixes,
        combined_patch=combined_patch,
    )


def _get_log(db: Session, log_id: int) -> Log:
    log = db.get(Log, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found.")
    return log


@router.get("/{log_id}/gitlab-fix/defaults", response_model=GitlabFixDefaultsResponse)
def get_gitlab_fix_defaults(log_id: int, db: Session = Depends(get_db)):
    """
    Pre-fills the "Push fix to GitLab" form: the code repository and base
    branch (from the target codebase checkout, or the Settings override), a
    fresh branch name and a commit message.
    """
    log = _get_log(db, log_id)
    return get_publish_defaults(db, log, app_setting_repo.get(db, TARGET_CODEBASE_PATH_KEY))


@router.post("/{log_id}/gitlab-fix", response_model=GitlabFixPushResponse)
def push_fix_to_gitlab(log_id: int, payload: GitlabFixPushRequest, db: Session = Depends(get_db)):
    """
    Commits the reviewed AI fixes to a NEW branch in the code repository
    (created from base_branch) and optionally opens a Draft merge request.
    The edits are re-applied to the base branch's files on GitLab; if any of
    them don't match, nothing is created.
    """
    log = _get_log(db, log_id)
    try:
        return publish_fix(
            db, log,
            codebase_path=app_setting_repo.get(db, TARGET_CODEBASE_PATH_KEY),
            fixes=[f.model_dump() for f in payload.fixes],
            base_branch=payload.base_branch,
            branch_name=payload.branch_name,
            commit_message=payload.commit_message,
            create_merge_request=payload.create_merge_request,
            explanation=payload.explanation,
        )
    except FixPublishError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Pushing fix for log {log_id} to GitLab failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"GitLab request failed: {e}")
