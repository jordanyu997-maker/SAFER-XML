#!/usr/bin/env python3
"""Build, validate, split, and conditionally freeze the Android XML V2 dataset."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.build_candidate_manifest import (  # noqa: E402
    sha256_file,
    snapshots_equal,
    v1_current_snapshot,
)
from scripts.source_prescreen.common import (  # noqa: E402
    CANDIDATE_FIELDS,
    ensure_output_is_v2,
    normalize_repo_url,
    read_csv,
    sha256_text,
    write_csv,
)
from scripts.source_prescreen.resolve_android_resources import (  # noqa: E402
    AndroidResourceResolver,
    canonical_layout_signature,
    line_number_for,
)
from scripts.source_prescreen.run_targeted_gap_fill import (  # noqa: E402
    validate_attribute_conflict,
    validate_input_semantics,
    validate_label_association,
)
from scripts.source_prescreen.scan_android_xml import (  # noqa: E402
    RELEVANT_RESOURCE_ATTRIBUTES,
    git_value,
    scan_repository,
)
from scripts.source_prescreen.split_dataset_by_app import (  # noqa: E402
    assert_no_split_leakage,
    repository_key,
    split_by_repository,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    all_attrs,
    apply_explicit_styles,
    build_parent_map,
    build_stack,
    element_path,
    normalize_view_type,
    parse_id,
    strip_ns,
)


VERSION = "v2.0.0"
DEFAULT_SEED = "android-xml-v2.0.0-fixed-seed"
FORMAL_ROOT = ROOT / "outputs/source_prescreen/formal_scan_v2"
TARGETED_ROOT = ROOT / "outputs/source_prescreen/targeted_gap_fill"
DEFAULT_OUTPUT_ROOT = ROOT / f"outputs/v2_dataset/{VERSION}"

PRIMARY_TYPES = (
    "accessible_name_missing",
    "accessible_name_quality",
    "input_label_hint",
    "focus_accessibility_tree",
    "stateful_dynamic_value",
    "static_xml_boundary",
)
LONG_TAIL_TYPES = (
    "input_type_semantics",
    "label_association",
    "accessibility_attribute_conflict",
)
EXCLUDED_TYPES = {"touch_target_size"}

# Three abundant XML-safe classes use 31 rather than 30 instances. With only
# nine XML-safe focus findings and 18 audited long-tail findings, this is the
# smallest deterministic allocation that reaches the hard minimum of 120.
TYPE_QUOTAS = {
    "accessible_name_missing": 31,
    "accessible_name_quality": 15,
    "input_label_hint": 31,
    "focus_accessibility_tree": 15,
    "stateful_dynamic_value": 31,
    "static_xml_boundary": 15,
}

V2_EXTRA_FIELDS = (
    "source_dataset",
    "candidate_role",
    "exploratory_long_tail",
    "source_severity",
    "source_confidence",
    "source_xml_safe",
    "source_runtime_required",
    "repository_path",
    "normalized_xml_path",
    "source_file_sha256",
    "commit_file_sha256",
    "relocated_line_number",
    "normalized_widget_type",
    "consistency_status",
    "frozen_dataset_version",
    "exclusion_reason",
)
V2_FIELDS = CANDIDATE_FIELDS + V2_EXTRA_FIELDS

CONSISTENCY_FIELDS = (
    "candidate_id",
    "source_dataset",
    "candidate_role",
    "app_name",
    "repository_url",
    "repository_path",
    "xml_path",
    "expected_commit",
    "actual_commit",
    "source_file_sha256",
    "commit_file_sha256",
    "original_line_number",
    "relocated_line_number",
    "node_relocated",
    "widget_id_matches",
    "widget_type_matches",
    "attributes_match",
    "resources_match",
    "layout_signature_matches",
    "candidate_contract_matches",
    "trigger_revalidated",
    "status",
    "reasons",
)


def truth(value: object) -> bool:
    return str(value).strip().casefold() == "true"


def stable_key(row: dict, seed: str) -> str:
    material = "|".join((
        seed,
        repository_key(row),
        row.get("xml_path", ""),
        row.get("issue_type", ""),
        row.get("issue_subtype", ""),
        row.get("candidate_id", ""),
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def json_dict(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalized_xml_path(value: str) -> str:
    """Collapse Android layout qualifiers while preserving the module path."""
    return "/".join(
        "layout" if part == "layout" or part.startswith("layout-") else part
        for part in Path(value).parts
    )


def strict_layout_fingerprint(path: Path) -> str:
    """Hash parsed XML without erasing resource names or IDs."""
    root = ET.parse(path).getroot()

    def visit(element: ET.Element):
        attrs = sorted((strip_ns(key), value.strip()) for key, value in element.attrib.items())
        text = (element.text or "").strip()
        return [strip_ns(element.tag), attrs, text, [visit(child) for child in element]]

    payload = json.dumps(visit(root), ensure_ascii=True, separators=(",", ":"))
    return sha256_text(payload)


def files_snapshot(paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path) if path.exists() else "missing"
        for path in paths
    }


def repository_maps(source_root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    by_url: dict[str, dict] = {}
    by_package: dict[str, dict] = {}
    for row in read_csv(source_root / "repository_summary.csv"):
        prepared = dict(row)
        prepared["source_root"] = source_root.name
        if row.get("repository_url"):
            by_url[normalize_repo_url(row["repository_url"])] = prepared
        if row.get("package_name"):
            by_package[row["package_name"].casefold()] = prepared
    return by_url, by_package


def load_candidate_pool() -> tuple[list[dict], list[dict], dict[tuple[str, str], dict]]:
    """Load only eligible formal and audited targeted rows."""
    pool: list[dict] = []
    exclusions: list[dict] = []
    repository_index: dict[tuple[str, str], dict] = {}
    sources = (
        (FORMAL_ROOT, "formal_scan_162"),
        (TARGETED_ROOT, "targeted_gap_fill_audited"),
    )
    for source_root, source_name in sources:
        by_url, by_package = repository_maps(source_root)
        for key, value in by_url.items():
            repository_index[(source_name, key)] = value
        for key, value in by_package.items():
            repository_index[(source_name, "package:" + key)] = value
        for filename, role in (
            ("high_confidence_candidates.csv", "xml_safe"),
            ("boundary_candidates.csv", "boundary"),
        ):
            path = source_root / filename
            if not path.exists():
                continue
            for original in read_csv(path):
                row = dict(original)
                row.update(
                    source_dataset=source_name,
                    candidate_role=role,
                    exploratory_long_tail=str(row.get("issue_type") in LONG_TAIL_TYPES).lower(),
                    source_severity=row.get("severity", ""),
                    source_confidence=row.get("confidence", ""),
                    source_xml_safe=row.get("xml_safe", ""),
                    source_runtime_required=row.get("runtime_required", ""),
                    normalized_xml_path=normalized_xml_path(row.get("xml_path", "")),
                    frozen_dataset_version=VERSION,
                    exclusion_reason="",
                )
                if row.get("selection_status") != "candidate":
                    row["exclusion_reason"] = "source_selection_status_not_candidate"
                    exclusions.append(row)
                    continue
                if row.get("issue_type") in EXCLUDED_TYPES:
                    row["exclusion_reason"] = "touch_target_review_excluded"
                    exclusions.append(row)
                    continue
                if role == "xml_safe" and not (
                    row.get("severity") == "error"
                    and row.get("confidence") == "high"
                    and truth(row.get("xml_safe"))
                    and not truth(row.get("runtime_required"))
                ):
                    row["exclusion_reason"] = "invalid_high_xml_safe_contract"
                    exclusions.append(row)
                    continue
                if role == "boundary" and row.get("difficulty") != "boundary":
                    row["exclusion_reason"] = "invalid_boundary_contract"
                    exclusions.append(row)
                    continue
                pool.append(row)
    return pool, exclusions, repository_index


def git_blob(repository: Path, commit_hash: str, xml_path: str) -> bytes | None:
    completed = subprocess.run(
        ["git", "-C", str(repository), "show", f"{commit_hash}:{xml_path}"],
        check=False,
        capture_output=True,
    )
    return completed.stdout if completed.returncode == 0 else None


def file_sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def element_candidates(root: ET.Element, row: dict) -> list[ET.Element]:
    stored = json_dict(row.get("relevant_attributes", ""))
    target_id = parse_id(row.get("widget_id") or stored.get("id"))
    expected_type = normalize_view_type(row.get("widget_type", ""))
    matches = []
    for element in root.iter():
        attrs = all_attrs(element)
        if target_id and parse_id(attrs.get("id")) != target_id:
            continue
        if expected_type and normalize_view_type(element.tag) != expected_type:
            continue
        matches.append(element)
    if len(matches) <= 1:
        return matches
    comparable = {
        key: value for key, value in stored.items()
        if key not in {"layout_width", "layout_height", "id"}
    }
    narrowed = [
        element for element in matches
        if all(all_attrs(element).get(key) == value for key, value in comparable.items())
    ]
    return narrowed or matches


def candidate_selector(element: ET.Element, root: ET.Element) -> str:
    return element_path(build_stack(element, build_parent_map(root)))


def current_resolution_matches(
    row: dict,
    attributes: dict,
    resolver: AndroidResourceResolver,
) -> tuple[bool, str]:
    current, unresolved = resolver.resolve_attributes(attributes)
    relevant = RELEVANT_RESOURCE_ATTRIBUTES.get(row.get("issue_type", ""), set())
    unresolved = [value for value in unresolved if value.split("=", 1)[0] in relevant]
    if row.get("issue_subtype") == "label_for_target_missing":
        unresolved = [value for value in unresolved if not value.startswith("labelFor=")]
    if unresolved:
        return False, "unresolved critical resources: " + "; ".join(unresolved)
    stored = json_dict(row.get("resolved_resource_values", ""))
    for key in sorted(relevant & set(stored) & set(current)):
        if stored[key] != current[key]:
            return False, f"resolved resource changed: {key}"
    return True, ""


def revalidate_targeted(
    row: dict,
    repository: Path,
    resolver: AndroidResourceResolver,
) -> tuple[bool, str]:
    issue_type = row.get("issue_type")
    if issue_type == "input_type_semantics":
        return validate_input_semantics(row, repository, resolver)
    if issue_type == "label_association":
        return validate_label_association(row, repository, resolver)
    if issue_type == "accessibility_attribute_conflict":
        adapted = dict(row)
        if adapted.get("issue_subtype") == "standard_interactive_focusable_false":
            adapted["issue_subtype"] = "interactive_control_not_focusable"
        valid, reason, _ = validate_attribute_conflict(adapted)
        return valid, reason
    return False, "targeted row has an unsupported issue type"


def base_consistency_record(row: dict) -> dict:
    return {
        "candidate_id": row.get("candidate_id", ""),
        "source_dataset": row.get("source_dataset", ""),
        "candidate_role": row.get("candidate_role", ""),
        "app_name": row.get("app_name", ""),
        "repository_url": row.get("repository_url", ""),
        "repository_path": "",
        "xml_path": row.get("xml_path", ""),
        "expected_commit": row.get("commit_hash", ""),
        "actual_commit": "",
        "source_file_sha256": "",
        "commit_file_sha256": "",
        "original_line_number": row.get("line_number", ""),
        "relocated_line_number": "",
        "node_relocated": "false",
        "widget_id_matches": "false",
        "widget_type_matches": "false",
        "attributes_match": "false",
        "resources_match": "false",
        "layout_signature_matches": "false",
        "candidate_contract_matches": "false",
        "trigger_revalidated": "false",
        "status": "failed",
        "reasons": "",
    }


def validate_pool(
    rows: list[dict],
    repository_index: dict[tuple[str, str], dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Re-scan candidate repositories and verify each source node at its commit."""
    validated: list[dict] = []
    exclusions: list[dict] = []
    reports: list[dict] = []
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["source_dataset"], repository_key(row))].append(row)

    for (source_name, _), repository_rows in sorted(grouped.items()):
        first = repository_rows[0]
        repo_meta = repository_index.get((source_name, normalize_repo_url(first.get("repository_url", ""))))
        if repo_meta is None:
            repo_meta = repository_index.get((source_name, "package:" + first.get("package_name", "").casefold()))
        repository = Path(repo_meta.get("repository_path", "")) if repo_meta else Path()
        current_candidates: dict[str, dict] = {}
        resolver = None
        repository_failure = ""
        if not repo_meta:
            repository_failure = "repository_summary_mapping_missing"
        elif not repository.is_dir() or not (repository / ".git").exists():
            repository_failure = "repository_or_git_metadata_missing"
        else:
            try:
                resolver = AndroidResourceResolver(repository, first.get("subdir", ""))
                metadata = {
                    "package_name": first.get("package_name", repository.name),
                    "app_name": first.get("app_name", repository.name),
                    "repository_url": first.get("repository_url", ""),
                    "repo_type": first.get("repo_type", "git"),
                    "subdir": first.get("subdir", ""),
                    "repository_status": "source_consistency_recheck",
                }
                _, rescanned, _ = scan_repository(
                    repository,
                    metadata=metadata,
                    detector_profile="expanded_v3",
                    high_min=0.8,
                    medium_min=0.4,
                )
                current_candidates = {row["candidate_id"]: row for row in rescanned}
            except Exception as exc:  # Keep a row-level audit trail for repository failures.
                repository_failure = f"repository_rescan_failed:{type(exc).__name__}:{exc}"

        for row in repository_rows:
            report = base_consistency_record(row)
            report["repository_path"] = str(repository) if repo_meta else ""
            reasons = []
            if repository_failure:
                reasons.append(repository_failure)
            if not reasons:
                actual_commit = git_value(repository, "rev-parse", "HEAD")
                report["actual_commit"] = actual_commit
                if actual_commit != row.get("commit_hash") or actual_commit != repo_meta.get("commit_hash"):
                    reasons.append("commit_mismatch")
            xml_path = repository / row.get("xml_path", "") if repo_meta else Path()
            root = None
            if not reasons and not xml_path.is_file():
                reasons.append("xml_file_missing")
            if not reasons:
                source_payload = xml_path.read_bytes()
                commit_payload = git_blob(repository, row["commit_hash"], row["xml_path"])
                report["source_file_sha256"] = file_sha256_bytes(source_payload)
                if commit_payload is None:
                    reasons.append("commit_blob_missing")
                else:
                    report["commit_file_sha256"] = file_sha256_bytes(commit_payload)
                    if report["source_file_sha256"] != report["commit_file_sha256"]:
                        reasons.append("working_xml_differs_from_commit")
            if not reasons:
                try:
                    root = ET.parse(xml_path).getroot()
                except (ET.ParseError, OSError) as exc:
                    reasons.append(f"xml_parser_error:{exc}")
            if not reasons and root is not None:
                layout_match = canonical_layout_signature(xml_path) == row.get("dedup_group")
                report["layout_signature_matches"] = str(layout_match).lower()
                if not layout_match:
                    reasons.append("layout_signature_mismatch")
                apply_explicit_styles(root, resolver.styles)
                matches = element_candidates(root, row)
                if len(matches) != 1:
                    reasons.append("source_node_not_uniquely_relocated")
                else:
                    element = matches[0]
                    attrs = all_attrs(element)
                    report["node_relocated"] = "true"
                    expected_id = parse_id(row.get("widget_id"))
                    id_match = not expected_id or parse_id(attrs.get("id")) == expected_id
                    type_match = normalize_view_type(element.tag) == normalize_view_type(row.get("widget_type", ""))
                    stored_attrs = json_dict(row.get("relevant_attributes", ""))
                    attr_match = all(attrs.get(key) == value for key, value in stored_attrs.items())
                    report["widget_id_matches"] = str(id_match).lower()
                    report["widget_type_matches"] = str(type_match).lower()
                    report["attributes_match"] = str(attr_match).lower()
                    if not id_match:
                        reasons.append("widget_id_mismatch")
                    if not type_match:
                        reasons.append("widget_type_mismatch")
                    if not attr_match:
                        reasons.append("trigger_attributes_changed")
                    resource_match, resource_reason = current_resolution_matches(row, attrs, resolver)
                    report["resources_match"] = str(resource_match).lower()
                    if not resource_match:
                        reasons.append(resource_reason)
                    relocated_line = line_number_for(xml_path, attrs.get("id", ""), strip_ns(element.tag))
                    if not relocated_line:
                        # A clean commit plus a unique selector still provides an exact node anchor.
                        relocated_line = int(row.get("line_number") or 0)
                    report["relocated_line_number"] = relocated_line
                    if relocated_line <= 0:
                        reasons.append("line_number_not_relocatable")

            contract_match = (
                row["candidate_role"] == "xml_safe"
                and row.get("severity") == "error"
                and row.get("confidence") == "high"
                and truth(row.get("xml_safe"))
                and not truth(row.get("runtime_required"))
            ) or (
                row["candidate_role"] == "boundary"
                and row.get("difficulty") == "boundary"
            )
            report["candidate_contract_matches"] = str(contract_match).lower()
            if not contract_match:
                reasons.append("candidate_contract_mismatch")

            trigger_valid = False
            trigger_reason = ""
            if not reasons:
                rescanned = current_candidates.get(row["candidate_id"])
                if rescanned is not None:
                    trigger_valid = (
                        rescanned.get("issue_type") == row.get("issue_type")
                        and rescanned.get("issue_subtype") == row.get("issue_subtype")
                        and rescanned.get("severity") == row.get("severity")
                        and rescanned.get("confidence") == row.get("confidence")
                        and truth(rescanned.get("xml_safe")) == truth(row.get("xml_safe"))
                        and truth(rescanned.get("runtime_required")) == truth(row.get("runtime_required"))
                    )
                    if not trigger_valid:
                        trigger_reason = "rescanned_candidate_contract_changed"
                elif source_name == "targeted_gap_fill_audited":
                    trigger_valid, trigger_reason = revalidate_targeted(row, repository, resolver)
                else:
                    trigger_reason = "candidate_not_reproduced_by_source_rescan"
                if not trigger_valid:
                    reasons.append(trigger_reason)
            report["trigger_revalidated"] = str(trigger_valid).lower()
            if reasons:
                report["reasons"] = "; ".join(reasons)
                rejected = dict(row)
                rejected.update(
                    repository_path=str(repository) if repo_meta else "",
                    consistency_status="failed",
                    exclusion_reason="source_consistency_failed:" + ";".join(reasons),
                )
                exclusions.append(rejected)
            else:
                report["status"] = "passed"
                prepared = dict(row)
                prepared.update(
                    repository_path=str(repository),
                    source_file_sha256=report["source_file_sha256"],
                    commit_file_sha256=report["commit_file_sha256"],
                    relocated_line_number=str(report["relocated_line_number"]),
                    normalized_widget_type=normalize_view_type(row.get("widget_type", "")),
                    consistency_status="passed",
                    exclusion_reason="",
                )
                if prepared["candidate_role"] == "boundary":
                    # The formal scanner used difficulty=boundary as the routing
                    # contract even for a few warning rows whose legacy xml_safe
                    # field remained true. Preserve source_* and normalize the
                    # frozen role so boundary can never enter the repair denominator.
                    prepared["xml_safe"] = "false"
                # Recompute from source so all similar-layout groups use one algorithm.
                prepared["dedup_group"] = canonical_layout_signature(xml_path)
                validated.append(prepared)
            reports.append(report)
    return validated, exclusions, reports


