#!/usr/bin/env python3
"""Scan Android source XML and emit evidence-grounded V2 candidates."""
from __future__ import annotations

import argparse
import configparser
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.common import (  # noqa: E402
    CANDIDATE_FIELDS,
    bool_cell,
    json_cell,
    normalize_repo_url,
    sha256_text,
    write_csv,
)
from scripts.source_prescreen.resolve_android_resources import (  # noqa: E402
    AndroidResourceResolver,
    canonical_layout_signature,
    discover_layout_files,
    line_number_for,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    ANDROID_NS,
    EMAIL_TERMS,
    GENERIC_LABELS,
    NUMBER_TERMS,
    PASSWORD_TERMS,
    PHONE_TERMS,
    SPECIFIC_NUMBER_TERMS,
    STATEFUL_CONTROL_TAGS,
    TOOLS_NS,
    all_attrs,
    apply_explicit_styles,
    attr,
    build_label_map,
    build_parent_map,
    build_stack,
    check_tree,
    collect_xml_files,
    element_path,
    has_any_term,
    is_custom_view,
    is_editable_input,
    is_image_widget,
    is_interactive,
    is_empty_value,
    load_color_resources,
    load_dimension_resources,
    load_string_resources,
    load_style_resources,
    normalize_view_type,
    parse_id,
    resolve_string,
    scan,
    strip_ns,
    text_input_layout_hint,
)


REPOSITORY_FIELDS = (
    "package_name", "app_name", "repository_url", "repository_path",
    "commit_hash", "subdir", "repository_status", "layout_xml_count",
    "res_root_count", "compose_evidence", "hybrid_xml_compose",
    "source_classification", "high_candidate_count", "review_candidate_count",
    "boundary_candidate_count", "scan_seconds", "scan_error",
)

XML_FIELDS = (
    "package_name", "app_name", "repository_url", "xml_path", "layout_name",
    "dedup_group", "root_tag", "included_by", "high_candidate_count",
    "review_candidate_count", "boundary_candidate_count",
)

CODE_CLASSIFICATION = {
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME": ("accessible_name_missing", "interactive_control_missing_name", "easy"),
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME": ("accessible_name_missing", "image_button_missing_name", "easy"),
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME": ("accessible_name_missing", "button_missing_name", "easy"),
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME": ("accessible_name_missing", "clickable_image_missing_name", "medium"),
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME": ("accessible_name_missing", "custom_clickable_missing_name", "medium"),
    "PRESCREEN_INTERACTIVE_IMAGE_EMPTY_NAME": ("accessible_name_missing", "interactive_image_empty_description", "medium"),
    "ANDROID_XML_REPEATED_GENERIC_LABEL": ("accessible_name_quality", "repeated_generic_name", "hard"),
    "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION": ("accessible_name_quality", "meaningful_image_requires_description_review", "boundary"),
    "PRESCREEN_GENERIC_ACCESSIBLE_NAME": ("accessible_name_quality", "generic_interactive_name", "hard"),
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT": ("input_label_hint", "input_missing_label_and_hint", "medium"),
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": ("input_label_hint", "weak_input_label_or_hint", "hard"),
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": ("input_type_semantics", "password_input_type_missing", "hard"),
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": ("input_type_semantics", "email_input_type_missing", "hard"),
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": ("input_type_semantics", "phone_input_type_missing", "hard"),
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": ("input_type_semantics", "number_input_type_missing", "hard"),
    "PRESCREEN_INPUT_TYPE_SEMANTIC_CONFLICT": ("input_type_semantics", "input_type_conflicts_with_label", "hard"),
    "ANDROID_XML_LABELFOR_TARGET_MISSING": ("label_association", "label_for_target_missing", "medium"),
    "ANDROID_XML_LABELFOR_TARGET_NOT_INPUT": ("label_association", "label_for_target_requires_review", "boundary"),
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": ("focus_accessibility_tree", "interactive_control_not_focusable", "hard"),
    "ANDROID_XML_UNNAMED_FOCUSABLE_CONTAINER": ("focus_accessibility_tree", "unnamed_focusable_container", "boundary"),
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL": ("stateful_dynamic_value", "stateful_control_missing_label", "medium"),
    "PRESCREEN_STATEFUL_STATIC_DESCRIPTION": ("stateful_dynamic_value", "static_description_may_mask_state", "boundary"),
    "ANDROID_XML_TOUCH_TARGET_TOO_SMALL": ("touch_target_size", "explicit_touch_target_below_48dp", "medium"),
    "ANDROID_XML_TOUCH_TARGET_DIMEN_UNRESOLVED": ("touch_target_size", "touch_target_dimension_unresolved", "boundary"),
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY": ("accessibility_attribute_conflict", "interactive_control_hidden", "hard"),
    "ANDROID_XML_INTERACTIVE_HIDDEN_BY_PARENT": ("accessibility_attribute_conflict", "interactive_child_hidden_by_parent", "boundary"),
    "ANDROID_XML_IMAGE_SEMANTICS_REQUIRES_REVIEW": ("static_xml_boundary", "image_semantics_runtime_or_visual_context", "boundary"),
    "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW": ("static_xml_boundary", "custom_view_runtime_semantics", "boundary"),
    "ANDROID_XML_PROGRESS_MISSING_STATUS_LABEL": ("static_xml_boundary", "dynamic_progress_status", "boundary"),
    "ANDROID_XML_NON_SEMANTIC_CLICKABLE": ("static_xml_boundary", "nonsemantic_clickable_requires_structure_or_code", "boundary"),
}

