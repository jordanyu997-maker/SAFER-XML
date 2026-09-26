#!/usr/bin/env python3
"""Fill V2 long-tail gaps from new F-Droid repositories without model calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.build_candidate_manifest import (  # noqa: E402
    cap_per_app_type,
    select_repository_metadata,
    v1_current_snapshot,
)
from scripts.source_prescreen.clone_sparse_repo import clone_one  # noqa: E402
from scripts.source_prescreen.common import (  # noqa: E402
    CANDIDATE_FIELDS,
    ensure_output_is_v2,
    json_cell,
    normalize_repo_url,
    read_csv,
    sha256_text,
    write_csv,
)
from scripts.source_prescreen.resolve_android_resources import (  # noqa: E402
    AndroidResourceResolver,
    RESOURCE_REF_RE,
    discover_layout_files,
    line_number_for,
)
from scripts.source_prescreen.scan_android_xml import (  # noqa: E402
    REPOSITORY_FIELDS,
    classify_repository,
    repository_origin,
    scan_repository,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    EMAIL_TERMS,
    NUMBER_TERMS,
    PASSWORD_TERMS,
    PHONE_TERMS,
    SPECIFIC_NUMBER_TERMS,
    attr,
    build_label_map,
    build_parent_map,
    is_editable_input,
    normalize_view_type,
    parse_id,
    resolve_string,
    strip_ns,
    text_input_layout_hint,
)


TARGET_REQUIREMENTS = {
    "input_type_semantics": {"instances": 8, "apps": 0},
    "label_association": {"instances": 5, "apps": 1},
    "accessibility_attribute_conflict": {"instances": 11, "apps": 2},
}
TARGET_TYPES = set(TARGET_REQUIREMENTS)
TARGET_REPOSITORY_FIELDS = REPOSITORY_FIELDS + (
    "targeted_status", "skip_reason", "target_marker_counts",
)
STANDARD_INTERACTIVE_TYPES = {
    "Button", "ImageButton", "EditText", "SelectionControl", "CheckBox",
    "RadioButton", "Switch", "SeekBar",
}
SEMANTIC_TERMS = {
    "email": tuple(EMAIL_TERMS),
    "phone": tuple(PHONE_TERMS),
    "password": tuple(PASSWORD_TERMS),
    "number": tuple(dict.fromkeys((*SPECIFIC_NUMBER_TERMS, *NUMBER_TERMS))),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def metadata_by_origin(rows: list[dict]) -> dict[str, list[dict]]:
    result = defaultdict(list)
    for row in rows:
        origin = normalize_repo_url(row.get("repository_url", ""))
        if origin:
            result[origin].append(row)
    return result


def unique_new_metadata(rows: list[dict], excluded_origins: set[str]) -> list[dict]:
    """Select one build per unseen origin without reading names or descriptions."""
    by_origin = defaultdict(list)
    for row in rows:
        origin = normalize_repo_url(row.get("repository_url", ""))
        if not origin or origin in excluded_origins or row.get("repo_type") != "git":
            continue
        by_origin[origin].append(row)

    def version_key(row: dict) -> tuple[int, str, str]:
        raw = str(row.get("version_code") or "")
        return (int(raw) if raw.isdigit() else -1, row.get("commit_hash", ""), row.get("package_name", ""))

    selected = [max(group, key=version_key) for group in by_origin.values()]
    return sorted(
        selected,
        key=lambda row: sha256_text(
            normalize_repo_url(row["repository_url"]) + "|" + row.get("commit_hash", "")
        ),
    )


def discover_new_local_repositories(
    local_root: Path,
    excluded_origins: set[str],
    metadata_map: dict[str, list[dict]],
    names: set[str] | None = None,
) -> list[tuple[Path, dict]]:
    result = []
    for git_dir in sorted(local_root.glob("*/.git")):
        repository = git_dir.parent
        if names and repository.name.casefold() not in names:
            continue
        origin = normalize_repo_url(repository_origin(repository))
        if not origin or origin in excluded_origins or origin not in metadata_map:
            continue
        metadata = select_repository_metadata(metadata_map[origin], repository)
        result.append((repository, metadata))
    return result


def target_marker_counts(repository: Path, subdir: str) -> dict[str, int]:
    patterns = {
        "input_widget": re.compile(r"<(?:[\w.]*EditText|[\w.]*AutoCompleteTextView)\b"),
        "input_type": re.compile(r"(?:android:)?inputType\s*="),
        "label_for": re.compile(r"(?:android:)?labelFor\s*="),
        "important_no": re.compile(r"importantForAccessibility\s*=\s*[\"'](?:no|noHideDescendants)[\"']"),
        "focusable_false": re.compile(r"focusable\s*=\s*[\"']false[\"']"),
        "clickable": re.compile(r"(?:clickable\s*=\s*[\"']true[\"']|android:onClick\s*=)"),
    }
    counts = {key: 0 for key in patterns}
    for path in discover_layout_files(repository, subdir):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key, pattern in patterns.items():
            counts[key] += len(pattern.findall(text))
    return counts


def has_target_markers(counts: dict[str, int]) -> bool:
    semantic = counts["input_widget"] > 0 and (
        counts["input_type"] > 0 or counts["label_for"] > 0
    )
    association = counts["label_for"] > 0
    conflict = counts["important_no"] > 0 or counts["focusable_false"] > 0
    return semantic or association or conflict


def _load_json_cell(row: dict, name: str) -> dict:
    try:
        value = json.loads(row.get(name) or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _resolved_attribute(row: dict, name: str, resolver: AndroidResourceResolver) -> str:
    resolved = _load_json_cell(row, "resolved_resource_values").get(name, {})
    value = resolved.get("value") if isinstance(resolved, dict) else ""
    if isinstance(value, str) and value:
        return value
    raw = _load_json_cell(row, "relevant_attributes").get(name, "")
    return resolve_string(str(raw), resolver.strings) if raw else ""


def _find_candidate_element(root: ET.Element, row: dict) -> ET.Element | None:
    attributes = _load_json_cell(row, "relevant_attributes")
    target_id = parse_id(attributes.get("id"))
    if target_id:
        for element in root.iter():
            if parse_id(attr(element, "id")) == target_id:
                return element
    widget = row.get("widget_type", "")
    for element in root.iter():
        if strip_ns(element.tag) == widget or normalize_view_type(element.tag) == normalize_view_type(widget):
            return element
    return None


def _semantic_kind(value: str) -> str:
    lowered = str(value or "").casefold()
    for kind, terms in SEMANTIC_TERMS.items():
        if any(str(term).casefold() in lowered for term in terms):
            return kind
    return ""


def semantic_evidence(row: dict, repository: Path, resolver: AndroidResourceResolver) -> dict[str, list[str]]:
    path = repository / row["xml_path"]
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return {}
    parent_map = build_parent_map(root)
    label_map = build_label_map(root, resolver.strings)
    element = _find_candidate_element(root, row)
    if element is None or not is_editable_input(element):
        return {}
    sources = {
        "hint": resolve_string(attr(element, "hint") or "", resolver.strings),
        "content_description": resolve_string(attr(element, "contentDescription") or "", resolver.strings),
        "label_for": label_map.get(parse_id(attr(element, "id")) or "", ""),
        "text_input_layout": resolve_string(text_input_layout_hint(element, parent_map) or "", resolver.strings),
        "layout_name": path.stem.replace("_", " "),
    }
    parent = parent_map.get(element)
    if parent is not None:
        siblings = list(parent)
        try:
            index = siblings.index(element)
        except ValueError:
            index = -1
        local_text = []
        for sibling in siblings[max(0, index - 2):index] if index >= 0 else []:
            if normalize_view_type(sibling.tag) == "TextView":
                value = resolve_string(attr(sibling, "text") or "", resolver.strings)
                if value:
                    local_text.append(value)
        sources["adjacent_visible_text"] = " ".join(local_text)
    evidence = defaultdict(list)
    for source, value in sources.items():
        kind = _semantic_kind(value)
        if kind:
            evidence[kind].append(f"{source}={value}")
    return dict(evidence)


def input_type_mismatches(kind: str, input_type: str, evidence: list[str]) -> bool:
    value = str(input_type or "").casefold()
    if kind == "email":
        return "email" not in value
    if kind == "phone":
        return "phone" not in value
    if kind == "password":
        return "password" not in value
    if kind == "number":
        decimal_terms = ("amount", "price", "money", "decimal", "金额", "小数")
        needs_decimal = any(term in " ".join(evidence).casefold() for term in decimal_terms)
        return "number" not in value or (needs_decimal and "decimal" not in value)
    return False


def validate_input_semantics(row: dict, repository: Path, resolver: AndroidResourceResolver) -> tuple[bool, str]:
    evidence = semantic_evidence(row, repository, resolver)
    attributes = _load_json_cell(row, "relevant_attributes")
    input_type = str(attributes.get("inputType") or "")
    supported = [
        (kind, values) for kind, values in evidence.items()
        if len(set(values)) >= 2 and input_type_mismatches(kind, input_type, values)
    ]
    if not supported:
        return False, "fewer than two independent semantic signals, or inputType mismatch is not explicit"
    kind, values = sorted(supported, key=lambda item: (-len(item[1]), item[0]))[0]
    return True, f"two-source semantic evidence ({kind}): " + " | ".join(values)


def layout_id_closure(
    path: Path,
    resolver: AndroidResourceResolver,
    visited: set[Path] | None = None,
) -> tuple[set[str], bool]:
    visited = visited or set()
    if path in visited:
        return set(), True
    visited.add(path)
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return set(), False
    ids = {parse_id(attr(element, "id")) for element in root.iter()}
    complete = True
    for element in root.iter():
        if strip_ns(element.tag) != "include":
            continue
        match = RESOURCE_REF_RE.match(element.attrib.get("layout", ""))
        if not match or match.group(1) != "layout" or not resolver.layouts.get(match.group(2)):
            complete = False
            continue
        for included in resolver.layouts[match.group(2)]:
            child_ids, child_complete = layout_id_closure(included, resolver, visited)
            ids.update(child_ids)
            complete = complete and child_complete
    return {value for value in ids if value}, complete


def validate_label_association(row: dict, repository: Path, resolver: AndroidResourceResolver) -> tuple[bool, str]:
    if row.get("issue_subtype") != "label_for_target_missing":
        return False, "only a missing labelFor target is XML-safe in targeted gap fill"
    attributes = _load_json_cell(row, "relevant_attributes")
    target = parse_id(attributes.get("labelFor"))
    if not target:
        return False, "labelFor target cannot be parsed"
    ids, complete = layout_id_closure(repository / row["xml_path"], resolver)
    if not complete:
        return False, "layout include closure is incomplete"
    if target in ids:
        return False, "labelFor target exists after include expansion"
    return True, f"labelFor target @{target} is absent after complete include expansion"


def validate_attribute_conflict(row: dict) -> tuple[bool, str, bool]:
    attributes = _load_json_cell(row, "relevant_attributes")
    important = str(attributes.get("importantForAccessibility") or "")
    if row.get("issue_subtype") == "interactive_control_hidden" and important in {"no", "noHideDescendants"}:
        return True, f"interactive element explicitly uses importantForAccessibility={important}", False
    if row.get("issue_subtype") == "interactive_control_not_focusable":
        component = normalize_view_type(row.get("widget_type", ""))
        explicit = str(attributes.get("focusable") or "").casefold() == "false"
        if explicit and component in STANDARD_INTERACTIVE_TYPES:
            return True, f"standard interactive {component} explicitly sets focusable=false", True
    return False, "conflict depends on parent structure, custom behavior, or runtime state", False


def _downgrade(row: dict, reason: str) -> dict:
    result = dict(row)
    result.update(
        severity="warning", confidence="medium", xml_safe="false",
        runtime_required="false", manual_review_status="pending",
        selection_status="excluded",
    )
    result["notes"] = "; ".join(filter(None, (result.get("notes", ""), reason)))
    return result


def is_high_xml_safe(row: dict) -> bool:
    return (
        row.get("severity") == "error"
        and row.get("confidence") == "high"
        and row.get("xml_safe") == "true"
        and row.get("runtime_required") == "false"
    )


def enforce_high_contract(high: list[dict], review: list[dict]) -> tuple[list[dict], list[dict]]:
    """Prevent a targeted adapter from promoting a warning or medium finding."""
    for row in high:
        if row.get("selection_status") == "candidate" and not is_high_xml_safe(row):
            downgraded = _downgrade(
                row,
                "excluded: original detector result does not satisfy the high XML-safe contract",
            )
            row.update(downgraded)
            review.append(dict(downgraded))
    return high, merge_by_id([], review)


def validate_target_candidates(
    repository: Path,
    metadata: dict,
    candidates: list[dict],
) -> tuple[list[dict], list[dict]]:
    resolver = AndroidResourceResolver(repository, metadata.get("subdir", ""))
    high = []
    review = []
    for original in candidates:
        row = dict(original)
        issue_type = row.get("issue_type")
        if issue_type == "input_type_semantics":
            valid, reason = validate_input_semantics(row, repository, resolver)
        elif issue_type == "label_association":
            valid, reason = validate_label_association(row, repository, resolver)
        elif issue_type == "accessibility_attribute_conflict":
            valid, reason, remapped = validate_attribute_conflict(row)
        elif issue_type == "focus_accessibility_tree" and row.get("issue_subtype") == "interactive_control_not_focusable":
            valid, reason, remapped = validate_attribute_conflict(row)
            if valid and remapped:
                row["issue_type"] = "accessibility_attribute_conflict"
                row["issue_subtype"] = "standard_interactive_focusable_false"
                row["candidate_id"] = "tgt-" + sha256_text(row["candidate_id"] + "|focus-conflict")[:20]
        elif issue_type == "touch_target_size":
            review.append(_downgrade(row, "touch target remains review-required in targeted gap fill"))
            continue
        else:
            continue
        if valid:
            if is_high_xml_safe(row):
                row["notes"] = "; ".join(filter(None, (row.get("notes", ""), "targeted validation: " + reason)))
                row["selection_status"] = "candidate"
                high.append(row)
            else:
                review.append(_downgrade(
                    row,
                    "targeted validation passed, but original severity/confidence was not high error",
                ))
        else:
            review.append(_downgrade(row, "targeted validation: " + reason))
    return high, review


def merge_by_id(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {row["candidate_id"]: row for row in existing}
    merged.update({row["candidate_id"]: row for row in incoming})
    return sorted(merged.values(), key=lambda row: (
        row["issue_type"], row["app_name"].casefold(), row["xml_path"], int(row["line_number"] or 0), row["candidate_id"],
    ))


def _configuration_neutral_xml_path(value: str) -> str:
    parts = Path(value).parts
    return "/".join("layout" if part.startswith("layout-") else part for part in parts)


def mark_configuration_variant_duplicates(candidates: list[dict]) -> None:
    """Do not count the same widget defect again in layout qualifier variants."""
    seen = set()
    for row in sorted(candidates, key=lambda item: (
        item["repository_url"], _configuration_neutral_xml_path(item["xml_path"]),
        item["line_number"], item["candidate_id"],
    )):
        if row.get("selection_status") != "candidate":
            continue
        attributes = _load_json_cell(row, "relevant_attributes")
        evidence_value = (
            attributes.get("labelFor")
            or attributes.get("importantForAccessibility")
            or attributes.get("focusable")
            or attributes.get("inputType")
            or ""
        )
        key = (
            normalize_repo_url(row.get("repository_url", "")),
            row.get("issue_type", ""), row.get("issue_subtype", ""),
            _configuration_neutral_xml_path(row.get("xml_path", "")),
            row.get("widget_id", ""), str(evidence_value),
        )
        if key in seen:
            row["selection_status"] = "excluded"
            row["notes"] = "; ".join(filter(None, (
                row.get("notes", ""),
                "duplicate defect in an Android layout configuration variant",
            )))
        else:
            seen.add(key)


def target_distribution(high: list[dict]) -> list[dict]:
    eligible = [row for row in high if row.get("selection_status") == "candidate"]
    rows = []
    for issue_type, requirement in TARGET_REQUIREMENTS.items():
        matches = [row for row in eligible if row["issue_type"] == issue_type]
        apps = {row["repository_url"] or row["package_name"] for row in matches}
        rows.append({
            "issue_type": issue_type,
            "new_high_xml_safe_count": len(matches),
            "new_app_count": len(apps),
            "required_new_instances": requirement["instances"],
            "required_new_apps": requirement["apps"],
            "instance_gap": max(requirement["instances"] - len(matches), 0),
            "app_gap": max(requirement["apps"] - len(apps), 0),
            "stop_condition_met": len(matches) >= requirement["instances"] and len(apps) >= requirement["apps"],
        })
    return rows


def stop_conditions_met(high: list[dict]) -> bool:
    return all(row["stop_condition_met"] for row in target_distribution(high))


def write_gap_outputs(output_root: Path, high: list[dict], review: list[dict], repositories: list[dict]) -> None:
    repositories_by_origin = {
        normalize_repo_url(row.get("repository_url", "")): Path(row["repository_path"])
        for row in repositories
        if row.get("repository_url") and row.get("repository_path")
    }
    for row in high + review:
        if int(row.get("line_number") or 0) > 0:
            continue
        repository = repositories_by_origin.get(normalize_repo_url(row.get("repository_url", "")))
        if repository:
            row["line_number"] = line_number_for(
                repository / row["xml_path"], row.get("widget_id", ""), row.get("widget_type", "")
            )
    distribution = target_distribution(high)
    gaps = [{
        "issue_type": row["issue_type"],
        "current_new_high": row["new_high_xml_safe_count"],
        "required_new_high": row["required_new_instances"],
        "remaining_issue_gap": row["instance_gap"],
        "current_new_apps": row["new_app_count"],
        "required_new_apps": row["required_new_apps"],
        "remaining_app_gap": row["app_gap"],
        "status": "met" if row["stop_condition_met"] else "below",
    } for row in distribution]
    write_csv(output_root / "high_confidence_candidates.csv", high, CANDIDATE_FIELDS)
    write_csv(output_root / "review_required_candidates.csv", review, CANDIDATE_FIELDS)
    write_csv(output_root / "repository_summary.csv", repositories, TARGET_REPOSITORY_FIELDS)
    write_csv(output_root / "issue_type_distribution.csv", distribution, list(distribution[0]))
    write_csv(output_root / "dataset_gap_report.csv", gaps, list(gaps[0]))


def render_report(
    output_root: Path,
    high: list[dict],
    review: list[dict],
    repositories: list[dict],
    formal_unchanged: bool,
    v1_unchanged: bool,
) -> None:
    distribution = target_distribution(high)
    skipped = [row for row in repositories if row.get("targeted_status", "").startswith("skipped")]
    scanned = [row for row in repositories if row.get("targeted_status") == "scanned"]
    log_records = []
    log_path = output_root / "scan_log.jsonl"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                log_records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    acquisitions = [row for row in log_records if row.get("stage") == "acquisition"]
    latest_acquisition = {}
    for row in acquisitions:
        latest_acquisition[normalize_repo_url(row.get("repository_url", ""))] = row
    acquisition_failures = [
        row for row in latest_acquisition.values() if row.get("status") == "failed"
    ]
    acquisition_successes = [
        row for row in latest_acquisition.values()
        if row.get("status") in {"cloned_sparse", "existing"}
    ]
    range_stop = len(repositories) >= 30 and not all(
        row["stop_condition_met"] for row in distribution
    )
    lines = [
        "# 长尾问题类型定向补齐报告",
        "",
        "## 执行摘要",
        "",
        f"- 新仓库处理数：{len(repositories)}",
        f"- 实际静态扫描数：{len(scanned)}",
        f"- 跳过数：{len(skipped)}",
        f"- 唯一远程仓库获取数：{len(latest_acquisition)}（历史尝试记录 {len(acquisitions)} 次）",
        f"- 远程获取成功：{len(acquisition_successes)}",
        f"- 当前获取失败：{len(acquisition_failures)}（不计入已处理仓库数）",
        f"- 新增 high-confidence XML-safe 候选：{sum(row['new_high_xml_safe_count'] for row in distribution)}",
        f"- review-required：{len(review)}",
        f"- 停止条件全部满足：{'是' if all(row['stop_condition_met'] for row in distribution) else '否'}",
        f"- 达到 30～50 个仓库不足即停止条件：{'是' if range_stop else '否'}",
        "- 付费模型调用：0",
        "- RAG/模型结果参与筛选：否",
        "- 原检测器规则修改：否；仅增加独立的定向证据复核层",
        f"- V1 哈希保持不变：{'是' if v1_unchanged else '否'}",
        f"- 原正式扫描目录哈希保持不变：{'是' if formal_unchanged else '否'}",
        "",
        "## 三类缺口",
        "",
        "| 类型 | 新增 high | 新 App | 目标 | 状态 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in distribution:
        target = f"{row['required_new_instances']} 条"
        if row["required_new_apps"]:
            target += f" / {row['required_new_apps']} App"
        lines.append(
            f"| {row['issue_type']} | {row['new_high_xml_safe_count']} | {row['new_app_count']} | {target} | "
            f"{'满足' if row['stop_condition_met'] else '不足'} |"
        )
    lines.extend(["", "## 跳过仓库", ""])
    if skipped:
        for row in skipped:
            lines.append(f"- `{row['app_name']}`：{row['skip_reason']}")
    else:
        lines.append("- 无。")
    lines.extend(["", "## 基础设施失败", ""])
    if acquisition_failures:
        lines.extend([
            f"- 当前仍有 {len(acquisition_failures)} 个唯一远程仓库在 Git 获取阶段失败，未下载源码、未进入静态扫描。",
            "- 失败原因保存在 `scan_log.jsonl`，不计入自然源码样本或已处理仓库数量。",
            "- 这些失败不属于 Compose、无 XML 或无目标证据，也不能用于判断自然缺陷是否不足。",
        ])
    else:
        lines.append("- 无。")
    lines.extend([
        "",
        "## 误报控制",
        "",
        "- 输入语义 high 必须由至少两种独立来源指向同一语义，且 inputType 明确不匹配；控件 ID 不计证据。",
        "- labelFor 缺失目标必须在 include 闭包完整解析后仍不存在；解析不完整即降级 review。",
        "- 属性冲突只保留交互控件显式隐藏或标准交互控件显式 focusable=false；父容器和运行时情况不计入 XML-safe high。",
        "- 触控目标继续保留为 review-required，没有为了补数量提升为 error。",
        "",
        (
            "本阶段已在 41 个成功取得源码的新仓库上完成轻量预筛或静态扫描。"
            "三类目标仍未全部满足，因此按预定停止条件结束，并如实记录自然高置信缺陷不足。"
            if range_stop else
            "尚未达到 30 个成功处理仓库，不能据此判断自然缺陷是否不足。"
        ),
        "",
        "候选集仍未冻结，也未执行 RAG/No-RAG。",
    ])
    (output_root / "TARGETED_GAP_FILL_REPORT_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_repository(repository: Path, metadata: dict) -> tuple[dict, list[dict], list[dict]]:
    metadata = dict(metadata)
    metadata["repository_status"] = "targeted_new_source"
    classification = classify_repository(repository, metadata.get("subdir", ""))
    markers = target_marker_counts(repository, metadata.get("subdir", ""))
    if not classification["layout_xml_count"]:
        summary = {
            "package_name": metadata.get("package_name", repository.name),
            "app_name": metadata.get("app_name", repository.name),
            "repository_url": metadata.get("repository_url", repository_origin(repository)),
            "repository_path": str(repository.resolve()),
            "commit_hash": metadata.get("commit_hash", ""),
            "subdir": metadata.get("subdir", ""),
            "repository_status": "targeted_new_source",
            **classification,
            "res_root_count": 0, "high_candidate_count": 0,
            "review_candidate_count": 0, "boundary_candidate_count": 0,
            "scan_seconds": 0, "scan_error": "",
            "targeted_status": "skipped_no_layout",
            "skip_reason": "Compose or no traditional layout XML in the F-Droid subdir",
            "target_marker_counts": json_cell(markers),
        }
        return summary, [], []
    if not has_target_markers(markers):
        summary = {
            "package_name": metadata.get("package_name", repository.name),
            "app_name": metadata.get("app_name", repository.name),
            "repository_url": metadata.get("repository_url", repository_origin(repository)),
            "repository_path": str(repository.resolve()),
            "commit_hash": metadata.get("commit_hash", ""),
            "subdir": metadata.get("subdir", ""),
            "repository_status": "targeted_new_source",
            **classification,
            "res_root_count": 0, "high_candidate_count": 0,
            "review_candidate_count": 0, "boundary_candidate_count": 0,
            "scan_seconds": 0, "scan_error": "",
            "targeted_status": "skipped_no_target_evidence",
            "skip_reason": "layout XML has no target attribute markers",
            "target_marker_counts": json_cell(markers),
        }
        return summary, [], []
    summary, candidates, _ = scan_repository(repository, metadata=metadata)
    high, review = validate_target_candidates(repository, metadata, candidates)
    summary.update(
        high_candidate_count=len(high), review_candidate_count=len(review),
        boundary_candidate_count=0, targeted_status="scanned", skip_reason="",
        target_marker_counts=json_cell(markers),
    )
    return summary, high, review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-inventory", type=Path, default=ROOT / "outputs/source_prescreen/formal_scan_v2/fdroid_metadata_inventory.csv")
    parser.add_argument("--formal-root", type=Path, default=ROOT / "outputs/source_prescreen/formal_scan_v2")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/source_prescreen/targeted_gap_fill")
    parser.add_argument("--local-root", type=Path)
    parser.add_argument("--repository-names", default="")
    parser.add_argument("--clone-root", type=Path)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--max-repositories", type=int, default=45)
    parser.add_argument("--execute-acquisition", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20:
        raise ValueError("batch-size must be between 1 and 20")
    if not 1 <= args.max_repositories <= 50:
        raise ValueError("max-repositories must be between 1 and 50")
    output_root = args.output_root.resolve()
    ensure_output_is_v2(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    clone_root = (args.clone_root or output_root / "repositories").resolve()

    formal_before = tree_snapshot(args.formal_root.resolve())
    v1_before = v1_current_snapshot()
    formal_rows = read_rows(args.formal_root / "repository_summary.csv")
    excluded = {normalize_repo_url(row["repository_url"]) for row in formal_rows if row.get("repository_url")}
    metadata_rows = read_rows(args.metadata_inventory)
    metadata_map = metadata_by_origin(metadata_rows)
    existing_high = read_csv(output_root / "high_confidence_candidates.csv") if args.resume else []
    existing_review = read_csv(output_root / "review_required_candidates.csv") if args.resume else []
    repositories = read_csv(output_root / "repository_summary.csv") if args.resume else []
    attempted = {normalize_repo_url(row.get("repository_url", "")) for row in repositories}
    log_path = output_root / "scan_log.jsonl"
    if not args.resume:
        log_path.write_text("", encoding="utf-8")

    selected: list[tuple[Path, dict]] = []
    if args.local_root:
        names = {item.strip().casefold() for item in args.repository_names.split(",") if item.strip()} or None
        selected = discover_new_local_repositories(args.local_root, excluded | attempted, metadata_map, names)
        selected = selected[:args.batch_size]
    elif args.execute_acquisition:
        candidates = unique_new_metadata(metadata_rows, excluded | attempted)
        candidates = candidates[:args.max_repositories]
        acquisition_index = 0
        for offset in range(0, len(candidates), args.batch_size):
            if stop_conditions_met(existing_high):
                break
            batch = candidates[offset:offset + args.batch_size]
            batch_number = offset // args.batch_size + 1
            print(f"[batch {batch_number}] acquisition candidates: {len(batch)}", flush=True)
            for metadata in batch:
                acquisition_index += 1
                result = clone_one(metadata, clone_root, depth=1, timeout=300)
                print(
                    f"[{acquisition_index}/{len(candidates)}] acquire "
                    f"{metadata['repository_url']}: {result['status']}",
                    flush=True,
                )
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"stage": "acquisition", **result, "paid_api_used": False}, ensure_ascii=False) + "\n")
                if result["status"] in {"cloned_sparse", "existing"}:
                    selected.append((Path(result["local_path"]), metadata))
            for repository, metadata in selected:
                if normalize_repo_url(metadata["repository_url"]) in attempted:
                    continue
                summary, high, review = process_repository(repository, metadata)
                print(
                    f"  scan {summary['app_name']}: {summary['targeted_status']}, "
                    f"high={len(high)}, review={len(review)}",
                    flush=True,
                )
                repositories.append(summary)
                existing_high = merge_by_id(existing_high, high)
                existing_review = merge_by_id(existing_review, review)
                attempted.add(normalize_repo_url(metadata["repository_url"]))
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "stage": "scan", "app_name": summary["app_name"],
                        "repository_url": summary["repository_url"],
                        "status": summary["targeted_status"], "new_high": len(high),
                        "review": len(review), "paid_api_used": False,
                        "model_outputs_used": False,
                    }, ensure_ascii=False) + "\n")
            selected = []
            existing_high, existing_review = enforce_high_contract(existing_high, existing_review)
            mark_configuration_variant_duplicates(existing_high)
            cap_per_app_type(existing_high, 4)
            write_gap_outputs(output_root, existing_high, existing_review, repositories)
            batch_distribution = target_distribution(existing_high)
            print(
                "  gaps: " + ", ".join(
                    f"{row['issue_type']}={row['instance_gap']}"
                    for row in batch_distribution
                ),
                flush=True,
            )
            if stop_conditions_met(existing_high):
                break
    else:
        plan = unique_new_metadata(metadata_rows, excluded | attempted)[:args.batch_size]
        print(json.dumps({
            "mode": "dry_run", "network_used": False,
            "selected_repositories": len(plan),
            "selection_uses_app_name_or_description": False,
            "repositories": [{
                "repository_url": row["repository_url"],
                "commit_hash": row["commit_hash"], "subdir": row["subdir"],
            } for row in plan],
        }, ensure_ascii=False, indent=2))
        return

    if args.local_root:
        for repository, metadata in selected:
            summary, high, review = process_repository(repository, metadata)
            repositories.append(summary)
            existing_high = merge_by_id(existing_high, high)
            existing_review = merge_by_id(existing_review, review)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "stage": "scan", "app_name": summary["app_name"],
                    "repository_url": summary["repository_url"],
                    "status": summary["targeted_status"], "new_high": len(high),
                    "review": len(review), "paid_api_used": False,
                    "model_outputs_used": False,
                }, ensure_ascii=False) + "\n")
        existing_high, existing_review = enforce_high_contract(existing_high, existing_review)
        mark_configuration_variant_duplicates(existing_high)
        cap_per_app_type(existing_high, 4)
        write_gap_outputs(output_root, existing_high, existing_review, repositories)

    formal_after = tree_snapshot(args.formal_root.resolve())
    v1_after = v1_current_snapshot()
    formal_unchanged = formal_before == formal_after
    v1_unchanged = {
        row["path"]: row["current_sha256"] for row in v1_before["records"]
    } == {
        row["path"]: row["current_sha256"] for row in v1_after["records"]
    }
    integrity = {
        "formal_scan_unchanged": formal_unchanged,
        "v1_unchanged": v1_unchanged,
        "formal_file_count": len(formal_before),
        "v1_preexisting_mismatch_count": v1_before["preexisting_mismatch_count"],
    }
    (output_root / "integrity_check.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    if not formal_unchanged or not v1_unchanged:
        raise RuntimeError("protected V1 or formal scan results changed")
    render_report(output_root, existing_high, existing_review, repositories, formal_unchanged, v1_unchanged)
    print(json.dumps({
        "processed_new_repositories": len(repositories),
        "new_high_eligible": sum(row.get("selection_status") == "candidate" for row in existing_high),
        "review_required": len(existing_review),
        "stop_conditions_met": stop_conditions_met(existing_high),
        "distribution": target_distribution(existing_high),
        "output": str(output_root),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