def mark_excluded(row: dict, reason: str) -> dict:
    result = dict(row)
    result["selection_status"] = "excluded"
    result["exclusion_reason"] = reason
    return result


def deduplicate_candidates(rows: list[dict], seed: str) -> tuple[list[dict], list[dict]]:
    """Apply strict source, configuration, control, and within-layout deduplication."""
    retained: list[dict] = []
    excluded: list[dict] = []
    seen_candidate_ids = set()
    seen_control = set()
    seen_variant = set()
    seen_exact_copy = set()
    per_xml_type = Counter()
    per_app_type = Counter()
    fingerprints: dict[tuple[str, str], str] = {}

    ordered = sorted(
        rows,
        key=lambda row: (
            {"hard": 0, "medium": 1, "easy": 2, "boundary": 3}.get(row.get("difficulty"), 4),
            stable_key(row, seed),
        ),
    )
    for row in ordered:
        candidate_id = row["candidate_id"]
        app = repository_key(row)
        attrs = json_dict(row.get("relevant_attributes", ""))
        widget_anchor = parse_id(row.get("widget_id")) or "|".join((
            normalize_view_type(row.get("widget_type", "")),
            str(row.get("relocated_line_number") or row.get("line_number") or ""),
        ))
        control_key = (app, row["xml_path"], widget_anchor, row["issue_type"], row["issue_subtype"])
        evidence_value = (
            attrs.get("labelFor")
            or attrs.get("importantForAccessibility")
            or attrs.get("focusable")
            or attrs.get("inputType")
            or widget_anchor
        )
        variant_key = (
            app,
            row["normalized_xml_path"],
            row["issue_type"],
            row["issue_subtype"],
            widget_anchor,
            str(evidence_value),
        )
        file_key = (row["repository_path"], row["xml_path"])
        fingerprint = fingerprints.get(file_key)
        if fingerprint is None:
            fingerprint = strict_layout_fingerprint(Path(row["repository_path"]) / row["xml_path"])
            fingerprints[file_key] = fingerprint
        exact_copy_key = (
            fingerprint,
            row["issue_type"],
            row["issue_subtype"],
            normalize_view_type(row.get("widget_type", "")),
            parse_id(row.get("widget_id")) or str(evidence_value),
        )
        xml_type_key = (app, row["normalized_xml_path"], row["issue_type"])
        app_type_key = (app, row["issue_type"])
        reason = ""
        if candidate_id in seen_candidate_ids:
            reason = "duplicate_candidate_id"
        elif control_key in seen_control:
            reason = "duplicate_issue_on_same_control"
        elif variant_key in seen_variant:
            reason = "duplicate_layout_configuration_variant"
        elif exact_copy_key in seen_exact_copy:
            reason = "duplicate_or_copied_xml_issue"
        elif per_xml_type[xml_type_key] >= 2:
            reason = "same_xml_same_type_cap_exceeded_2"
        elif per_app_type[app_type_key] >= 4:
            reason = "same_app_same_type_cap_exceeded_4"
        if reason:
            excluded.append(mark_excluded(row, reason))
            continue
        seen_candidate_ids.add(candidate_id)
        seen_control.add(control_key)
        seen_variant.add(variant_key)
        seen_exact_copy.add(exact_copy_key)
        per_xml_type[xml_type_key] += 1
        per_app_type[app_type_key] += 1
        retained.append(row)
    return retained, excluded