FORCED_RUNTIME_CODES = {
    "ANDROID_XML_INTERACTIVE_HIDDEN_BY_PARENT",
    "ANDROID_XML_IMAGE_SEMANTICS_REQUIRES_REVIEW",
    "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW",
    "ANDROID_XML_PROGRESS_MISSING_STATUS_LABEL",
    "ANDROID_XML_NON_SEMANTIC_CLICKABLE",
    "PRESCREEN_STATEFUL_STATIC_DESCRIPTION",
}

RELEVANT_RESOURCE_ATTRIBUTES = {
    "accessible_name_missing": {"text", "hint", "contentDescription", "style", "labelFor", "id"},
    "accessible_name_quality": {"text", "contentDescription", "style", "src", "srcCompat"},
    "input_label_hint": {"hint", "contentDescription", "style", "labelFor", "id"},
    "input_type_semantics": {"hint", "contentDescription", "style", "labelFor", "id", "inputType"},
    "label_association": {"text", "contentDescription", "style", "labelFor", "id"},
    "focus_accessibility_tree": {"style"},
    "stateful_dynamic_value": {"text", "hint", "contentDescription", "style", "labelFor", "id"},
    "touch_target_size": {"layout_width", "layout_height", "minWidth", "minHeight", "padding", "style"},
    "accessibility_attribute_conflict": {"style"},
    "static_xml_boundary": {"style"},
}


def git_value(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def repository_origin(repository: Path) -> str:
    config = configparser.RawConfigParser()
    try:
        config.read(repository / ".git" / "config", encoding="utf-8")
        return config.get('remote "origin"', "url", fallback="")
    except (configparser.Error, OSError):
        return ""


def has_compose_evidence(repository: Path, file_limit: int = 5000) -> bool:
    suffixes = {".kt", ".gradle", ".kts", ".toml"}
    patterns = (
        "androidx.compose",
        "buildFeatures { compose",
        "compose = true",
        "compose=true",
    )
    checked = 0
    for path in repository.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in {".git", ".gradle", "build", "node_modules"} for part in path.parts):
            continue
        checked += 1
        if checked > file_limit:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(pattern in text for pattern in patterns):
            return True
    return False


