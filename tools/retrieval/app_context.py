"""Retrieve traceable context from one Android App source tree."""
import re
from pathlib import Path


SOURCE_SUFFIXES = {".xml", ".kt", ".java"}
EXCLUDED_PARTS = {
    ".git",
    ".gradle",
    ".idea",
    "build",
    "node_modules",
    "target",
}
ANDROID_ID_RE = re.compile(r"(?:@\+?id/|R\.id\.)([A-Za-z0-9_]+)")
RESOURCE_RE = re.compile(
    r"@(?:string|drawable|mipmap)/([A-Za-z0-9_]+)"
)


def safe_source_files(source_root):
    root = Path(source_root).resolve()
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        yield path


def evidence_terms(issue):
    attributes = issue.get("attributes", {}) or {}
    values = [
        issue.get("component", ""),
        issue.get("element", ""),
        issue.get("selector", ""),
        *[str(value) for value in attributes.values()],
    ]
    ids = []
    resources = []
    for value in values:
        ids.extend(ANDROID_ID_RE.findall(value))
        resources.extend(RESOURCE_RE.findall(value))
    return {
        "ids": sorted(set(ids)),
        "resources": sorted(set(resources)),
    }


def excerpt(lines, center, radius=4):
    start = max(center - radius, 0)
    end = min(center + radius + 1, len(lines))
    return start + 1, end, "".join(lines[start:end]).strip()


def retrieve_app_context(source_root, issue, limit=8):
    root = Path(source_root).resolve()
    terms = evidence_terms(issue)
    needles = terms["ids"] + terms["resources"]
    if not needles:
        return []
    candidates = []
    for path in safe_source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines(keepends=True)
        for line_index, line in enumerate(lines):
            matched = [needle for needle in needles if needle in line]
            if not matched:
                continue
            start, end, content = excerpt(lines, line_index)
            relative = path.relative_to(root).as_posix()
            if path.suffix in {".kt", ".java"}:
                kind = "controller_code"
                base_score = 4
            elif "/values" in f"/{relative}":
                kind = "resource_value"
                base_score = 3
            else:
                kind = "xml_context"
                base_score = 2
            score = base_score + len(set(matched))
            candidates.append({
                "path": relative,
                "kind": kind,
                "line_start": start,
                "line_end": end,
                "score": score,
                "matched_terms": sorted(set(matched)),
                "excerpt": content,
                "source_root": str(root),
            })
    candidates.sort(
        key=lambda item: (-item["score"], item["path"], item["line_start"])
    )
    results = []
    seen = set()
    for candidate in candidates:
        signature = (candidate["path"], candidate["line_start"], candidate["line_end"])
        if signature in seen:
            continue
        seen.add(signature)
        results.append(candidate)
        if len(results) >= limit:
            break
    return results


def retrieve_app_context_for_issues(
    source_root,
    issues,
    per_issue_limit=4,
    prompt_limit=12,
):
    if per_issue_limit < 1 or prompt_limit < 1:
        raise ValueError("Invalid App-context retrieval limits")
    merged = []
    seen = set()
    for issue_index, issue in enumerate(issues):
        for result in retrieve_app_context(
            source_root,
            issue,
            limit=per_issue_limit,
        ):
            signature = (
                result["path"],
                result["line_start"],
                result["line_end"],
            )
            if signature in seen:
                continue
            seen.add(signature)
            merged.append({
                **result,
                "issue_index": issue_index,
                "issue_code": issue.get("code"),
                "issue_selector": issue.get("selector"),
            })
            if len(merged) >= prompt_limit:
                return merged
    return merged