def choose_row(
    candidates: list[dict],
    selected: list[dict],
    seed: str,
    prefer_new_app: bool,
    prefer_new_xml: bool,
) -> dict | None:
    selected_ids = {row["candidate_id"] for row in selected}
    apps = Counter(repository_key(row) for row in selected)
    xmls = {(repository_key(row), row["normalized_xml_path"]) for row in selected}
    eligible = [
        row for row in candidates
        if row["candidate_id"] not in selected_ids and apps[repository_key(row)] < 10
    ]
    if not eligible:
        return None

    def rank(row: dict):
        app = repository_key(row)
        xml = (app, row["normalized_xml_path"])
        difficulty = {"hard": 0, "medium": 1, "easy": 2, "boundary": 1}.get(row.get("difficulty"), 3)
        app_preference = (
            0 if (app not in apps if prefer_new_app else app in apps) else 1
        )
        xml_preference = (
            0 if (xml not in xmls if prefer_new_xml else xml in xmls) else 1
        )
        return (
            0 if row["candidate_role"] == "xml_safe" else 1,
            app_preference,
            xml_preference,
            difficulty,
            apps[app],
            stable_key(row, seed),
        )

    return min(eligible, key=rank)


def sample_dataset(rows: list[dict], seed: str) -> tuple[list[dict], list[dict], list[str]]:
    """Build a balanced deterministic sample without using model outcomes."""
    selected: list[dict] = []
    sampling_exclusions: list[dict] = []
    notes: list[str] = []
    by_type = defaultdict(list)
    for row in rows:
        by_type[row["issue_type"]].append(row)

    # Strictly audited natural long-tail findings are retained first.
    for issue_type in LONG_TAIL_TYPES:
        selected.extend(sorted(
            (row for row in by_type[issue_type] if row["candidate_role"] == "xml_safe"),
            key=lambda row: stable_key(row, seed),
        ))

    # Allocate the six primary classes together. This lets the sampler reuse
    # multi-issue layouts instead of creating a new XML for every type.
    selected_ids = {row["candidate_id"] for row in selected}
    while True:
        counts = Counter(row["issue_type"] for row in selected)
        unmet = {issue_type: max(target - counts[issue_type], 0) for issue_type, target in TYPE_QUOTAS.items()}
        if not any(unmet.values()):
            break
        apps = Counter(repository_key(row) for row in selected)
        xmls = {(repository_key(row), row["normalized_xml_path"]) for row in selected}
        available = [
            row for row in rows
            if row["candidate_id"] not in selected_ids
            and unmet.get(row["issue_type"], 0) > 0
            and apps[repository_key(row)] < 10
        ]
        if not available:
            break
        layout_potential = Counter(
            (repository_key(row), row["normalized_xml_path"])
            for row in available
        )
        app_type_potential: dict[str, set[str]] = defaultdict(set)
        for candidate in available:
            app_type_potential[repository_key(candidate)].add(candidate["issue_type"])

        def allocation_rank(row: dict):
            app = repository_key(row)
            xml = (app, row["normalized_xml_path"])
            app_preference = 0 if (app not in apps if len(apps) < 40 else app in apps) else 1
            difficulty = {"hard": 0, "medium": 1, "easy": 2, "boundary": 1}.get(row.get("difficulty"), 3)
            return (
                0 if row["candidate_role"] == "xml_safe" else 1,
                -len(app_type_potential[app]),
                app_preference,
                0 if xml in xmls else 1,
                -layout_potential[xml],
                difficulty,
                apps[app],
                stable_key(row, seed + "|primary-allocation"),
            )

        choice = min(available, key=allocation_rank)
        selected.append(choice)
        selected_ids.add(choice["candidate_id"])

    # Fill the XML-safe denominator using only already eligible primary rows.
    def dataset_counts() -> tuple[int, int, int, int]:
        return (
            len({repository_key(row) for row in selected}),
            len({(repository_key(row), row["normalized_xml_path"]) for row in selected}),
            sum(row["candidate_role"] == "xml_safe" for row in selected),
            len(selected),
        )

    while dataset_counts()[2] < 120 and dataset_counts()[3] < 180:
        apps = Counter(repository_key(row) for row in selected)
        xmls = {(repository_key(row), row["normalized_xml_path"]) for row in selected}
        available = [
            row for row in rows
            if row["candidate_id"] not in selected_ids
            and row["candidate_role"] == "xml_safe"
            and row["issue_type"] in PRIMARY_TYPES
            and apps[repository_key(row)] < 10
        ]
        if not available:
            break
        choice = min(available, key=lambda row: (
            0 if repository_key(row) in apps else 1,
            0 if (repository_key(row), row["normalized_xml_path"]) in xmls else 1,
            {"hard": 0, "medium": 1, "easy": 2}.get(row.get("difficulty"), 3),
            stable_key(row, seed + "|xml-safe-fill"),
        ))
        selected.append(choice)
        selected_ids.add(choice["candidate_id"])

    # Add distinct XML only if the source-derived sample is still below 90.
    while dataset_counts()[1] < 90 and dataset_counts()[3] < 180:
        apps = Counter(repository_key(row) for row in selected)
        xmls = {(repository_key(row), row["normalized_xml_path"]) for row in selected}
        available = [
            row for row in rows
            if row["candidate_id"] not in selected_ids
            and row["candidate_role"] == "xml_safe"
            and row["issue_type"] in PRIMARY_TYPES
            and (repository_key(row), row["normalized_xml_path"]) not in xmls
            and apps[repository_key(row)] < 10
        ]
        if not available:
            break
        choice = min(available, key=lambda row: (
            0 if repository_key(row) in apps else 1,
            stable_key(row, seed + "|xml-minimum-fill"),
        ))
        selected.append(choice)
        selected_ids.add(choice["candidate_id"])

    selected_ids = {row["candidate_id"] for row in selected}
    for row in rows:
        if row["candidate_id"] not in selected_ids:
            sampling_exclusions.append(mark_excluded(row, "not_selected_by_v2_balanced_sampling"))

    selected = sorted(
        selected,
        key=lambda row: (repository_key(row), row["xml_path"], int(row.get("line_number") or 0), row["candidate_id"]),
    )
    boundary_count = sum(row["candidate_role"] == "boundary" for row in selected)
    if boundary_count > 30:
        notes.append(
            "boundary soft target 20-30 is infeasible with the six primary-type hard minimums; "
            f"the minimum selected boundary allocation is {boundary_count}"
        )
    return selected, sampling_exclusions, notes