def classify_repository(repository: Path, subdir: str = "", compose_file_limit: int = 5000) -> dict:
    layouts = discover_layout_files(repository, subdir)
    compose = has_compose_evidence(repository, compose_file_limit)
    if layouts:
        classification = "traditional_xml"
    elif compose:
        classification = "compose_without_layout"
    else:
        classification = "no_usable_layout"
    return {
        "layout_xml_count": len(layouts),
        "compose_evidence": compose,
        "hybrid_xml_compose": bool(layouts and compose),
        "source_classification": classification,
    }


def confidence_label(score: float, high_min: float = 0.8, medium_min: float = 0.5) -> str:
    if score >= high_min:
        return "high"
    if score >= medium_min:
        return "medium"
    return "low"


def _issue(
    path: Path,
    root: ET.Element,
    parent_map: dict,
    element: ET.Element,
    code: str,
    severity: str,
    confidence: float,
    message: str,
    repairability: str,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "confidence": confidence,
        "requires_review": severity != "error" or repairability != "xml_safe",
        "repairability": repairability,
        "file": str(path),
        "element": strip_ns(element.tag),
        "component": normalize_view_type(element.tag),
        "selector": element_path(build_stack(element, parent_map)),
        "attributes": all_attrs(element),
        "message": message,
        "prescreen_rule": True,
    }


def _resolved_element_name(element: ET.Element, resolver: AndroidResourceResolver, label_map: dict, parent_map: dict) -> str:
    values = [
        attr(element, "hint"),
        label_map.get(parse_id(attr(element, "id")) or ""),
        text_input_layout_hint(element, parent_map),
        attr(element, "contentDescription"),
    ]
    return " ".join(
        resolve_string(value, resolver.strings)
        for value in values
        if value and not is_empty_value(value)
    ).strip()


def supplementary_issues(path: Path, resolver: AndroidResourceResolver) -> list[dict]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []
    apply_explicit_styles(root, resolver.styles)
    parent_map = build_parent_map(root)
    label_map = build_label_map(root, resolver.strings)
    issues = []
    for element in root.iter():
        tools_ignore = attr(element, "ignore", TOOLS_NS) or ""
        important = attr(element, "importantForAccessibility") or ""
        description = attr(element, "contentDescription")
        if (
            is_image_widget(element)
            and is_interactive(element)
            and description is not None
            and is_empty_value(description)
            and important not in {"no", "noHideDescendants"}
            and "contentdescription" not in {part.strip().casefold() for part in tools_ignore.split(",")}
        ):
            issues.append(_issue(
                path, root, parent_map, element,
                "PRESCREEN_INTERACTIVE_IMAGE_EMPTY_NAME", "error", 0.95,
                "交互图片显式使用空 contentDescription，源码中没有可供辅助技术使用的名称。",
                "xml_safe",
            ))

        if is_interactive(element) and description and not is_empty_value(description):
            resolved = resolve_string(description, resolver.strings).strip().casefold()
            if resolved in GENERIC_LABELS:
                issues.append(_issue(
                    path, root, parent_map, element,
                    "PRESCREEN_GENERIC_ACCESSIBLE_NAME", "warning", 0.7,
                    f"交互控件使用空泛的可访问名称 {resolved!r}，需要结合具体功能人工复核。",
                    "manual_review",
                ))

        tag = strip_ns(element.tag)
        if any(tag == stateful or tag.endswith(stateful) for stateful in STATEFUL_CONTROL_TAGS):
            if description and not is_empty_value(description):
                issues.append(_issue(
                    path, root, parent_map, element,
                    "PRESCREEN_STATEFUL_STATIC_DESCRIPTION", "warning", 0.65,
                    "有状态或动态值控件使用固定 contentDescription，可能遮蔽当前状态或数值。",
                    "requires_structure_or_code",
                ))

        if is_editable_input(element):
            evidence = _resolved_element_name(element, resolver, label_map, parent_map)
            input_type = (attr(element, "inputType") or "").casefold()
            if not evidence or not input_type or is_custom_view(element):
                continue
            expected = ""
            conflicting = False
            if has_any_term(evidence, EMAIL_TERMS):
                expected = "textEmailAddress"
                conflicting = any(token in input_type for token in ("phone", "password", "number"))
            elif has_any_term(evidence, PHONE_TERMS):
                expected = "phone"
                conflicting = any(token in input_type for token in ("email", "password"))
            elif has_any_term(evidence, PASSWORD_TERMS):
                expected = "password"
                conflicting = "password" not in input_type
            elif has_any_term(evidence, SPECIFIC_NUMBER_TERMS):
                expected = "number or numberDecimal"
                conflicting = any(token in input_type for token in ("email", "phone", "password"))
            if expected and conflicting:
                issues.append(_issue(
                    path, root, parent_map, element,
                    "PRESCREEN_INPUT_TYPE_SEMANTIC_CONFLICT", "error", 0.9,
                    f"可解析标签或 hint 表明字段需要 {expected}，但当前 inputType={input_type!r}。",
                    "xml_safe",
                ))
    return issues


