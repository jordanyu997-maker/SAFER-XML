#!/usr/bin/env python3
"""Build a type-targeted Android XML sample pool without model outcomes."""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLONE_ROOT = Path("fdroid_apps/selected_xml_apps")
DEFAULT_METADATA = ROOT / "reports/fdroid_screening_v3/app_screening.json"
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_dataset_redesign/targeted_sample_pool_expanded_v2"
)
TARGET_CODES = (
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING",
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING",
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY",
)
REVIEW_CODES = (
    "ANDROID_XML_TOUCH_TARGET_TOO_SMALL",
    "ANDROID_XML_LOW_TEXT_CONTRAST",
    "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION",
    "ANDROID_XML_NON_SEMANTIC_CLICKABLE",
    "ANDROID_XML_PROGRESS_MISSING_STATUS_LABEL",
    "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW",
)

sys.path.insert(0, str(ROOT))

from tools.analyze_android_xml_dataset_coverage import (  # noqa: E402
    issue_severity,
    metadata_maps,
    ranked_screen_candidates,
    scan_candidate_pool,
)
from tools.dataset.fdroid_app_screening import relative_to_repo  # noqa: E402


def is_actionable(issue):
    return (
        issue_severity(issue) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
    )


def issue_key(row):
    return (
        row["app_name"],
        row["issue_layout_path"],
        row["selector"],
        row["code"],
        row["severity"],
        row["repairability"],
    )


def select_owning_screen(containing_screens, issue_relative_path):
    """Prefer the XML file that physically contains the finding."""
    direct = [
        item
        for item in containing_screens
        if item.relative_path == issue_relative_path
    ]
    pool = direct or containing_screens
    return min(
        pool,
        key=lambda item: (-item.score, item.name, item.relative_path),
    )


def audit_repository(repo, metadata, detector_profile):
    candidates = ranked_screen_candidates(repo, 100000)
    if not candidates:
        return []
    issues_by_signature, candidate_issues = scan_candidate_pool(
        repo,
        candidates,
        detector_profile=detector_profile,
    )
    screens_by_signature = defaultdict(list)
    for candidate in candidates:
        for signature in candidate_issues[candidate.relative_path]:
            screens_by_signature[signature].append(candidate)

    rows = []
    app_name = metadata.get("name", repo.name)
    category = metadata.get("category", "Unknown")
    for signature, issue in issues_by_signature.items():
        code = issue.get("code", "UNKNOWN")
        if code not in TARGET_CODES and code not in REVIEW_CODES:
            continue
        containing_screens = screens_by_signature.get(signature, [])
        if not containing_screens:
            continue
        issue_path = Path(issue.get("file", ""))
        issue_relative_path = relative_to_repo(issue_path, repo)
        screen = select_owning_screen(containing_screens, issue_relative_path)
        rows.append({
            "app_id": metadata.get("app_id", repo.name),
            "app_name": app_name,
            "category": category,
            "repo_url": metadata.get("repo_url", ""),
            "source_path": str(repo.resolve()),
            "screen_name": screen.name,
            "screen_path": screen.relative_path,
            "screen_score": screen.score,
            "screen_reasons": "; ".join(screen.reasons),
            "issue_layout_path": issue_relative_path,
            "code": code,
            "severity": issue_severity(issue),
            "repairability": issue.get("repairability", "xml_safe"),
            "actionable": is_actionable(issue),
            "component": issue.get("component") or issue.get("element", ""),
            "selector": issue.get("selector", ""),
            "confidence": issue.get("confidence", ""),
            "requires_review": issue.get("requires_review", True),
            "message": issue.get("message", ""),
        })
    unique = {}
    for row in rows:
        key = issue_key(row)
        current = unique.get(key)
        if current is None or row["screen_score"] > current["screen_score"]:
            unique[key] = row
    return sorted(
        unique.values(),
        key=lambda row: (
            row["code"],
            row["app_name"].casefold(),
            row["issue_layout_path"],
            row["selector"],
        ),
    )


def app_candidates(rows, code):
    by_app = defaultdict(list)
    for row in rows:
        if row["code"] == code and row["actionable"]:
            by_app[row["app_name"]].append(row)
    candidates = []
    for app_name, findings in by_app.items():
        candidates.append({
            "app_id": findings[0]["app_id"],
            "app_name": app_name,
            "category": findings[0]["category"],
            "source_path": findings[0]["source_path"],
            "finding_count": len(findings),
            "screen_count": len({row["screen_path"] for row in findings}),
            "screens": sorted({row["screen_path"] for row in findings}),
            "max_screen_score": max(row["screen_score"] for row in findings),
        })
    return sorted(
        candidates,
        key=lambda item: (
            -item["finding_count"],
            -item["screen_count"],
            -item["max_screen_score"],
            item["app_name"].casefold(),
        ),
    )


def select_quota_apps(
    candidates,
    min_apps=5,
    min_findings=10,
    max_apps=10,
    max_per_category=2,
):
    selected = []
    remaining = list(candidates)
    category_counts = Counter()

    while remaining and len(selected) < max_apps:
        need_more = (
            len(selected) < min_apps
            or sum(item["finding_count"] for item in selected) < min_findings
        )
        if not need_more:
            break
        eligible = [
            item for item in remaining
            if category_counts[item["category"]] < max_per_category
        ]
        if not eligible:
            eligible = remaining
        chosen = eligible[0]
        selected.append(chosen)
        category_counts[chosen["category"]] += 1
        remaining.remove(chosen)
    return selected