def best_split(rows: list[dict], seed: str) -> tuple[dict[str, str], dict]:
    """Search deterministic seeds for the most balanced leakage-safe app split."""
    repositories = {repository_key(row) for row in rows}
    target_development = round(len(repositories) * 0.20)
    best = None
    for attempt in range(500):
        attempt_seed = f"{seed}|split|{attempt}"
        assignments = split_by_repository(rows, 0.20, attempt_seed)
        trial = [dict(row, dataset_split=assignments[repository_key(row)]) for row in rows]
        dev_repos = {repository_key(row) for row in trial if row["dataset_split"] == "development"}
        coverage = {
            split: {row["issue_type"] for row in trial if row["dataset_split"] == split}
            for split in ("development", "test")
        }
        missing = sum(
            issue_type not in coverage[split]
            for split in coverage
            for issue_type in PRIMARY_TYPES
        )
        dev_ratio_gap = abs(len(dev_repos) - target_development)
        dev_issue_ratio = sum(row["dataset_split"] == "development" for row in trial) / max(len(trial), 1)
        score = (missing, dev_ratio_gap, abs(dev_issue_ratio - 0.20), attempt)
        if best is None or score < best[0]:
            best = (score, assignments, coverage, attempt_seed)
    assert best is not None
    score, assignments, coverage, used_seed = best
    return assignments, {
        "seed": used_seed,
        "missing_primary_split_coverage": score[0],
        "development_repository_target_gap": score[1],
        "coverage": {key: sorted(value) for key, value in coverage.items()},
    }