def scan_res_root_isolated(res_root: Path, detector_profile: str) -> tuple[list[dict], list[str]]:
    """Run the shared detector while isolating one malformed or unsupported layout."""
    resources = load_string_resources([res_root])
    colors = load_color_resources([res_root])
    dimensions = load_dimension_resources([res_root])
    styles = load_style_resources([res_root])
    issues = []
    errors = []
    for path in collect_xml_files([res_root]):
        try:
            root = ET.parse(path).getroot()
            apply_explicit_styles(root, styles)
            issues.extend(check_tree(
                path,
                root,
                resources,
                colors,
                dimensions,
                styles,
                detector_profile=detector_profile,
            ))
        except (ET.ParseError, OSError, TypeError, ValueError) as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    return issues, errors


def issue_to_candidate(
    issue: dict,
    metadata: dict,
    repository: Path,
    resolver: AndroidResourceResolver,
    high_min: float,
    medium_min: float,
) -> dict | None:
    code = issue.get("code", "")
    if code not in CODE_CLASSIFICATION:
        return None
    xml_path = Path(issue.get("file", ""))
    if not xml_path.exists():
        return None
    issue_type, subtype, default_difficulty = CODE_CLASSIFICATION[code]
    attributes = issue.get("attributes") or {}
    resolved_values, unresolved = resolver.resolve_attributes(attributes)
    if code == "ANDROID_XML_LABELFOR_TARGET_MISSING":
        unresolved = [
            value for value in unresolved
            if not value.startswith("labelFor=")
        ]
    relevant_attributes = RELEVANT_RESOURCE_ATTRIBUTES[issue_type]
    unresolved = [
        value for value in unresolved
        if value.split("=", 1)[0] in relevant_attributes
    ]
    score = float(issue.get("confidence", 0.35))
    severity = issue.get("severity", "error")
    repairability = issue.get("repairability", "manual_review")
    runtime_required = code in FORCED_RUNTIME_CODES or repairability in {
        "requires_structure_or_code", "runtime_required",
    }
    xml_safe = repairability == "xml_safe" and not runtime_required
    notes = []
    if issue.get("prescreen_rule"):
        notes.append("V2-only source prescreen rule; compare with frozen V1 detector before experiment integration")
    if unresolved:
        notes.append("unresolved resources: " + "; ".join(unresolved))
        score = min(score, 0.79)
        severity = "warning"
        xml_safe = False
    if code == "ANDROID_XML_INTERACTIVE_HIDDEN_BY_PARENT":
        notes.append("parent-level repair may affect multiple descendants")
    confidence = confidence_label(score, high_min, medium_min)
    difficulty = "boundary" if runtime_required or default_difficulty == "boundary" else default_difficulty
    relative = xml_path.resolve().relative_to(repository.resolve()).as_posix()
    widget_id = attributes.get("id", "")
    commit_hash = metadata.get("scanned_commit") or git_value(repository, "rev-parse", "HEAD")
    candidate_key = "|".join([
        normalize_repo_url(metadata.get("repository_url", "")),
        commit_hash,
        relative,
        code,
        issue.get("selector", ""),
    ])
    context = resolver.context_for(xml_path, issue.get("selector", ""))
    selection_status = (
        "candidate"
        if (confidence == "high" and severity == "error" and xml_safe) or difficulty == "boundary"
        else "excluded"
    )
    return {
        "candidate_id": "src-" + sha256_text(candidate_key)[:20],
        "package_name": metadata.get("package_name", repository.name),
        "app_name": metadata.get("app_name", repository.name),
        "repository_url": metadata.get("repository_url", repository_origin(repository)),
        "repo_type": metadata.get("repo_type", "git"),
        "commit_hash": commit_hash,
        "subdir": metadata.get("subdir", ""),
        "xml_path": relative,
        "line_number": line_number_for(xml_path, widget_id, issue.get("element", "")),
        "widget_type": issue.get("element") or issue.get("component", ""),
        "widget_id": widget_id,
        "issue_type": issue_type,
        "issue_subtype": subtype,
        "severity": severity,
        "confidence": confidence,
        "difficulty": difficulty,
        "xml_safe": bool_cell(xml_safe),
        "runtime_required": bool_cell(runtime_required),
        "evidence": issue.get("message", ""),
        "relevant_attributes": json_cell(attributes),
        "resolved_resource_values": json_cell(resolved_values),
        "parent_context": json_cell(context),
        "screen_or_layout_name": xml_path.stem,
        "repository_status": metadata.get("repository_status", "existing_local"),
        "source_type": "natural_source_issue",
        "dedup_group": canonical_layout_signature(xml_path),
        "manual_review_status": "pending",
        "selection_status": selection_status,
        "dataset_split": "unassigned",
        "notes": "; ".join(notes),
    }


