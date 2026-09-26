#!/usr/bin/env python3
"""Run and record a controlled Android XML baseline/RAG comparison."""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ANDROID_NS = "http://schemas.android.com/apk/res/android"
FORMAL_RECORD_FIELDS = [
    "app_name",
    "category",
    "xml_file",
    "interface_role",
    "before_error_count",
    "baseline_after_error_count",
    "enhanced_after_error_count",
    "baseline_repair_rate",
    "enhanced_repair_rate",
    "baseline_iterations",
    "enhanced_iterations",
    "baseline_status",
    "enhanced_status",
    "baseline_warning_count",
    "warning_count",
    "baseline_info_count",
    "info_count",
    "baseline_structural_safety_findings",
    "enhanced_structural_safety_findings",
    "source_review_status",
    "professional_review_status",
    "baseline_semantic_correct_count",
    "baseline_semantic_incorrect_count",
    "baseline_semantic_pending_count",
    "enhanced_semantic_correct_count",
    "enhanced_semantic_incorrect_count",
    "enhanced_semantic_pending_count",
    "baseline_unrelated_change_count",
    "enhanced_unrelated_change_count",
    "baseline_dynamic_semantics_risk_count",
    "enhanced_dynamic_semantics_risk_count",
    "notes",
]
FORMAL_APP_SUMMARY_FIELDS = [
    "app_name",
    "category",
    "run_id",
    "selected_interface_count",
    "before_error_count",
    "baseline_after_error_count",
    "enhanced_after_error_count",
    "baseline_repair_rate",
    "enhanced_repair_rate",
    "baseline_model_calls",
    "enhanced_model_calls",
    "baseline_status",
    "enhanced_status",
    "baseline_warning_count",
    "enhanced_warning_count",
    "baseline_info_count",
    "enhanced_info_count",
    "baseline_structural_safety_findings",
    "enhanced_structural_safety_findings",
    "source_review_status",
    "professional_review_status",
    "baseline_semantic_correct_count",
    "baseline_semantic_incorrect_count",
    "baseline_semantic_pending_count",
    "enhanced_semantic_correct_count",
    "enhanced_semantic_incorrect_count",
    "enhanced_semantic_pending_count",
    "baseline_unrelated_change_count",
    "enhanced_unrelated_change_count",
    "baseline_dynamic_semantics_risk_count",
    "enhanced_dynamic_semantics_risk_count",
    "notes",
]

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.evaluation.collect_android_xml_package import collect  # noqa: E402
from tools.generate import (  # noqa: E402
    MODEL_PROVIDER_CHOICES,
    ModelError,
    model_error_metadata,
    run_model_with_metadata,
    validate_model_configuration,
)
from tools.generate_android_xml import (  # noqa: E402
    DEFAULT_DETECTOR_PROFILE,
    DETECTOR_PROFILE_CHOICES,
    apply_model_result,
    issue_quality,
    run_xml_checker,
    save_report,
    save_safety_report,
    validate_repair_safety,
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def model_call_summary(model_calls):
    calls = [call for call in model_calls if isinstance(call, dict)]
    usage_fields = (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_hit_input_tokens",
        "cache_creation_input_tokens",
    )
    usage = {}
    for field in usage_fields:
        values = [
            call.get("usage", {}).get(field)
            for call in calls
            if call.get("usage", {}).get(field) is not None
        ]
        usage[field] = sum(values) if values else None
    resolved_models = sorted({
        call.get("resolved_model")
        for call in calls
        if call.get("resolved_model")
    })
    successful_calls = [
        call for call in calls if call.get("status") != "failed"
    ]
    failed_calls = [
        call for call in calls if call.get("status") == "failed"
    ]
    return {
        "model_calls": len(calls),
        "successful_model_calls": len(successful_calls),
        "failed_model_calls": len(failed_calls),
        "provider_attempts": sum(
            call.get("provider_attempts", 1) for call in calls
        ),
        "network_retries": sum(
            max(call.get("provider_attempts", 1) - 1, 0)
            for call in calls
        ),
        "duration_ms": round(
            sum(call.get("duration_ms", 0.0) for call in calls),
            3,
        ),
        "usage": usage,
        "resolved_models": resolved_models,
        "request_ids": [
            call.get("request_id") for call in calls if call.get("request_id")
        ],
        "http_statuses": [
            call.get("http_status")
            for call in calls
            if call.get("http_status") is not None
        ],
        "error_types": [
            call.get("error_type")
            for call in failed_calls
            if call.get("error_type")
        ],
    }


def load_issue_report(path: Path):
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    return []


def issue_file_key(issue):
    file_value = issue.get("file", "")
    if not file_value:
        return ""
    path = Path(file_value)
    parts = path.parts
    if "res" in parts:
        index = len(parts) - 1 - list(reversed(parts)).index("res")
        return Path(*parts[index + 1:]).as_posix()
    return path.name


def severity_count_by_file(issues, severity):
    counts = Counter()
    for issue in issues:
        issue_severity = issue.get("severity", issue.get("type", "error"))
        if issue_severity == severity:
            counts[issue_file_key(issue)] += 1
    return counts


def rate(before, after):
    if not before:
        return None
    return (before - after) / before


def load_safety_report(path: Path):
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else payload.get("findings", [])


def empty_review_group(pending_count=0):
    return {
        "decision": None,
        "semantic_correct_count": 0,
        "semantic_incorrect_count": 0,
        "semantic_pending_count": pending_count,
        "unrelated_change_count": None,
        "dynamic_semantics_risk_count": None,
        "notes": "",
    }


def build_manual_review(experiment_id, file_repairs=None):
    files = {}
    for xml_file, repairs in (file_repairs or {}).items():
        files[xml_file] = {
            "source_review_status": "pending",
            "baseline": empty_review_group(repairs.get("baseline", 0)),
            "proposed": empty_review_group(repairs.get("proposed", 0)),
            "notes": "",
        }
    return {
        "schema_version": 2,
        "experiment_id": experiment_id,
        "status": "pending",
        "source_review_status": "pending",
        "professional_review_status": "pending",
        "review_items": [
            "Accessible labels accurately describe each control action",
            "Repairs preserve dynamic value and state announcements",
            "Layout hierarchy, ids, dimensions, and resource references are preserved",
            "No unrelated XML changes were introduced",
        ],
        "baseline": empty_review_group(),
        "proposed": empty_review_group(),
        "files": files,
    }


def normalize_review_group(group, pending_count=0):
    normalized = empty_review_group(pending_count)
    if isinstance(group, dict):
        normalized.update(group)
    return normalized


def normalize_manual_review(review, experiment_id, file_repairs):
    review = dict(review or {})
    normalized = build_manual_review(experiment_id, file_repairs)
    normalized.update({
        key: value
        for key, value in review.items()
        if key not in {"baseline", "proposed", "files"}
    })
    normalized["schema_version"] = 2
    normalized["source_review_status"] = review.get(
        "source_review_status", "pending"
    )
    normalized["professional_review_status"] = review.get(
        "professional_review_status",
        "completed" if review.get("status") == "completed" else "pending",
    )
    normalized["baseline"] = normalize_review_group(review.get("baseline"))
    normalized["proposed"] = normalize_review_group(review.get("proposed"))
    old_files = review.get("files", {})
    for xml_file, repairs in file_repairs.items():
        old_file = old_files.get(xml_file, {})
        normalized["files"][xml_file] = {
            "source_review_status": old_file.get(
                "source_review_status", "pending"
            ),
            "baseline": normalize_review_group(
                old_file.get("baseline"), repairs.get("baseline", 0)
            ),
            "proposed": normalize_review_group(
                old_file.get("proposed"), repairs.get("proposed", 0)
            ),
            "notes": old_file.get("notes", ""),
        }
    return normalized


def manual_review_for_run(run_dir, config, before_errors, baseline_errors, proposed_errors):
    xml_files = sorted(
        path.relative_to(run_dir / "original/res").as_posix()
        for path in (run_dir / "original/res").glob("layout*/*.xml")
    )
    file_repairs = {
        xml_file: {
            "baseline": max(before_errors[xml_file] - baseline_errors[xml_file], 0),
            "proposed": max(before_errors[xml_file] - proposed_errors[xml_file], 0),
        }
        for xml_file in xml_files
    }
    path = run_dir / "manual_review.json"
    review = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return normalize_manual_review(review, config["experiment_id"], file_repairs)


def aggregate_review_metric(review, group_name, metric):
    values = [
        file_review[group_name].get(metric)
        for file_review in review.get("files", {}).values()
    ]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def repair_attempt_count(repair_run, status=None):
    attempts = [
        attempt
        for round_state in repair_run.get("rounds", [])
        for attempt in round_state.get("attempts", [])
    ]
    if status is None:
        return len(attempts)
    return sum(attempt.get("status") == status for attempt in attempts)


def experiment_status(raw_status, final_error_count):
    if final_error_count == 0 and raw_status in {
        "completed",
        "completed_with_observations",
        "completed_with_deferred_issues",
    }:
        return "success"
    return raw_status or "unknown"


def build_record_notes(
    xml_file,
    original_issues,
    baseline_issues,
    proposed_issues,
    baseline_status,
    proposed_status,
    run_notes=None,
):
    notes = []
    original_codes = sorted({
        issue.get("code", "UNKNOWN")
        for issue in original_issues
        if issue_file_key(issue) == xml_file
    })
    if original_codes:
        notes.append("initial=" + ",".join(original_codes))
    if baseline_status != "success":
        notes.append("baseline=" + baseline_status)
    if proposed_status != "success":
        notes.append("enhanced=" + proposed_status)
    proposed_review = sorted({
        issue.get("code", "UNKNOWN")
        for issue in proposed_issues
        if issue_file_key(issue) == xml_file
        and issue.get("severity", issue.get("type", "error")) != "error"
    })
    if proposed_review:
        notes.append("review=" + ",".join(proposed_review))
    notes.extend(run_notes or [])
    if not notes and not baseline_issues and not proposed_issues:
        notes.append("no detected findings")
    return "; ".join(notes)


def formal_record_rows(run_dir: Path):
    config = json.loads((run_dir / "experiment_config.json").read_text(encoding="utf-8"))
    comparison = json.loads((run_dir / "comparison_result.json").read_text(encoding="utf-8"))
    original_issues = load_issue_report(
        run_dir / "original/reports/android_xml_a11y_report.json"
    )
    baseline_issues = load_issue_report(
        run_dir / "baseline/reports/android_xml_a11y_report.json"
    )
    proposed_issues = load_issue_report(
        run_dir / "proposed/reports/android_xml_a11y_report.json"
    )
    before_errors = severity_count_by_file(original_issues, "error")
    baseline_errors = severity_count_by_file(baseline_issues, "error")
    proposed_errors = severity_count_by_file(proposed_issues, "error")
    baseline_warnings = severity_count_by_file(baseline_issues, "warning")
    proposed_warnings = severity_count_by_file(proposed_issues, "warning")
    baseline_info = severity_count_by_file(baseline_issues, "info")
    proposed_info = severity_count_by_file(proposed_issues, "info")
    baseline_safety = load_safety_report(
        run_dir / "baseline/reports/android_xml_repair_safety_report.json"
    )
    proposed_safety = load_safety_report(
        run_dir / "proposed/reports/android_xml_repair_safety_report.json"
    )
    baseline_safety_by_file = Counter(issue_file_key(item) for item in baseline_safety)
    proposed_safety_by_file = Counter(issue_file_key(item) for item in proposed_safety)
    review = manual_review_for_run(
        run_dir, config, before_errors, baseline_errors, proposed_errors
    )
    baseline_group = comparison["groups"]["baseline"]
    proposed_group = comparison["groups"]["proposed"]
    repair_run_path = run_dir / "proposed/reports/repair_run.json"
    repair_run = (
        json.loads(repair_run_path.read_text(encoding="utf-8"))
        if repair_run_path.exists()
        else {}
    )
    enhanced_iterations = sum(
        bool(round_state.get("attempts"))
        for round_state in repair_run.get("rounds", [])
    )
    enhanced_model_calls = repair_attempt_count(repair_run)
    rejected_attempts = repair_attempt_count(repair_run, "rejected")
    run_notes = []
    baseline_error_path = run_dir / "baseline/reports/operation_error.txt"
    if baseline_error_path.exists():
        first_line = baseline_error_path.read_text(encoding="utf-8").splitlines()
        if first_line:
            run_notes.append("baseline_error=" + first_line[0])
    if rejected_attempts:
        run_notes.append(
            f"enhanced_model_calls={enhanced_model_calls}; "
            f"rejected_attempts={rejected_attempts}"
        )
    baseline_status = experiment_status(
        baseline_group.get("status"),
        baseline_group["metrics"]["final"]["error_count"],
    )
    proposed_status = experiment_status(
        proposed_group.get("status"),
        proposed_group["metrics"]["final"]["error_count"],
    )
    xml_files = sorted(
        path.relative_to(run_dir / "original/res").as_posix()
        for path in (run_dir / "original/res").glob("layout*/*.xml")
    )
    selected_layouts = set(config.get("layouts", []))
    selected_entry_paths = {}
    for layout_name in selected_layouts:
        candidates = [
            xml_file for xml_file in xml_files
            if Path(xml_file).stem == layout_name
        ]
        if candidates:
            preferred = f"layout/{layout_name}.xml"
            selected_entry_paths[layout_name] = (
                preferred if preferred in candidates else candidates[0]
            )
    return [
        {
            "app_name": config["app_name"],
            "category": config["category"],
            "xml_file": xml_file,
            "interface_role": (
                "entry"
                if selected_entry_paths.get(Path(xml_file).stem) == xml_file
                else "entry_variant"
                if Path(xml_file).stem in selected_layouts
                else "supporting"
            ),
            "before_error_count": before_errors[xml_file],
            "baseline_after_error_count": baseline_errors[xml_file],
            "enhanced_after_error_count": proposed_errors[xml_file],
            "baseline_repair_rate": rate(
                before_errors[xml_file], baseline_errors[xml_file]
            ),
            "enhanced_repair_rate": rate(
                before_errors[xml_file], proposed_errors[xml_file]
            ),
            "baseline_iterations": baseline_group.get("model_calls", 0),
            "enhanced_iterations": enhanced_iterations,
            "baseline_status": baseline_status,
            "enhanced_status": proposed_status,
            "baseline_warning_count": baseline_warnings[xml_file],
            "warning_count": proposed_warnings[xml_file],
            "baseline_info_count": baseline_info[xml_file],
            "info_count": proposed_info[xml_file],
            "baseline_structural_safety_findings": baseline_safety_by_file[xml_file],
            "enhanced_structural_safety_findings": proposed_safety_by_file[xml_file],
            "source_review_status": review["files"][xml_file][
                "source_review_status"
            ],
            "professional_review_status": review["professional_review_status"],
            "baseline_semantic_correct_count": review["files"][xml_file][
                "baseline"
            ]["semantic_correct_count"],
            "baseline_semantic_incorrect_count": review["files"][xml_file][
                "baseline"
            ]["semantic_incorrect_count"],
            "baseline_semantic_pending_count": review["files"][xml_file][
                "baseline"
            ]["semantic_pending_count"],
            "enhanced_semantic_correct_count": review["files"][xml_file][
                "proposed"
            ]["semantic_correct_count"],
            "enhanced_semantic_incorrect_count": review["files"][xml_file][
                "proposed"
            ]["semantic_incorrect_count"],
            "enhanced_semantic_pending_count": review["files"][xml_file][
                "proposed"
            ]["semantic_pending_count"],
            "baseline_unrelated_change_count": review["files"][xml_file][
                "baseline"
            ]["unrelated_change_count"],
            "enhanced_unrelated_change_count": review["files"][xml_file][
                "proposed"
            ]["unrelated_change_count"],
            "baseline_dynamic_semantics_risk_count": review["files"][xml_file][
                "baseline"
            ]["dynamic_semantics_risk_count"],
            "enhanced_dynamic_semantics_risk_count": review["files"][xml_file][
                "proposed"
            ]["dynamic_semantics_risk_count"],
            "notes": build_record_notes(
                xml_file,
                original_issues,
                baseline_issues,
                proposed_issues,
                baseline_status,
                proposed_status,
                run_notes,
            ),
        }
        for xml_file in xml_files
    ]


def formal_app_summary_row(run_dir: Path):
    config = json.loads((run_dir / "experiment_config.json").read_text(encoding="utf-8"))
    comparison = json.loads((run_dir / "comparison_result.json").read_text(encoding="utf-8"))
    original_issues = load_issue_report(
        run_dir / "original/reports/android_xml_a11y_report.json"
    )
    baseline_issues = load_issue_report(
        run_dir / "baseline/reports/android_xml_a11y_report.json"
    )
    proposed_issues = load_issue_report(
        run_dir / "proposed/reports/android_xml_a11y_report.json"
    )
    review = manual_review_for_run(
        run_dir,
        config,
        severity_count_by_file(original_issues, "error"),
        severity_count_by_file(baseline_issues, "error"),
        severity_count_by_file(proposed_issues, "error"),
    )
    before = comparison["original"]["error_count"]
    baseline = comparison["groups"]["baseline"]
    proposed = comparison["groups"]["proposed"]
    baseline_final = baseline["metrics"]["final"]
    proposed_final = proposed["metrics"]["final"]
    return {
        "app_name": config["app_name"],
        "category": config["category"],
        "run_id": config["run_id"],
        "selected_interface_count": len(config.get("layouts", [])),
        "before_error_count": before,
        "baseline_after_error_count": baseline_final["error_count"],
        "enhanced_after_error_count": proposed_final["error_count"],
        "baseline_repair_rate": rate(before, baseline_final["error_count"]),
        "enhanced_repair_rate": rate(before, proposed_final["error_count"]),
        "baseline_model_calls": baseline.get("model_calls", 0),
        "enhanced_model_calls": proposed.get("model_calls", 0),
        "baseline_status": experiment_status(
            baseline.get("status"), baseline_final["error_count"]
        ),
        "enhanced_status": experiment_status(
            proposed.get("status"), proposed_final["error_count"]
        ),
        "baseline_warning_count": baseline_final["warning_count"],
        "enhanced_warning_count": proposed_final["warning_count"],
        "baseline_info_count": baseline_final["info_count"],
        "enhanced_info_count": proposed_final["info_count"],
        "baseline_structural_safety_findings": baseline["metrics"]["safety_findings"],
        "enhanced_structural_safety_findings": proposed["metrics"]["safety_findings"],
        "source_review_status": review.get("source_review_status", "pending"),
        "professional_review_status": review.get(
            "professional_review_status", "pending"
        ),
        "baseline_semantic_correct_count": aggregate_review_metric(
            review, "baseline", "semantic_correct_count"
        ),
        "baseline_semantic_incorrect_count": aggregate_review_metric(
            review, "baseline", "semantic_incorrect_count"
        ),
        "baseline_semantic_pending_count": aggregate_review_metric(
            review, "baseline", "semantic_pending_count"
        ),
        "enhanced_semantic_correct_count": aggregate_review_metric(
            review, "proposed", "semantic_correct_count"
        ),
        "enhanced_semantic_incorrect_count": aggregate_review_metric(
            review, "proposed", "semantic_incorrect_count"
        ),
        "enhanced_semantic_pending_count": aggregate_review_metric(
            review, "proposed", "semantic_pending_count"
        ),
        "baseline_unrelated_change_count": aggregate_review_metric(
            review, "baseline", "unrelated_change_count"
        ),
        "enhanced_unrelated_change_count": aggregate_review_metric(
            review, "proposed", "unrelated_change_count"
        ),
        "baseline_dynamic_semantics_risk_count": aggregate_review_metric(
            review, "baseline", "dynamic_semantics_risk_count"
        ),
        "enhanced_dynamic_semantics_risk_count": aggregate_review_metric(
            review, "proposed", "dynamic_semantics_risk_count"
        ),
        "notes": " | ".join(
            text
            for text in (
                review.get("baseline", {}).get("notes", ""),
                review.get("proposed", {}).get("notes", ""),
            )
            if text
        ),
    }


def rebuild_formal_experiment_records(
    manifest_path: Path,
    output_path: Path,
    app_summary_path: Optional[Path] = None,
):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    app_rows = []
    for record in manifest.get("runs", []):
        if not (
            record.get("protocol_version") == 4
            and record.get("protocol_status") == "valid"
            and record.get("experiment_phase") == "formal"
        ):
            continue
        run_dir = ROOT / record["result_path"]
        rows.extend(formal_record_rows(run_dir))
        app_rows.append(formal_app_summary_row(run_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FORMAL_RECORD_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    app_summary_path = app_summary_path or output_path.with_name(
        "formal_experiment_app_summary.csv"
    )
    with app_summary_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FORMAL_APP_SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(app_rows)
    return rows


def source_commit(source: Path):
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def resource_hash(res_dir: Path):
    digest = hashlib.sha256()
    for path in sorted(res_dir.rglob("*.xml")):
        digest.update(path.relative_to(res_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def baseline_xml_files(res_dir: Path):
    files = sorted(
        path
        for path in res_dir.rglob("*.xml")
        if path.relative_to(res_dir).parts[0].startswith("layout")
    )
    strings = res_dir / "values" / "strings.xml"
    if strings.exists():
        files.append(strings)
    return files


def format_xml_files(files, res_dir: Path):
    sections = []
    for path in files:
        rel = path.relative_to(res_dir).as_posix()
        sections.append(
            f"### res/{rel}\n```xml\n"
            f"{path.read_text(encoding='utf-8')}\n```"
        )
    return "\n\n".join(sections)


def local_tag(tag: str):
    return tag.rsplit("}", 1)[-1].rsplit(".", 1)[-1]


def selector_reference(res_dir: Path):
    lines = []
    for path in baseline_xml_files(res_dir):
        if not path.relative_to(res_dir).parts[0].startswith("layout"):
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue

        def visit(element, selector):
            element_id = element.attrib.get(f"{{{ANDROID_NS}}}id")
            if element_id:
                lines.append(
                    f"- res/{path.relative_to(res_dir).as_posix()} | "
                    f"{element_id} | {selector}"
                )
            counts = Counter()
            for child in list(element):
                name = local_tag(child.tag)
                counts[name] += 1
                visit(child, f"{selector}/{name}[{counts[name]}]")

        visit(root, f"/{local_tag(root.tag)}[1]")
    return "\n".join(lines) or "- No elements with android:id were found."


def build_baseline_prompt(res_dir: Path):
    files = baseline_xml_files(res_dir)
    return f"""You are an Android developer.

Review the Android XML resources below and repair any accessibility problems you identify.
Preserve the original behavior, element types, ids, styles, dimensions, hierarchy, include tags, input restrictions, and resource references.
Make only the smallest necessary changes. Do not rewrite unrelated resources.
Prefer string resources over hardcoded user-facing text.
Do not delete or replace existing resources.
The selector in every element operation must be copied exactly from the selector reference below.
Never use placeholder names such as Root or Child.

Mechanical selector reference (this contains no accessibility findings):

{selector_reference(res_dir)}

Current Android XML resources:

{format_xml_files(files, res_dir)}

Return only a strict JSON object, with no markdown and no explanation:
{{
  "operations": [
    {{
      "op": "set_attribute",
      "path": "res/layout/example.xml",
      "selector": "/LinearLayout[1]/ImageButton[1]",
      "attribute": "android:contentDescription",
      "value": "@string/example_description"
    }},
    {{
      "op": "add_string_resource",
      "path": "res/values/strings.xml",
      "name": "example_description",
      "value": "Example description"
    }}
  ]
}}

Allowed operations are remove_attribute, set_attribute, remove_attribute_value, and add_string_resource.
Do not output complete XML files, new files, deleted files, or deleted resources.
"""


def issue_counts(issues):
    codes = Counter(issue.get("code", "UNKNOWN") for issue in issues)
    repairability = Counter(
        issue.get("repairability", "xml_safe")
        for issue in issues
    )
    errors, warnings, info, total = issue_quality(issues)
    repairable_error_count = sum(
        issue.get("severity", issue.get("type", "error")) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
        for issue in issues
    )
    return {
        "issue_count": errors,
        "error_count": errors,
        "warning_count": warnings,
        "info_count": info,
        "total_issue_count": total,
        "total": total,
        "errors": errors,
        "warnings": warnings,
        "repairable_error_count": repairable_error_count,
        "codes": dict(sorted(codes.items())),
        "repairability": dict(sorted(repairability.items())),
    }


def result_metrics(initial_issues, final_issues, safety_findings):
    initial = issue_counts(initial_issues)
    final = issue_counts(final_issues)
    reduced = initial["error_count"] - final["error_count"]
    initial_repairable = initial["repairable_error_count"]
    final_repairable = final["repairable_error_count"]
    repairable_reduced = initial_repairable - final_repairable
    return {
        "initial": initial,
        "final": final,
        "issues_reduced": reduced,
        "issue_reduction_rate": (
            reduced / initial["error_count"] if initial["error_count"] else None
        ),
        "repair_rate": (
            reduced / initial["error_count"] if initial["error_count"] else None
        ),
        "repairable_issues_reduced": repairable_reduced,
        "repairable_issue_reduction_rate": (
            repairable_reduced / initial_repairable
            if initial_repairable
            else None
        ),
        "safety_findings": len(safety_findings),
    }


def run_baseline(
    original_dir: Path,
    output_dir: Path,
    provider: str,
    model: str,
    api_key,
    detector_profile: str = DEFAULT_DETECTOR_PROFILE,
):
    shutil.copytree(original_dir, output_dir)
    reports = output_dir / "reports"
    prompt = build_baseline_prompt(output_dir / "res")
    write_text(reports / "baseline_prompt.txt", prompt)

    state = {
        "group": "baseline",
        "provider": provider,
        "model": model,
        "uses_rag": False,
        "uses_detector_feedback": False,
        "detector_profile": detector_profile,
        "model_calls": 1,
        "started_at": now_iso(),
        "status": "running",
    }
    try:
        model_result = run_model_with_metadata(provider, model, prompt, api_key)
        response = model_result["content"]
        state["model_call"] = model_result["metadata"]
        state["model_call_summary"] = model_call_summary([
            model_result["metadata"]
        ])
        write_text(reports / "model_response.txt", response)
        try:
            changed = apply_model_result(output_dir, response)
            state["status"] = "completed"
            state["changed_files"] = [
                path.relative_to(output_dir).as_posix() for path in changed
            ]
        except ValueError as exc:
            state["status"] = "invalid_model_output"
            state["operation_error"] = str(exc)
            write_text(reports / "operation_error.txt", str(exc) + "\n")
    except ModelError as exc:
        failed_call = model_error_metadata(exc, provider, model)
        state["status"] = "model_error"
        state["error_type"] = type(exc).__name__
        state["error"] = str(exc)
        state["model_call"] = failed_call
        state["model_call_summary"] = model_call_summary([failed_call])

    final_issues = run_xml_checker(
        output_dir / "res",
        detector_profile=detector_profile,
    )
    safety = validate_repair_safety(original_dir / "res", output_dir / "res")
    save_report(output_dir, final_issues)
    save_safety_report(output_dir, safety)
    state["completed_at"] = now_iso()
    write_json(reports / "baseline_run.json", state)
    return state, final_issues, safety


def run_proposed(
    original_dir: Path,
    output_dir: Path,
    provider: str,
    model: str,
    api_key,
    max_rounds: int,
    max_model_attempts: int,
    rag_limit: int,
    detector_profile: str = DEFAULT_DETECTOR_PROFILE,
):
    command = [
        sys.executable,
        str(ROOT / "tools" / "generate_android_xml.py"),
        str(original_dir),
        str(output_dir),
        "--provider",
        provider,
        "--model",
        model,
        "--max-rounds",
        str(max_rounds),
        "--max-model-attempts",
        str(max_model_attempts),
        "--limit",
        str(rag_limit),
        "--detector-profile",
        detector_profile,
        "--force",
    ]
    if api_key:
        command.extend(["--api-key", api_key])

    started_at = now_iso()
    result = subprocess.run(command, capture_output=True, text=True)
    reports = output_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_text(reports / "runner_stdout.txt", result.stdout)
    write_text(reports / "runner_stderr.txt", result.stderr)

    final_issues = run_xml_checker(
        output_dir / "res",
        detector_profile=detector_profile,
    )
    safety = validate_repair_safety(original_dir / "res", output_dir / "res")
    save_report(output_dir, final_issues)
    save_safety_report(output_dir, safety)
    state = {
        "group": "proposed",
        "provider": provider,
        "model": model,
        "uses_rag": True,
        "uses_detector_feedback": True,
        "max_rounds": max_rounds,
        "max_model_attempts_per_round": max_model_attempts,
        "rag_limit": rag_limit,
        "detector_profile": detector_profile,
        "started_at": started_at,
        "completed_at": now_iso(),
        "return_code": result.returncode,
        "status": "completed" if result.returncode == 0 else "failed",
    }
    repair_run_path = reports / "repair_run.json"
    if repair_run_path.exists():
        repair_run = json.loads(repair_run_path.read_text(encoding="utf-8"))
        model_calls = [
            attempt.get("model_call")
            for round_state in repair_run.get("rounds", [])
            for attempt in round_state.get("attempts", [])
            if attempt.get("model_call")
        ]
        state["model_calls"] = sum(
            len(round_state.get("attempts", []))
            for round_state in repair_run.get("rounds", [])
        )
        state["model_call_summary"] = model_call_summary(model_calls)
        state["completed_round"] = repair_run.get("completed_round")
        state["status"] = repair_run.get("status", state["status"])
    write_json(reports / "proposed_runner.json", state)
    return state, final_issues, safety


def update_manifest(manifest_path: Path, record):
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": 1,
            "experiment": "Android XML accessibility repair comparison",
            "groups": {
                "baseline": "Raw model, one call, no RAG and no detector feedback",
                "proposed": "Same model with RAG and iterative detector feedback",
            },
            "runs": [],
        }
    manifest["current_protocol_version"] = 4
    manifest["formal_target_app_count"] = 40
    manifest["updated_at"] = now_iso()
    manifest["runs"] = [
        item for item in manifest["runs"]
        if item.get("experiment_id") != record["experiment_id"]
    ]
    manifest["runs"].append(record)
    write_json(manifest_path, manifest)


def build_summary(config, comparison):
    baseline = comparison["groups"]["baseline"]["metrics"]
    proposed = comparison["groups"]["proposed"]["metrics"]
    return f"""# Android XML experiment: {config['app_name']}

- Experiment ID: `{config['experiment_id']}`
- Protocol: version {config['protocol_version']} ({config['protocol_status']})
- Source commit: `{config.get('source_commit') or 'unavailable'}`
- Interfaces: {', '.join(config['layouts'])}
- Model: `{config['provider']} / {config['model']}`
- Original errors: {comparison['original']['error_count']}

| Group | Final errors | Warnings | Info | Repairable final | Repairable reduction | Safety findings | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | {baseline['final']['error_count']} | {baseline['final']['warning_count']} | {baseline['final']['info_count']} | {baseline['final']['repairable_error_count']} | {baseline['repairable_issues_reduced']} | {baseline['safety_findings']} | {comparison['groups']['baseline']['status']} |
| Proposed | {proposed['final']['error_count']} | {proposed['final']['warning_count']} | {proposed['final']['info_count']} | {proposed['final']['repairable_error_count']} | {proposed['repairable_issues_reduced']} | {proposed['safety_findings']} | {comparison['groups']['proposed']['status']} |

The manual semantic review is stored in `manual_review.json`.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Run a recorded baseline versus RAG Android XML experiment."
    )
    parser.add_argument("source", help="Android app source directory")
    parser.add_argument("output", help="Experiment run output directory")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--layouts", required=True, help="Comma-separated layout names")
    parser.add_argument("--run-id", default="run_01")
    parser.add_argument("--protocol-version", type=int, default=4)
    parser.add_argument("--protocol-id", default="android_xml_protocol_v4")
    parser.add_argument(
        "--experiment-phase",
        choices=("pilot", "formal"),
        default="formal",
    )
    parser.add_argument(
        "--provider",
        choices=MODEL_PROVIDER_CHOICES,
        default="deepseek",
    )
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--max-model-attempts", type=int, default=3)
    parser.add_argument("--rag-limit", type=int, default=8)
    parser.add_argument(
        "--detector-profile",
        choices=DETECTOR_PROFILE_CHOICES,
        default=DEFAULT_DETECTOR_PROFILE,
    )
    parser.add_argument(
        "--skip-manifest-update",
        action="store_true",
        help="保留完整运行文件，但不写入旧的单模型正式实验索引。",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    layouts = [
        item.strip().removeprefix("@layout/").removesuffix(".xml")
        for item in args.layouts.split(",")
        if item.strip()
    ]
    if len(layouts) not in {2, 3}:
        raise SystemExit("正式实验要求每个 App 选择 2 或 3 个入口 layout。")
    if output.exists():
        if not args.force:
            raise SystemExit(f"实验目录已存在，请使用新的 run-id 或加 --force: {output}")
        shutil.rmtree(output)

    validate_model_configuration(args.provider, args.api_key)
    original = output / "original"
    collect(source, original, selected_layouts=set(layouts))
    initial_issues = run_xml_checker(
        original / "res",
        detector_profile=args.detector_profile,
    )
    save_report(original, initial_issues)

    experiment_id = f"{args.app_id}:{args.run_id}"
    config = {
        "schema_version": 1,
        "protocol_version": args.protocol_version,
        "protocol_id": args.protocol_id,
        "protocol_status": "valid",
        "experiment_phase": args.experiment_phase,
        "experiment_id": experiment_id,
        "run_id": args.run_id,
        "app_id": args.app_id,
        "app_name": args.app_name,
        "category": args.category,
        "source_path": str(source),
        "source_commit": source_commit(source),
        "layouts": layouts,
        "provider": args.provider,
        "model": args.model,
        "model_temperature": (
            None if args.provider == "openai" else 1.0
        ),
        "model_top_p": (
            None if args.provider == "openai" else 1.0
        ),
        "model_max_output_tokens": int(os.environ.get(
            "LLM_MAX_OUTPUT_TOKENS",
            "65536" if args.provider == "deepseek" else "16384",
        )),
        "baseline_model_calls": 1,
        "proposed_max_rounds": args.max_rounds,
        "proposed_max_model_attempts_per_round": args.max_model_attempts,
        "rag_limit": args.rag_limit,
        "detector_profile": args.detector_profile,
        "created_at": now_iso(),
        "input_resource_sha256": resource_hash(original / "res"),
        "api_base_url": {
            "deepseek": os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ),
            "openai": os.environ.get(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ),
            "anthropic": os.environ.get(
                "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
            ),
            "ollama": "ollama CLI",
        }[args.provider],
        "api_style": (
            os.environ.get("OPENAI_API_STYLE", "responses")
            if args.provider == "openai"
            else {
                "deepseek": "chat_completions",
                "anthropic": "messages",
                "ollama": "ollama_cli",
            }[args.provider]
        ),
        "api_streaming": (
            args.provider == "openai"
            and os.environ.get(
                "OPENAI_RESPONSES_STREAM", "false"
            ).strip().casefold() in {"1", "true", "yes", "on"}
        ),
    }
    write_json(output / "experiment_config.json", config)

    baseline_state, baseline_issues, baseline_safety = run_baseline(
        original,
        output / "baseline",
        args.provider,
        args.model,
        args.api_key,
        args.detector_profile,
    )
    proposed_state, proposed_issues, proposed_safety = run_proposed(
        original,
        output / "proposed",
        args.provider,
        args.model,
        args.api_key,
        args.max_rounds,
        args.max_model_attempts,
        args.rag_limit,
        args.detector_profile,
    )

    comparison = {
        "experiment_id": experiment_id,
        "protocol_version": config["protocol_version"],
        "protocol_status": config["protocol_status"],
        "experiment_phase": config["experiment_phase"],
        "completed_at": now_iso(),
        "original": issue_counts(initial_issues),
        "groups": {
            "baseline": {
                "status": baseline_state["status"],
                "model_calls": baseline_state["model_calls"],
                "model_call_summary": baseline_state.get(
                    "model_call_summary", model_call_summary([])
                ),
                "metrics": result_metrics(
                    initial_issues, baseline_issues, baseline_safety
                ),
            },
            "proposed": {
                "status": proposed_state["status"],
                "model_calls": proposed_state.get("model_calls", 0),
                "model_call_summary": proposed_state.get(
                    "model_call_summary", model_call_summary([])
                ),
                "metrics": result_metrics(
                    initial_issues, proposed_issues, proposed_safety
                ),
            },
        },
    }
    write_json(output / "comparison_result.json", comparison)
    write_text(output / "comparison_summary.md", build_summary(config, comparison))
    write_json(
        output / "manual_review.json",
        build_manual_review(
            experiment_id,
            {
                xml_file: {
                    "baseline": max(
                        severity_count_by_file(initial_issues, "error")[xml_file]
                        - severity_count_by_file(baseline_issues, "error")[xml_file],
                        0,
                    ),
                    "proposed": max(
                        severity_count_by_file(initial_issues, "error")[xml_file]
                        - severity_count_by_file(proposed_issues, "error")[xml_file],
                        0,
                    ),
                }
                for xml_file in sorted(
                    path.relative_to(original / "res").as_posix()
                    for path in (original / "res").glob("layout*/*.xml")
                )
            },
        ),
    )

    manifest_record = {
        "experiment_id": experiment_id,
        "protocol_version": config["protocol_version"],
        "protocol_status": config["protocol_status"],
        "experiment_phase": config["experiment_phase"],
        "run_id": args.run_id,
        "app_id": args.app_id,
        "app_name": args.app_name,
        "category": args.category,
        "provider": args.provider,
        "model": args.model,
        "layouts": layouts,
        "source_commit": config["source_commit"],
        "input_resource_sha256": config["input_resource_sha256"],
        "result_path": str(output.relative_to(ROOT)),
        "original_issues": comparison["original"]["error_count"],
        "original_repairable_issues": comparison["original"]["repairable_error_count"],
        "baseline_final_issues": comparison["groups"]["baseline"]["metrics"]["final"]["error_count"],
        "baseline_final_repairable_issues": comparison["groups"]["baseline"]["metrics"]["final"]["repairable_error_count"],
        "proposed_final_issues": comparison["groups"]["proposed"]["metrics"]["final"]["error_count"],
        "proposed_final_repairable_issues": comparison["groups"]["proposed"]["metrics"]["final"]["repairable_error_count"],
        "baseline_status": baseline_state["status"],
        "proposed_status": proposed_state["status"],
        "baseline_model_calls": baseline_state["model_calls"],
        "proposed_model_calls": proposed_state.get("model_calls", 0),
        "baseline_model_call_summary": baseline_state.get(
            "model_call_summary", model_call_summary([])
        ),
        "proposed_model_call_summary": proposed_state.get(
            "model_call_summary", model_call_summary([])
        ),
        "manual_review_status": "pending",
        "completed_at": comparison["completed_at"],
    }
    if not args.skip_manifest_update:
        manifest_path = (
            ROOT / "experiments" / "android_xml" / "experiment_manifest.json"
        )
        update_manifest(manifest_path, manifest_record)
        rebuild_formal_experiment_records(
            manifest_path,
            ROOT / "experiments" / "android_xml" / "formal_experiment_records.csv",
        )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