def leakage_rows(rows: list[dict]) -> list[dict]:
    checks = []
    definitions = {
        "app": lambda row: row.get("package_name", "").casefold(),
        "repository": repository_key,
        "dedup_group": lambda row: row.get("dedup_group", ""),
        "similar_layout": lambda row: row.get("dedup_group", ""),
    }
    for name, getter in definitions.items():
        groups = defaultdict(set)
        for row in rows:
            value = getter(row)
            if value:
                groups[value].add(row["dataset_split"])
        overlap = sorted(key for key, splits in groups.items() if len(splits) > 1)
        checks.append({
            "check_name": name,
            "overlap_count": len(overlap),
            "status": "passed" if not overlap else "failed",
            "details": json.dumps(overlap, ensure_ascii=False),
        })
    return checks


def issue_type_distribution(rows: list[dict]) -> list[dict]:
    result = []
    for issue_type in sorted(set(PRIMARY_TYPES) | set(LONG_TAIL_TYPES)):
        matches = [row for row in rows if row["issue_type"] == issue_type]
        result.append({
            "issue_type": issue_type,
            "role": "primary" if issue_type in PRIMARY_TYPES else "exploratory_long_tail",
            "total_count": len(matches),
            "xml_safe_count": sum(row["candidate_role"] == "xml_safe" for row in matches),
            "boundary_count": sum(row["candidate_role"] == "boundary" for row in matches),
            "app_count": len({repository_key(row) for row in matches}),
            "xml_count": len({(repository_key(row), row["normalized_xml_path"]) for row in matches}),
            "minimum_15_instances_met": issue_type not in PRIMARY_TYPES or len(matches) >= 15,
            "minimum_4_apps_met": issue_type not in PRIMARY_TYPES or len({repository_key(row) for row in matches}) >= 4,
        })
    return result