def summarize_type(rows, code, min_apps, min_findings):
    all_rows = [row for row in rows if row["code"] == code]
    actionable = [row for row in all_rows if row["actionable"]]
    apps = app_candidates(rows, code)
    selected = select_quota_apps(
        apps,
        min_apps=min_apps,
        min_findings=min_findings,
    )
    app_count = len({row["app_name"] for row in actionable})
    finding_count = len(actionable)
    return {
        "code": code,
        "actionable_finding_count": finding_count,
        "actionable_app_count": app_count,
        "actionable_screen_count": len({
            (row["app_name"], row["screen_path"]) for row in actionable
        }),
        "warning_or_info_count": len(all_rows) - finding_count,
        "category_count": len({row["category"] for row in actionable}),
        "app_quota": min_apps,
        "finding_quota": min_findings,
        "app_gap": max(min_apps - app_count, 0),
        "finding_gap": max(min_findings - finding_count, 0),
        "quota_met": app_count >= min_apps and finding_count >= min_findings,
        "selected_quota_apps": selected,
        "all_actionable_apps": apps,
    }


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(output, rows, repository_count, detector_profile, min_apps, min_findings):
    output.mkdir(parents=True, exist_ok=True)
    fields = [
        "app_id", "app_name", "category", "repo_url", "source_path",
        "screen_name", "screen_path", "screen_score", "screen_reasons",
        "issue_layout_path", "code", "severity", "repairability",
        "actionable", "component", "selector", "confidence",
        "requires_review", "message",
    ]
    write_csv(output / "targeted_issue_instances.csv", rows, fields)

    summaries = [
        summarize_type(rows, code, min_apps, min_findings)
        for code in TARGET_CODES
    ]
    summary_rows = [
        {key: value for key, value in summary.items()
         if key not in {"selected_quota_apps", "all_actionable_apps"}}
        for summary in summaries
    ]
    write_csv(
        output / "issue_type_sample_summary.csv",
        summary_rows,
        list(summary_rows[0]),
    )
    payload = {
        "schema_version": 1,
        "pool_id": f"android_xml_targeted_sample_pool_{detector_profile}",
        "status": "candidate_requires_source_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "detector_profile": detector_profile,
        "repository_count": repository_count,
        "selection_uses_model_outputs": False,
        "minimum_apps_per_type": min_apps,
        "minimum_findings_per_type": min_findings,
        "target_types": summaries,
    }
    (output / "targeted_app_candidates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Android XML Targeted Sample Pool",
        "",
        f"- Detector profile: `{detector_profile}`",
        f"- Repositories scanned: {repository_count}",
        "- Model outputs used: no",
        f"- Per-type quota: {min_apps} Apps and {min_findings} findings",
        "",
        "| Finding code | Findings | Apps | Screens | Categories | App gap | Finding gap | Quota met |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for summary in summaries:
        lines.append(
            f"| `{summary['code']}` | {summary['actionable_finding_count']} | "
            f"{summary['actionable_app_count']} | {summary['actionable_screen_count']} | "
            f"{summary['category_count']} | {summary['app_gap']} | "
            f"{summary['finding_gap']} | {'yes' if summary['quota_met'] else 'no'} |"
        )
    lines.extend([
        "",
        "Only `severity=error` and `repairability=xml_safe` findings count toward the automatic-repair quota. Warnings and info are retained in the instance CSV for later review but do not satisfy the quota.",
        "",
    ])
    (output / "targeted_sample_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone-root", type=Path, default=DEFAULT_CLONE_ROOT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--detector-profile", default="expanded_v2")
    parser.add_argument("--min-apps-per-type", type=int, default=5)
    parser.add_argument("--min-findings-per-type", type=int, default=10)
    args = parser.parse_args()

    by_path, by_name = metadata_maps(args.metadata)
    repos = sorted(
        path for path in args.clone_root.iterdir()
        if path.is_dir() and (path / ".git").exists()
    )
    rows = []
    for index, repo in enumerate(repos, 1):
        metadata = (
            by_path.get(str(repo.resolve()))
            or by_name.get(repo.name.casefold())
            or {}
        )
        rows.extend(audit_repository(repo, metadata, args.detector_profile))
        if index % 10 == 0 or index == len(repos):
            print(f"[{index}/{len(repos)}] targeted full-layout scan")
    rows.sort(key=lambda row: (
        row["code"],
        row["app_name"].casefold(),
        row["issue_layout_path"],
        row["selector"],
    ))
    payload = write_outputs(
        args.output,
        rows,
        len(repos),
        args.detector_profile,
        args.min_apps_per_type,
        args.min_findings_per_type,
    )
    met = sum(item["quota_met"] for item in payload["target_types"])
    print(json.dumps({
        "repositories": len(repos),
        "target_types": len(payload["target_types"]),
        "types_meeting_quota": met,
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
