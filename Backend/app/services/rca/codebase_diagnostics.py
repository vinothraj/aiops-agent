import os
import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Matches "SomeClass.java:123" whether or not it's preceded by "at " -- covers
# both real stack trace frames and inline file:line references some log lines
# embed directly in the message (e.g. "(BIWRecentlyViewedProductsProcessor.java:93)").
_FRAME_PATTERN = re.compile(r'([A-Za-z0-9_$]+\.(?:java|py|ts|js|kt|cs))(?::|,\s*line\s*)(\d+)', re.IGNORECASE)

# Directories that are never source-of-truth for application code -- skipped
# while walking the target repo to keep scans fast and avoid noise.
_SKIP_DIRS = {
    '.git', '.svn', '.hg', 'node_modules', 'target', 'build', 'dist', 'out',
    '.idea', '.vscode', '.gradle', '.mvn', '__pycache__', 'venv', '.venv', 'bin', 'obj'
}

MAX_FILES_SCANNED = 20000
MAX_CANDIDATES = 15
MAX_FRAMES = 20
SNIPPET_CONTEXT_LINES = 10


def parse_stack_trace_frames(*texts: Optional[str]) -> List[dict]:
    """
    Extracts (file, line) references from stack traces / log messages.
    Dedupes while preserving first-seen order, capped at MAX_FRAMES.
    """
    seen = set()
    frames = []
    for text in texts:
        if not text:
            continue
        for match in _FRAME_PATTERN.finditer(text):
            file_name, line_str = match.group(1), match.group(2)
            key = (file_name.lower(), line_str)
            if key in seen:
                continue
            seen.add(key)
            frames.append({"file": file_name, "line": int(line_str)})
            if len(frames) >= MAX_FRAMES:
                return frames
    return frames


def _read_snippet(file_path: str, line_number: Optional[int]) -> Optional[str]:
    if not line_number:
        return None
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        logger.warning(f"Could not read snippet from {file_path}: {e}")
        return None

    start = max(0, line_number - 1 - SNIPPET_CONTEXT_LINES)
    end = min(len(lines), line_number + SNIPPET_CONTEXT_LINES)
    if start >= len(lines):
        return None
    return "".join(lines[start:end])


def search_codebase_for_candidates(root_path: str, frames: List[dict], keywords: List[str]) -> tuple[List[dict], bool]:
    """
    Walks root_path looking for files matching stack trace frames first (exact
    filename match), falling back to keyword search (service/dependency/category
    names appearing in the filename) if no frame matched anything -- e.g. the
    real cause is a misconfiguration rather than the class that happened to
    throw. Read-only: only ever opens files for reading. Returns
    (candidates, truncated) where truncated indicates the file-count cap was hit.
    """
    frame_targets = {f["file"].lower(): f["line"] for f in frames}
    clean_keywords = [k.strip().lower() for k in keywords if k and len(k.strip()) >= 3]

    frame_matches = []
    keyword_matches = []
    files_scanned = 0
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith('.')]

        for filename in filenames:
            files_scanned += 1
            if files_scanned > MAX_FILES_SCANNED:
                truncated = True
                break

            file_path = os.path.join(dirpath, filename)
            lower_name = filename.lower()

            if lower_name in frame_targets:
                line_number = frame_targets[lower_name]
                frame_matches.append({
                    "file_path": file_path,
                    "match_reason": f"stack trace frame: {filename}:{line_number}",
                    "matched_line": line_number,
                    "snippet": _read_snippet(file_path, line_number),
                })
            elif not frame_matches and clean_keywords:
                hit_count = sum(1 for kw in clean_keywords if kw in lower_name)
                if hit_count > 0:
                    keyword_matches.append((hit_count, {
                        "file_path": file_path,
                        "match_reason": f"filename matches {hit_count} keyword(s) from the RCA (service/dependency/category)",
                        "matched_line": None,
                        "snippet": None,
                    }))
        if truncated:
            break

    if frame_matches:
        return frame_matches[:MAX_CANDIDATES], truncated

    keyword_matches.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in keyword_matches[:MAX_CANDIDATES]], truncated