def scan_repository(
    repository: Path,
    metadata: dict | None = None,
    detector_profile: str = "expanded_v3",
    high_min: float = 0.8,
    medium_min: float = 0.5,
    compose_file_limit: int = 5000,
) -> tuple[dict, list[dict], list[dict]]:
    started = time.monotonic()
    repository = repository.resolve()
    metadata = dict(metadata or {})
    metadata.setdefault("app_name", repository.name)
    metadata.setdefault("package_name", repository.name)
    metadata.setdefault("repository_url", repository_origin(repository))
    metadata.setdefault("repo_type", "git")
    metadata.setdefault("subdir", "")
    metadata.setdefault("repository_status", "existing_local")
    metadata["scanned_commit"] = git_value(repository, "rev-parse", "HEAD")
    classification = classify_repository(repository, metadata["subdir"], compose_file_limit)
    summary = {
        "package_name": metadata["package_name"],
        "app_name": metadata["app_name"],
        "repository_url": metadata["repository_url"],
        "repository_path": str(repository),
        "commit_hash": metadata["scanned_commit"],
        "subdir": metadata["subdir"],
        "repository_status": metadata["repository_status"],
        **classification,
        "res_root_count": 0,
        "high_candidate_count": 0,
        "review_candidate_count": 0,
        "boundary_candidate_count": 0,
        "scan_seconds": 0.0,
        "scan_error": "",
    }
    if not classification["layout_xml_count"]:
        summary["scan_seconds"] = round(time.monotonic() - started, 4)
        return summary, [], []
    resolver = AndroidResourceResolver(repository, metadata["subdir"])
    summary["res_root_count"] = len(resolver.res_roots)
    raw_issues = []
    scan_errors = []
    for res_root in resolver.res_roots:
        root_issues, root_errors = scan_res_root_isolated(res_root, detector_profile)
        raw_issues.extend(root_issues)
        scan_errors.extend(root_errors)
    for layout in discover_layout_files(repository, metadata["subdir"]):
        try:
            raw_issues.extend(supplementary_issues(layout, resolver))
        except (ET.ParseError, OSError, TypeError, ValueError) as exc:
            scan_errors.append(f"{layout}: {type(exc).__name__}: {exc}")
    summary["scan_error"] = " | ".join(scan_errors[:20])
    candidates = []
    seen = set()
    for issue in raw_issues:
        candidate = issue_to_candidate(
            issue, metadata, repository, resolver, high_min, medium_min
        )
        if candidate and candidate["candidate_id"] not in seen:
            candidates.append(candidate)
            seen.add(candidate["candidate_id"])
    candidates.sort(key=lambda row: (row["xml_path"], row["line_number"], row["issue_subtype"], row["candidate_id"]))
    high = [row for row in candidates if row["confidence"] == "high" and row["severity"] == "error" and row["xml_safe"] == "true"]
    boundary = [row for row in candidates if row["difficulty"] == "boundary" or row["runtime_required"] == "true"]
    review = [row for row in candidates if row not in high and row not in boundary]
    summary["high_candidate_count"] = len(high)
    summary["review_candidate_count"] = len(review)
    summary["boundary_candidate_count"] = len(boundary)
    summary["scan_seconds"] = round(time.monotonic() - started, 4)

    xml_rows = []
    by_xml = defaultdict(list)
    for row in candidates:
        by_xml[row["xml_path"]].append(row)
    for layout in discover_layout_files(repository, metadata["subdir"]):
        relative = layout.relative_to(repository).as_posix()
        rows = by_xml.get(relative, [])
        context = resolver.context_for(layout, "")
        xml_rows.append({
            "package_name": metadata["package_name"],
            "app_name": metadata["app_name"],
            "repository_url": metadata["repository_url"],
            "xml_path": relative,
            "layout_name": layout.stem,
            "dedup_group": canonical_layout_signature(layout),
            "root_tag": context["root_tag"],
            "included_by": json_cell(context["included_by"]),
            "high_candidate_count": sum(row in high for row in rows),
            "review_candidate_count": sum(row in review for row in rows),
            "boundary_candidate_count": sum(row in boundary for row in rows),
        })
    return summary, candidates, xml_rows


