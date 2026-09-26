#!/usr/bin/env python3
"""Summarize V1 findings and define evidence-bounded V2 repair candidates."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = (
    ROOT
    / "experiments/android_xml_multimodel/runs/formal/deepseek_v4_pro/rep_01"
)
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_design/scope"

SCOPE_DECISIONS = {
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME": (
        "keep_v1_auto_when_xml_safe",
        True,
        "Keep only high-confidence interactive controls; use App context to infer the action label.",
    ),
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT": (
        "keep_v1_auto_when_xml_safe",
        True,
        "Keep stable label/hint repair and retrieve nearby field purpose when wording is ambiguous.",
    ),
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": (
        "v2_internal_pilot_candidate",
        False,
        "Pilot only for explicitly interactive elements with focusable=false and no conflicting focus policy.",
    ),
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": (
        "v2_internal_pilot_candidate",
        True,
        "Replacement text requires field semantics from strings, nearby labels, and source code.",
    ),
    "ANDROID_XML_UNNAMED_FOCUSABLE_CONTAINER": (
        "v2_internal_pilot_candidate",
        False,
        "Pilot removal of redundant focus only for non-interactive containers without descendants that rely on it.",
    ),
    "ANDROID_XML_TOUCH_TARGET_TOO_SMALL": (
        "v2_internal_pilot_candidate",
        False,
        "Pilot minWidth/minHeight only when dimensions are explicit and layout safety checks remain clean.",
    ),
    "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION": (
        "app_context_research_then_manual",
        True,
        "Retrieve drawable, neighboring text, and controller code; do not auto-commit before semantic validation.",
    ),
    "ANDROID_XML_IMAGE_SEMANTICS_REQUIRES_REVIEW": (
        "keep_manual_review",
        True,
        "XML alone cannot distinguish meaningful and decorative images reliably.",
    ),
    "ANDROID_XML_LOW_TEXT_CONTRAST": (
        "keep_manual_review",
        False,
        "Theme overlays, state lists, and runtime backgrounds can change effective contrast.",
    ),
    "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW": (
        "source_context_research_then_manual",
        True,
        "Kotlin/Java accessibility behavior is required before deciding on a repair.",
    ),
    "ANDROID_XML_NON_SEMANTIC_CLICKABLE": (
        "keep_structure_or_runtime",
        True,
        "Replacing widget semantics can alter hierarchy, interaction, styling, or runtime behavior.",
    ),
    "ANDROID_XML_PROGRESS_MISSING_STATUS_LABEL": (
        "keep_runtime_review",
        True,
        "Status announcements depend on runtime updates and nearby dynamic text.",
    ),
}

FIELDS = [
    "code",
    "issue_count",
    "app_count",
    "error_count",
    "warning_count",
    "info_count",
    "xml_safe_count",
    "manual_review_count",
    "requires_structure_or_code_count",
    "top_components",
    "v2_decision",
    "requires_app_context",
    "rationale",
]


def read_findings(run_root):
    findings = []
    reports = sorted(
        Path(run_root).glob("*/original/reports/android_xml_a11y_report.json")
    )
    for report in reports:
        payload = json.loads(report.read_text(encoding="utf-8"))
        for issue in payload.get("issues", []):
            findings.append((report.parts[-4], issue))
    return reports, findings


def scope_rows(findings):
    grouped = defaultdict(list)
    for app_name, issue in findings:
        grouped[issue.get("code", "UNKNOWN")].append((app_name, issue))
    rows = []
    for code, values in grouped.items():
        severity = Counter(
            issue.get("severity", "error") for _, issue in values
        )
        repairability = Counter(
            issue.get("repairability", "xml_safe") for _, issue in values
        )
        components = Counter(
            issue.get("component") or issue.get("element") or "unknown"
            for _, issue in values
        )
        decision, requires_context, rationale = SCOPE_DECISIONS.get(
            code,
            (
                "unclassified_requires_review",
                True,
                "No V2 decision has been frozen for this finding type.",
            ),
        )
        rows.append({
            "code": code,
            "issue_count": len(values),
            "app_count": len({app_name for app_name, _ in values}),
            "error_count": severity["error"],
            "warning_count": severity["warning"],
            "info_count": severity["info"],
            "xml_safe_count": repairability["xml_safe"],
            "manual_review_count": repairability["manual_review"],
            "requires_structure_or_code_count": repairability[
                "requires_structure_or_code"
            ],
            "top_components": "; ".join(
                f"{name}:{count}" for name, count in components.most_common(5)
            ),
            "v2_decision": decision,
            "requires_app_context": requires_context,
            "rationale": rationale,
        })
    return sorted(rows, key=lambda row: (-row["issue_count"], row["code"]))


def write_outputs(output, reports, findings, rows):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "finding_scope.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": 1,
        "analysis_id": "android_xml_v2_scope_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_app_count": len(reports),
        "finding_count": len(findings),
        "finding_type_count": len(rows),
        "severity_counts": dict(Counter(
            issue.get("severity", "error") for _, issue in findings
        )),
        "repairability_counts": dict(Counter(
            issue.get("repairability", "xml_safe") for _, issue in findings
        )),
        "decision_counts": dict(Counter(row["v2_decision"] for row in rows)),
        "rows": rows,
    }
    json_path = output / "finding_scope.json"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Android XML V2 Finding Scope",
        "",
        f"- Frozen V1 Apps: {len(reports)}",
        f"- Initial findings: {len(findings)}",
        f"- Finding types: {len(rows)}",
        "- Scope decisions are design inputs, not new detector behavior.",
        "",
        "| Finding | Count | Errors | XML-safe | Apps | V2 decision |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['code']} | {row['issue_count']} | {row['error_count']} | "
            f"{row['xml_safe_count']} | {row['app_count']} | "
            f"{row['v2_decision']} |"
        )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "V2 candidates remain non-formal until they pass deterministic safety tests and a five-App internal pilot. Manual/runtime categories must not be promoted merely to increase the automated repair count.",
        "",
    ])
    (output / "finding_scope.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return csv_path, json_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    reports, findings = read_findings(args.run_root)
    if len(reports) != 40:
        raise SystemExit(f"Expected 40 frozen App reports, found {len(reports)}")
    rows = scope_rows(findings)
    csv_path, json_path = write_outputs(args.output, reports, findings, rows)
    print(json.dumps({
        "apps": len(reports),
        "findings": len(findings),
        "types": len(rows),
        "csv": csv_path.relative_to(ROOT).as_posix(),
        "json": json_path.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
