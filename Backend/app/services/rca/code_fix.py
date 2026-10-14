import difflib
import json
import logging
import os
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# How much of each candidate file the AI gets to see. Files are sent as a
# line-numbered window around the stack-trace line (plus the file header for
# imports / class declaration) rather than just the first N characters --
# otherwise the failing line in a large class is often never sent at all.
HEADER_LINES = 40
WINDOW_LINES_BEFORE = 60
WINDOW_LINES_AFTER = 40
MAX_LINES_WITHOUT_ANCHOR = 200
DIFF_CONTEXT_LINES = 3

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def read_lines(file_path: str) -> List[str]:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines(keepends=True)


def _numbered(lines: List[str], start: int, end: int) -> str:
    return "".join(f"{i + 1:>5} | {lines[i]}" if lines[i].endswith("\n") else f"{i + 1:>5} | {lines[i]}\n"
                   for i in range(start, end))


def build_file_context(file_path: str, matched_line: Optional[int]) -> str:
    """
    Line-numbered excerpt of file_path for the AI prompt: the file header plus
    a window around matched_line, or the top of the file if there's no
    stack-trace line to anchor on.
    """
    lines = read_lines(file_path)
    total = len(lines)

    if not matched_line or matched_line > total:
        end = min(total, MAX_LINES_WITHOUT_ANCHOR)
        body = _numbered(lines, 0, end)
        if end < total:
            body += f"  ... ({total - end} more lines not shown)\n"
        return body

    win_start = max(0, matched_line - 1 - WINDOW_LINES_BEFORE)
    win_end = min(total, matched_line + WINDOW_LINES_AFTER)
    parts = []
    if win_start > HEADER_LINES:
        parts.append(_numbered(lines, 0, HEADER_LINES))
        parts.append(f"  ... (lines {HEADER_LINES + 1}-{win_start} not shown)\n")
    else:
        win_start = 0
    parts.append(_numbered(lines, win_start, win_end))
    if win_end < total:
        parts.append(f"  ... ({total - win_end} more lines not shown)\n")
    return "".join(parts)


def parse_fix_response(text: str) -> Optional[dict]:
    """
    Pulls the {"explanation": ..., "fixes": [...]} object out of the AI's
    reply, tolerating markdown fences or prose around it. Returns None if no
    usable JSON was found (caller falls back to showing the raw text).
    """
    if not text:
        return None
    candidates = []
    fence = _JSON_FENCE.search(text)
    if fence:
        candidates.append(fence.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first:last + 1])

    for raw in candidates:
        try:
            # strict=False: models often emit raw newlines inside code strings.
            parsed = json.loads(raw, strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("fixes"), list):
            return parsed
    return None


def _find_anchor(lines: List[str], original: str, near_line: Optional[int]) -> Optional[tuple]:
    """
    Locates `original` in the file as a run of whole lines. Exact match first,
    then a whitespace-insensitive match (AI output often drifts on
    indentation). When it occurs more than once, picks the occurrence closest
    to the stack-trace line. Returns (start_index, end_index) or None.
    """
    orig_lines = original.strip("\n").splitlines()
    if not orig_lines:
        return None
    n = len(orig_lines)

    for normalize in (lambda s: s.rstrip("\r\n"), lambda s: " ".join(s.split())):
        target = [normalize(l) for l in orig_lines]
        file_norm = [normalize(l) for l in lines]
        hits = [i for i in range(len(lines) - n + 1) if file_norm[i:i + n] == target]
        if hits:
            if near_line:
                hits.sort(key=lambda i: abs(i + 1 - near_line))
            return hits[0], hits[0] + n
    return None


def build_fix(file_path: str, original: str, replacement: str, root_path: Optional[str],
              near_line: Optional[int]) -> dict:
    """
    Applies one AI-proposed edit to an in-memory copy of file_path and returns
    a unified diff against the current file. Never writes to disk.
    `applied` is False when `original` couldn't be found verbatim in the file
    (the AI paraphrased or hallucinated the code) -- the UI then shows the
    proposed before/after but warns that it doesn't match the current code.
    """
    rel_path = os.path.relpath(file_path, root_path) if root_path else os.path.basename(file_path)
    rel_path = rel_path.replace("\\", "/")
    result = {
        "file_path": file_path,
        "relative_path": rel_path,
        "original": original,
        "replacement": replacement,
        "applied": False,
        "start_line": None,
        "diff": None,
    }

    try:
        lines = read_lines(file_path)
    except Exception as e:
        logger.warning(f"Could not read {file_path} to build fix diff: {e}")
        return result

    edit = apply_edit(lines, original, replacement, near_line)
    if not edit:
        return result

    patched, start = edit
    diff = unified_diff(lines, patched, rel_path)
    result.update(applied=bool(diff), start_line=start + 1, diff=diff or None)
    return result


def apply_edit(lines: List[str], original: str, replacement: str,
               near_line: Optional[int]) -> Optional[Tuple[List[str], int]]:
    """
    Replaces the run of lines matching `original` with `replacement`, keeping
    the file's line endings. Returns (patched_lines, start_index), or None when
    `original` isn't in `lines`. Shared by the local diff preview and the
    GitLab commit, which re-applies the edit to the branch's copy of the file.
    """
    anchor = _find_anchor(lines, original, near_line)
    if not anchor:
        return None

    start, end = anchor
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    new_block = [l + newline for l in replacement.strip("\n").splitlines()] if replacement.strip("\n") else []
    # Keep the file's trailing-newline state if the edit touched the last line.
    if end == len(lines) and new_block and not lines[-1].endswith("\n"):
        new_block[-1] = new_block[-1].rstrip("\r\n")
    return lines[:start] + new_block + lines[end:], start


def unified_diff(before: List[str], after: List[str], rel_path: str) -> str:
    def _terminated(seq: List[str]) -> List[str]:
        return [l if l.endswith("\n") else l + "\n" for l in seq]

    return "".join(difflib.unified_diff(
        _terminated(before), _terminated(after),
        fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}",
        n=DIFF_CONTEXT_LINES,
    ))