def difficulty_distribution(rows: list[dict]) -> list[dict]:
    return [
        {
            "difficulty": difficulty,
            "total_count": sum(row["difficulty"] == difficulty for row in rows),
            "xml_safe_count": sum(row["difficulty"] == difficulty and row["candidate_role"] == "xml_safe" for row in rows),
            "boundary_count": sum(row["difficulty"] == difficulty and row["candidate_role"] == "boundary" for row in rows),
        }
        for difficulty in ("easy", "medium", "hard", "boundary")
    ]


def app_distribution(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[repository_key(row)].append(row)
    return [
        {
            "repository_key": key,
            "package_name": values[0]["package_name"],
            "app_name": values[0]["app_name"],
            "repository_url": values[0]["repository_url"],
            "dataset_split": values[0]["dataset_split"],
            "issue_count": len(values),
            "xml_safe_count": sum(row["candidate_role"] == "xml_safe" for row in values),
            "boundary_count": sum(row["candidate_role"] == "boundary" for row in values),
            "xml_count": len({row["normalized_xml_path"] for row in values}),
            "contribution_ratio": round(len(values) / max(len(rows), 1), 6),
        }
        for key, values in sorted(grouped.items())
    ]


def split_distribution(rows: list[dict]) -> list[dict]:
    result = []
    for split in ("development", "test"):
        matches = [row for row in rows if row["dataset_split"] == split]
        result.append({
            "dataset_split": split,
            "app_count": len({repository_key(row) for row in matches}),
            "xml_count": len({(repository_key(row), row["normalized_xml_path"]) for row in matches}),
            "total_count": len(matches),
            "xml_safe_count": sum(row["candidate_role"] == "xml_safe" for row in matches),
            "boundary_count": sum(row["candidate_role"] == "boundary" for row in matches),
            **{f"{issue_type}_count": sum(row["issue_type"] == issue_type for row in matches) for issue_type in PRIMARY_TYPES},
        })
    return result


def hard_checks(
    rows: list[dict],
    consistency: list[dict],
    leakage: list[dict],
    v1_unchanged: bool,
) -> tuple[dict[str, bool], list[str]]:
    apps = {repository_key(row) for row in rows}
    xmls = {(repository_key(row), row["normalized_xml_path"]) for row in rows}
    safe = [row for row in rows if row["candidate_role"] == "xml_safe"]
    by_type = {issue_type: [row for row in rows if row["issue_type"] == issue_type] for issue_type in PRIMARY_TYPES}
    app_counts = Counter(repository_key(row) for row in rows)
    maximum_ratio = max(app_counts.values(), default=0) / max(len(rows), 1)
    checks = {
        "minimum_35_apps": len(apps) >= 35,
        "maximum_45_apps": len(apps) <= 45,
        "minimum_90_xml": len(xmls) >= 90,
        "maximum_120_xml": len(xmls) <= 120,
        "minimum_120_xml_safe": len(safe) >= 120,
        "maximum_150_xml_safe": len(safe) <= 150,
        "total_at_most_180": len(rows) <= 180,
        "six_primary_types_minimum_15": all(len(by_type[value]) >= 15 for value in PRIMARY_TYPES),
        "six_primary_types_minimum_4_apps": all(len({repository_key(row) for row in by_type[value]}) >= 4 for value in PRIMARY_TYPES),
        "single_app_at_most_10_percent": maximum_ratio <= 0.10,
        "all_selected_consistency_passed": all(row["consistency_status"] == "passed" for row in rows),
        "consistency_report_has_no_selected_failure": all(row["status"] == "passed" for row in consistency if row["candidate_id"] in {item["candidate_id"] for item in rows}),
        "no_split_leakage": all(row["status"] == "passed" for row in leakage),
        "v1_hashes_unchanged_during_build": v1_unchanged,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return checks, failures


def dataset_summary(rows: list[dict]) -> dict:
    safe = [row for row in rows if row["candidate_role"] == "xml_safe"]
    boundary = [row for row in rows if row["candidate_role"] == "boundary"]
    app_counts = Counter(repository_key(row) for row in rows)
    return {
        "app_count": len(app_counts),
        "xml_count": len({(repository_key(row), row["normalized_xml_path"]) for row in rows}),
        "xml_safe_count": len(safe),
        "boundary_count": len(boundary),
        "total_issue_count": len(rows),
        "long_tail_count": sum(row["issue_type"] in LONG_TAIL_TYPES for row in rows),
        "easy_xml_safe_count": sum(row["difficulty"] == "easy" for row in safe),
        "easy_xml_safe_ratio": round(sum(row["difficulty"] == "easy" for row in safe) / max(len(safe), 1), 6),
        "maximum_app_contribution_ratio": round(max(app_counts.values(), default=0) / max(len(rows), 1), 6),
    }


def write_report(
    path: Path,
    status: str,
    summary: dict,
    types: list[dict],
    difficulties: list[dict],
    splits: list[dict],
    exclusion_counts: Counter,
    consistency_counts: Counter,
    leakage: list[dict],
    failures: list[str],
    notes: list[str],
    dataset_hash: str,
    v1_unchanged: bool,
) -> None:
    lines = [
        "# V2 冻结数据集报告",
        "",
        "## 结论",
        "",
        f"- 状态：`{status}`",
        f"- 数据集版本：`{VERSION}`",
        f"- 数据集 SHA-256：`{dataset_hash}`",
        f"- App：{summary['app_count']}；XML：{summary['xml_count']}",
        f"- XML-safe：{summary['xml_safe_count']}；boundary：{summary['boundary_count']}；总问题：{summary['total_issue_count']}",
        f"- XML-safe 中 easy 占比：{summary['easy_xml_safe_ratio']:.2%}",
        f"- 单 App 最大贡献占比：{summary['maximum_app_contribution_ratio']:.2%}",
        f"- V1 在本次构建前后哈希保持不变：{'是' if v1_unchanged else '否'}",
        "",
        "## 类型分布",
        "",
        "| 类型 | 角色 | 总数 | XML-safe | Boundary | App 来源 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in types:
        lines.append(
            f"| {row['issue_type']} | {row['role']} | {row['total_count']} | "
            f"{row['xml_safe_count']} | {row['boundary_count']} | {row['app_count']} |"
        )
    lines.extend((
        "",
        "## 难度分布",
        "",
        "| 难度 | 总数 | XML-safe | Boundary |",
        "|---|---:|---:|---:|",
    ))
    for row in difficulties:
        lines.append(f"| {row['difficulty']} | {row['total_count']} | {row['xml_safe_count']} | {row['boundary_count']} |")
    lines.extend((
        "",
        "## 数据划分",
        "",
        "| 集合 | App | XML | 总数 | XML-safe | Boundary |",
        "|---|---:|---:|---:|---:|---:|",
    ))
    for row in splits:
        lines.append(
            f"| {row['dataset_split']} | {row['app_count']} | {row['xml_count']} | "
            f"{row['total_count']} | {row['xml_safe_count']} | {row['boundary_count']} |"
        )
    lines.extend((
        "",
        "## 校验与排除",
        "",
        f"- 源码一致性：通过 {consistency_counts['passed']}，失败 {consistency_counts['failed']}。",
        f"- 去重及抽样排除：{sum(exclusion_counts.values())} 条。",
        f"- 泄漏检查：{'全部通过' if all(row['status'] == 'passed' for row in leakage) else '存在失败'}。",
    ))
    for reason, count in sorted(exclusion_counts.items()):
        lines.append(f"- `{reason}`：{count}")
    if notes:
        lines.extend(("", "## 约束说明", ""))
        lines.extend(f"- {note}" for note in notes)
    if failures:
        lines.extend(("", "## 未通过的冻结条件", ""))
        lines.extend(f"- `{failure}`" for failure in failures)
        lines.append("- 因硬性条件未全部满足，数据已输出供审计，但未标记为冻结。")
    else:
        lines.extend((
            "",
            "## 冻结声明",
            "",
            "所有硬性条件均已通过。Development/Test 按 App 与仓库划分，boundary 不进入 XML-safe 修复率分母，触控目标 review 未进入本数据集。",
            "本构建仅使用源码、资源、既定规则和固定随机种子，未使用任何模型输出，也未调用付费 API。",
        ))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checksums(output_root: Path) -> dict[str, str]:
    checksums = {}
    for path in sorted(output_root.iterdir()):
        if path.is_file() and path.name != "v2_checksums.sha256":
            checksums[path.name] = sha256_file(path)
    content = "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items()))
    (output_root / "v2_checksums.sha256").write_text(content, encoding="ascii")
    return checksums


def verify_existing_freeze(output_root: Path) -> dict | None:
    metadata_path = output_root / "v2_dataset_metadata.json"
    checksum_path = output_root / "v2_checksums.sha256"
    if not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("status") != "frozen":
        return None
    mismatches = []
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        path = output_root / name
        if not path.exists() or sha256_file(path) != digest:
            mismatches.append(name)
    if mismatches:
        raise RuntimeError("existing frozen V2 checksum mismatch: " + ", ".join(mismatches))
    return metadata


def build(output_root: Path, seed: str = DEFAULT_SEED) -> dict:
    ensure_output_is_v2(output_root)
    existing = verify_existing_freeze(output_root)
    if existing is not None:
        return {"status": "already_frozen_verified", **existing}

    input_files = [
        FORMAL_ROOT / name for name in (
            "high_confidence_candidates.csv", "boundary_candidates.csv", "repository_summary.csv",
            "candidate_manifest.json", "v1_integrity_check.json",
        )
    ] + [
        TARGETED_ROOT / name for name in (
            "high_confidence_candidates.csv", "repository_summary.csv", "integrity_check.json",
        )
    ]
    source_before = files_snapshot(input_files)
    v1_before = v1_current_snapshot()

    pool, exclusions, repository_index = load_candidate_pool()
    validated, consistency_exclusions, consistency = validate_pool(pool, repository_index)
    exclusions.extend(consistency_exclusions)
    deduplicated, duplicate_exclusions = deduplicate_candidates(validated, seed)
    exclusions.extend(duplicate_exclusions)
    selected, sampling_exclusions, sampling_notes = sample_dataset(deduplicated, seed)
    exclusions.extend(sampling_exclusions)

    assignments, split_meta = best_split(selected, seed)
    for row in selected:
        row["dataset_split"] = assignments[repository_key(row)]
        row["selection_status"] = "included"
    assert_no_split_leakage(selected)
    leakage = leakage_rows(selected)

    source_after = files_snapshot(input_files)
    v1_after = v1_current_snapshot()
    source_unchanged = source_before == source_after
    v1_unchanged = snapshots_equal(v1_before, v1_after)
    checks, failures = hard_checks(selected, consistency, leakage, v1_unchanged)
    if not source_unchanged:
        checks["source_scan_inputs_unchanged"] = False
        failures.append("source_scan_inputs_unchanged")
    else:
        checks["source_scan_inputs_unchanged"] = True
    status = "frozen" if not failures else "build_failed_not_frozen"

    temporary = output_root.with_name(output_root.name + ".building")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)

    xml_safe = [row for row in selected if row["candidate_role"] == "xml_safe"]
    boundary = [row for row in selected if row["candidate_role"] == "boundary"]
    long_tail = [row for row in selected if row["issue_type"] in LONG_TAIL_TYPES]
    development = [row for row in selected if row["dataset_split"] == "development"]
    test = [row for row in selected if row["dataset_split"] == "test"]
    types = issue_type_distribution(selected)
    difficulties = difficulty_distribution(selected)
    apps = app_distribution(selected)
    splits = split_distribution(selected)

    write_csv(temporary / "v2_frozen_manifest.csv", selected, V2_FIELDS)
    write_csv(temporary / "v2_development.csv", development, V2_FIELDS)
    write_csv(temporary / "v2_test.csv", test, V2_FIELDS)
    write_csv(temporary / "v2_xml_safe.csv", xml_safe, V2_FIELDS)
    write_csv(temporary / "v2_boundary.csv", boundary, V2_FIELDS)
    write_csv(temporary / "v2_long_tail_exploratory.csv", long_tail, V2_FIELDS)
    write_csv(temporary / "v2_sampling_exclusions.csv", exclusions, V2_FIELDS)
    write_csv(temporary / "v2_source_consistency_report.csv", consistency, CONSISTENCY_FIELDS)
    write_csv(temporary / "v2_leakage_check.csv", leakage, ["check_name", "overlap_count", "status", "details"])
    write_csv(temporary / "v2_issue_type_distribution.csv", types, list(types[0].keys()))
    write_csv(temporary / "v2_difficulty_distribution.csv", difficulties, list(difficulties[0].keys()))
    write_csv(temporary / "v2_app_distribution.csv", apps, list(apps[0].keys()))
    write_csv(temporary / "v2_split_distribution.csv", splits, list(splits[0].keys()))

    dataset_hash = sha256_file(temporary / "v2_frozen_manifest.csv")
    summary = dataset_summary(selected)
    exclusion_counts = Counter(row.get("exclusion_reason", "unspecified") for row in exclusions)
    consistency_counts = Counter(row["status"] for row in consistency)
    metadata = {
        "schema_version": 1,
        "dataset_version": VERSION,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fixed_random_seed": seed,
        "dataset_sha256": dataset_hash,
        "source_type": "natural_source_issue",
        "paid_api_used": False,
        "model_outputs_used_for_selection": False,
        "issue_injection_used": False,
        "review_required_included": False,
        "touch_target_review_included": False,
        "boundary_in_xml_safe_denominator": False,
        "summary": summary,
        "primary_issue_types": list(PRIMARY_TYPES),
        "exploratory_long_tail_types": list(LONG_TAIL_TYPES),
        "split": split_meta,
        "hard_checks": checks,
        "freeze_failures": failures,
        "constraint_notes": sampling_notes,
        "source_inputs_unchanged": source_unchanged,
        "source_input_hashes": source_after,
        "v1_hashes_unchanged_during_build": v1_unchanged,
        "v1_preexisting_frozen_manifest_mismatch_count": v1_before["preexisting_mismatch_count"],
        "v1_current_hashes": {row["path"]: row["current_sha256"] for row in v1_after["records"]},
    }
    (temporary / "v2_dataset_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(
        temporary / "V2_FROZEN_DATASET_REPORT_ZH.md",
        status,
        summary,
        types,
        difficulties,
        splits,
        exclusion_counts,
        consistency_counts,
        leakage,
        failures,
        sampling_notes,
        dataset_hash,
        v1_unchanged,
    )
    checksums = write_checksums(temporary)
    metadata["file_checksums"] = checksums

    if output_root.exists():
        shutil.rmtree(output_root)
    temporary.replace(output_root)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args()
    result = build(args.output_root.resolve(), args.seed)
    print(json.dumps({
        "dataset_version": result.get("dataset_version", VERSION),
        "status": result.get("status"),
        "dataset_sha256": result.get("dataset_sha256", ""),
        "summary": result.get("summary", {}),
        "freeze_failures": result.get("freeze_failures", []),
        "output_root": str(args.output_root.resolve()),
        "paid_api_used": False,
        "model_outputs_used_for_selection": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
