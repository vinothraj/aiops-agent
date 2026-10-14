import configparser
import logging
import os
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import gitlab
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import GitlabIssue, IncidentDecision, IssueActivity, Log
from app.repositories.repositories import app_setting_repo
from app.services.gitlab.gitlab_agent import get_gitlab_config, is_gitlab_configured
from app.services.rca.code_fix import apply_edit, unified_diff

logger = logging.getLogger(__name__)

# The repository AI fixes are pushed to. Separate from GITLAB_PROJECT_ID
# (where incident issues are filed), since the issue tracker project is often
# not the application's code repository. Empty -> auto-detected from the
# target codebase checkout's `origin` remote.
GITLAB_CODE_PROJECT_SETTING = "gitlab_code_project"
# Branch fixes are based on / merged back into. Empty -> the target codebase
# checkout's current branch.
GITLAB_FIX_BASE_BRANCH_SETTING = "gitlab_fix_base_branch"

BRANCH_PREFIX = "aiops/fix-log-"
_INVALID_BRANCH_CHARS = re.compile(r"[^A-Za-z0-9._/-]+")


class FixPublishError(Exception):
    """User-facing failure: bad input, missing config, or edits that don't match the branch."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ─── Local checkout inspection ───────────────────────────────────────────────

def find_git_root(path: str) -> Optional[str]:
    """Walks up from `path` to the directory holding `.git`, or None."""
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _git_dir(repo_root: str) -> Optional[str]:
    """Resolves `.git`, following the `gitdir:` pointer used by worktrees."""
    dot_git = os.path.join(repo_root, ".git")
    if os.path.isdir(dot_git):
        return dot_git
    try:
        with open(dot_git, "r", encoding="utf-8") as f:
            line = f.read().strip()
    except OSError:
        return None
    if line.startswith("gitdir:"):
        target = line[len("gitdir:"):].strip()
        return target if os.path.isabs(target) else os.path.normpath(os.path.join(repo_root, target))
    return None


def read_local_checkout(repo_root: str) -> dict:
    """
    Reads the checkout's current branch and `origin` URL straight from the
    .git files -- no git binary needed, and it works on network shares.
    """
    info = {"branch": None, "remote_url": None}
    git_dir = _git_dir(repo_root)
    if not git_dir:
        return info

    try:
        with open(os.path.join(git_dir, "HEAD"), "r", encoding="utf-8") as f:
            head = f.read().strip()
        if head.startswith("ref: refs/heads/"):
            info["branch"] = head[len("ref: refs/heads/"):]
    except OSError:
        pass

    # A worktree's config lives in the main repo's git dir ("commondir").
    config_dir = git_dir
    try:
        with open(os.path.join(git_dir, "commondir"), "r", encoding="utf-8") as f:
            config_dir = os.path.normpath(os.path.join(git_dir, f.read().strip()))
    except OSError:
        pass
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read(os.path.join(config_dir, "config"), encoding="utf-8")
        info["remote_url"] = parser.get('remote "origin"', "url", fallback=None)
    except configparser.Error:
        pass
    return info


def project_path_from_remote(remote_url: Optional[str], gitlab_url: Optional[str]) -> Optional[str]:
    """
    'https://host/CAP/Endor.git' or 'git@host:CAP/Endor.git' -> 'CAP/Endor',
    but only when the remote is on the configured GitLab host.
    """
    if not remote_url or not gitlab_url:
        return None
    gitlab_host = (urlparse(gitlab_url).hostname or "").lower()

    scp = re.match(r"^[\w.-]+@([^:/]+):(.+)$", remote_url)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        parsed = urlparse(remote_url)
        host, path = parsed.hostname or "", parsed.path

    if host.lower() != gitlab_host:
        return None
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path or None


# ─── Defaults for the "Push fix to GitLab" form ───────────────────────────────

def suggest_branch_name(log: Log) -> str:
    service = _INVALID_BRANCH_CHARS.sub("-", (log.service_name or "app").lower()).strip("-./")[:30] or "app"
    return f"{BRANCH_PREFIX}{log.id}-{service}-{datetime.now().strftime('%Y%m%d%H%M')}"


def resolve_code_project(db: Session, codebase_path: Optional[str]) -> dict:
    """
    Which GitLab project/branch the fix goes to: the Settings override if set,
    else what the local checkout of the target codebase points at.
    """
    config = get_gitlab_config(db)
    repo_root = find_git_root(codebase_path) if codebase_path else None
    checkout = read_local_checkout(repo_root) if repo_root else {"branch": None, "remote_url": None}
    detected = project_path_from_remote(checkout["remote_url"], config["url"])
    override = (app_setting_repo.get(db, GITLAB_CODE_PROJECT_SETTING) or "").strip()
    return {
        "project": override or detected,
        "detected_project": detected,
        "repo_root": repo_root,
        "local_branch": checkout["branch"],
        "base_branch": (app_setting_repo.get(db, GITLAB_FIX_BASE_BRANCH_SETTING) or "").strip() or checkout["branch"],
    }


def get_publish_defaults(db: Session, log: Log, codebase_path: Optional[str]) -> dict:
    resolved = resolve_code_project(db, codebase_path)
    issue = linked_issue(db, log.id)
    return {
        "configured": is_gitlab_configured(db),
        "project": resolved["project"],
        "base_branch": resolved["base_branch"],
        "branch_name": suggest_branch_name(log),
        "commit_message": f"Fix {log.service_name or 'application'} error (AIOps log #{log.id})",
        "linked_issue_url": issue.web_url if issue else None,
    }


def linked_issue(db: Session, log_id: int) -> Optional[GitlabIssue]:
    return db.scalar(
        select(GitlabIssue)
        .join(IncidentDecision, GitlabIssue.incident_decision_id == IncidentDecision.id)
        .where(IncidentDecision.log_id == log_id)
        .order_by(GitlabIssue.created_at.desc())
    )


# ─── Publishing ───────────────────────────────────────────────────────────────

def _repo_path(fix: dict, repo_root: Optional[str]) -> str:
    """Path of the fixed file inside the repository, '/'-separated."""
    file_path = fix.get("file_path")
    if repo_root and file_path:
        try:
            rel = os.path.relpath(file_path, repo_root)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:  # different drive on Windows
            pass
    return (fix.get("relative_path") or "").replace("\\", "/").lstrip("/")


def publish_fix(db: Session, log: Log, codebase_path: Optional[str], fixes: List[dict], base_branch: str,
                branch_name: str, commit_message: str, create_merge_request: bool,
                explanation: Optional[str] = None) -> dict:
    """
    Creates `branch_name` from `base_branch` in the code project, commits the
    AI fixes to it in a single commit, and optionally opens a Draft merge
    request back into `base_branch`.

    Every edit is re-applied to the *branch's* copy of each file, not the
    local one the diff was previewed against, and all of them must match
    before anything is created -- so a stale or hallucinated edit fails
    cleanly instead of leaving a half-written branch. Never commits to an
    existing branch.
    """
    if not fixes:
        raise FixPublishError("No code changes to commit.")
    branch_name = (branch_name or "").strip()
    base_branch = (base_branch or "").strip()
    commit_message = (commit_message or "").strip()
    if not base_branch:
        raise FixPublishError("Base branch is required.")
    if not branch_name or _INVALID_BRANCH_CHARS.search(branch_name) or ".." in branch_name \
            or branch_name.startswith(("/", "-")) or branch_name.endswith(("/", ".", ".lock")):
        raise FixPublishError(f"Invalid branch name: '{branch_name}'.")
    if branch_name == base_branch:
        raise FixPublishError("The new branch must differ from the base branch.")
    if not commit_message:
        raise FixPublishError("Commit message is required.")

    config = get_gitlab_config(db)
    if not (config["url"] and config["token"]):
        raise FixPublishError("GitLab is not configured. Set it up in Settings -> GitLab Integration.")
    resolved = resolve_code_project(db, codebase_path)
    if not resolved["project"]:
        raise FixPublishError(
            "Could not determine the GitLab code repository. The target codebase has no 'origin' remote on "
            f"{config['url']} -- set the code repository in Settings -> GitLab Integration."
        )

    gl = gitlab.Gitlab(url=config["url"], private_token=config["token"], ssl_verify=False)
    try:
        project = gl.projects.get(resolved["project"])
    except gitlab.exceptions.GitlabGetError as e:
        raise FixPublishError(f"GitLab project '{resolved['project']}' not accessible: {e.error_message}", 404)

    try:
        project.branches.get(base_branch)
    except gitlab.exceptions.GitlabGetError:
        raise FixPublishError(
            f"Base branch '{base_branch}' does not exist in {project.path_with_namespace}. "
            "Push it first or pick another branch."
        , 404)
    try:
        project.branches.get(branch_name)
        raise FixPublishError(f"Branch '{branch_name}' already exists -- choose a new branch name.", 409)
    except gitlab.exceptions.GitlabGetError:
        pass

    # Apply all edits in memory against the base branch before touching GitLab.
    files = {}  # repo path -> {"lines": [...], "original": [...]}
    failures = []
    for fix in fixes:
        path = _repo_path(fix, resolved["repo_root"])
        if not path:
            failures.append(f"{fix.get('file_path')}: no repository path")
            continue
        if path not in files:
            try:
                raw = project.files.get(file_path=path, ref=base_branch).decode()
            except gitlab.exceptions.GitlabGetError:
                failures.append(f"{path}: not found on {base_branch}")
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                failures.append(f"{path}: not a UTF-8 text file")
                continue
            lines = text.splitlines(keepends=True)
            files[path] = {"lines": lines, "original": lines}
        edit = apply_edit(files[path]["lines"], fix.get("original") or "", fix.get("replacement") or "",
                          fix.get("start_line"))
        if not edit:
            failures.append(f"{path}: the code to replace was not found on {base_branch} (branch differs from local copy?)")
            continue
        files[path]["lines"] = edit[0]

    if failures:
        raise FixPublishError("Nothing was pushed. " + "; ".join(failures), 409)
    changed = {p: f for p, f in files.items() if f["lines"] != f["original"]}
    if not changed:
        raise FixPublishError("The fixes produce no change on the base branch -- nothing to commit.", 409)

    project.branches.create({"branch": branch_name, "ref": base_branch})
    try:
        commit = project.commits.create({
            "branch": branch_name,
            "commit_message": commit_message,
            "actions": [
                {"action": "update", "file_path": p, "content": "".join(f["lines"])}
                for p, f in changed.items()
            ],
        })
    except Exception:
        # Don't leave an empty branch behind.
        try:
            project.branches.delete(branch_name)
        except Exception as cleanup_error:
            logger.warning(f"Could not delete branch {branch_name} after failed commit: {cleanup_error}")
        raise

    web_base = project.web_url
    result = {
        "project": project.path_with_namespace,
        "base_branch": base_branch,
        "branch": branch_name,
        "branch_url": f"{web_base}/-/tree/{branch_name}",
        "commit_sha": commit.id,
        "commit_url": f"{web_base}/-/commit/{commit.id}",
        "merge_request_url": None,
        "files": list(changed.keys()),
        "diff": "".join(unified_diff(f["original"], f["lines"], p) for p, f in changed.items()),
    }

    issue = linked_issue(db, log.id)
    if create_merge_request:
        description = [f"Automated fix proposed by AIOps for log #{log.id} ({log.service_name}).", ""]
        if explanation:
            description += ["### Analysis", explanation, ""]
        if issue:
            description.append(f"Related issue: {issue.web_url}")
        description += ["", "---", "*Generated by AIOps Platform -- review before merging.*"]
        mr = project.mergerequests.create({
            "source_branch": branch_name,
            "target_branch": base_branch,
            "title": f"Draft: {commit_message.splitlines()[0]}",
            "description": "\n".join(description),
            "remove_source_branch": True,
        })
        result["merge_request_url"] = mr.web_url

    link = result["merge_request_url"] or result["commit_url"]
    comment_on_incident_issue(
        db, log.id,
        body=f"AIOps pushed a proposed fix to `{result['project']}` branch `{result['branch']}`: {link}",
        action_type="fix_pushed",
        activity=f"Fix pushed to {result['project']}@{result['branch']}: {link}",
    )

    logger.info(f"Pushed AI fix for log {log.id} to {project.path_with_namespace}@{branch_name} ({commit.short_id})")
    return result


def comment_on_incident_issue(db: Session, log_id: int, body: str, action_type: str, activity: str) -> bool:
    """
    Best-effort: posts `body` as a comment on the GitLab issue filed for this
    log's incident (if any) and records it in the issue's activity history.
    Never raises -- a GitLab hiccup must not fail the caller's main action.
    """
    issue = linked_issue(db, log_id)
    if not issue:
        return False
    config = get_gitlab_config(db)
    if not (config["url"] and config["token"] and config["project_id"]):
        return False
    try:
        gl = gitlab.Gitlab(url=config["url"], private_token=config["token"], ssl_verify=False)
        gl.projects.get(config["project_id"], lazy=True).issues.get(issue.gitlab_issue_iid).notes.create({"body": body})
        db.add(IssueActivity(gitlab_issue_id=issue.id, action_type=action_type, description=activity))
        db.commit()
        return True
    except Exception as e:
        logger.warning(f"Could not comment on GitLab issue {issue.gitlab_issue_iid}: {e}")
        db.rollback()
        return False