def metadata_by_origin(rows: list[dict]) -> dict[str, dict]:
    return {
        normalize_repo_url(row.get("repository_url", "")): row
        for row in rows
        if row.get("repository_url")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--repository-root", type=Path, required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)
    inventory_parser.add_argument("--compose-file-limit", type=int, default=5000)
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("repository", type=Path)
    scan_parser.add_argument("--output", type=Path, required=True)
    scan_parser.add_argument("--detector-profile", default="expanded_v3")
    args = parser.parse_args()

    if args.command == "inventory":
        rows = []
        for repository in sorted(args.repository_root.glob("*")):
            if not repository.is_dir() or not (repository / ".git").exists():
                continue
            classification = classify_repository(repository, compose_file_limit=args.compose_file_limit)
            rows.append({
                "package_name": repository.name,
                "app_name": repository.name,
                "repository_url": repository_origin(repository),
                "repository_path": str(repository.resolve()),
                "commit_hash": git_value(repository, "rev-parse", "HEAD"),
                "subdir": "",
                "repository_status": "existing_local",
                **classification,
                "res_root_count": len({path.parent.parent for path in discover_layout_files(repository)}),
                "high_candidate_count": 0,
                "review_candidate_count": 0,
                "boundary_candidate_count": 0,
                "scan_seconds": 0,
                "scan_error": "",
            })
        write_csv(args.output, rows, REPOSITORY_FIELDS)
        counts = Counter(row["source_classification"] for row in rows)
        print(json.dumps({
            "repositories": len(rows),
            "traditional_xml": counts["traditional_xml"],
            "compose_without_layout": counts["compose_without_layout"],
            "no_usable_layout": counts["no_usable_layout"],
            "hybrid_xml_compose": sum(row["hybrid_xml_compose"] for row in rows),
            "output": str(args.output.resolve()),
        }, ensure_ascii=False, indent=2))
        return

    summary, candidates, xml_rows = scan_repository(
        args.repository,
        detector_profile=args.detector_profile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "repository": summary,
        "candidates": candidates,
        "xml": xml_rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "repository": summary["app_name"],
        "high": summary["high_candidate_count"],
        "review": summary["review_candidate_count"],
        "boundary": summary["boundary_candidate_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
