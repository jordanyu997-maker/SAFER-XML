#!/usr/bin/env python3
"""Analyze V2 source-prescreen candidate balance and dataset gaps."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.common import (  # noqa: E402
    CORE_ISSUE_TYPES,
    load_config,
    read_csv,
    write_csv,
)


def _eligible(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("selection_status") == "candidate"]


def distribution_rows(high: list[dict], review: list[dict], boundary: list[dict], config: dict) -> list[dict]:
    targets = config["dataset_targets"]
    rows = []
    for issue_type in CORE_ISSUE_TYPES:
        high_rows = [row for row in _eligible(high) if row["issue_type"] == issue_type]
        review_rows = [row for row in review if row["issue_type"] == issue_type]
        boundary_rows = [row for row in _eligible(boundary) if row["issue_type"] == issue_type]
        all_rows = high_rows + boundary_rows
        app_count = len({row["repository_url"] or row["package_name"] for row in all_rows})
        rows.append({
            "issue_type": issue_type,
            "high_xml_safe_count": len(high_rows),
            "boundary_count": len(boundary_rows),
            "review_required_count": len(review_rows),
            "candidate_app_count": app_count,
            "candidate_xml_count": len({(row["repository_url"], row["xml_path"]) for row in all_rows}),
            "minimum_instance_target": targets["min_instances_per_type"],
            "minimum_app_target": targets["min_apps_per_type"],
            "instance_gap": max(targets["min_instances_per_type"] - len(all_rows), 0),
            "app_gap": max(targets["min_apps_per_type"] - app_count, 0),
            "quota_met": len(all_rows) >= targets["min_instances_per_type"] and app_count >= targets["min_apps_per_type"],
        })
    return rows


def difficulty_rows(high: list[dict], boundary: list[dict]) -> list[dict]:
    rows = _eligible(high) + _eligible(boundary)
    counts = Counter(row["difficulty"] for row in rows)
    total = len(rows)
    return [
        {"difficulty": level, "count": counts[level], "ratio": round(counts[level] / total, 6) if total else 0.0}
        for level in ("easy", "medium", "hard", "boundary")
    ]


def app_contribution_rows(high: list[dict], boundary: list[dict]) -> list[dict]:
    rows = _eligible(high) + _eligible(boundary)
    by_app = defaultdict(list)
    for row in rows:
        by_app[(row["package_name"], row["app_name"], row["repository_url"])].append(row)
    total = len(rows)
    result = []
    for (package_name, app_name, repository_url), app_rows in by_app.items():
        result.append({
            "package_name": package_name,
            "app_name": app_name,
            "repository_url": repository_url,
            "candidate_count": len(app_rows),
            "candidate_ratio": round(len(app_rows) / total, 6) if total else 0.0,
            "xml_count": len({row["xml_path"] for row in app_rows}),
            "issue_type_count": len({row["issue_type"] for row in app_rows}),
        })
    return sorted(result, key=lambda row: (-row["candidate_count"], row["app_name"].casefold()))


def gap_rows(
    high: list[dict],
    boundary: list[dict],
    repository_rows: list[dict],
    xml_rows: list[dict],
    issue_distribution: list[dict],
    config: dict,
) -> list[dict]:
    targets = config["dataset_targets"]
    high_rows = _eligible(high)
    boundary_rows = _eligible(boundary)
    all_rows = high_rows + boundary_rows
    app_count = len({row["repository_url"] or row["package_name"] for row in all_rows})
    xml_count = len({(row["repository_url"], row["xml_path"]) for row in all_rows})
    issue_types = sum(row["quota_met"] for row in issue_distribution)
    easy_count = sum(row["difficulty"] == "easy" for row in all_rows)
    easy_ratio = easy_count / len(all_rows) if all_rows else 0.0
    app_counts = Counter(row["repository_url"] or row["package_name"] for row in all_rows)
    max_app_ratio = max(app_counts.values(), default=0) / len(all_rows) if all_rows else 0.0
    metrics = [
        ("candidate_apps", app_count, targets["target_apps_min"], targets["target_apps_max"], "apps contributing eligible high or boundary candidates"),
        ("candidate_xml", xml_count, targets["target_xml_min"], targets["target_xml_max"], "unique repository and XML pairs"),
        ("candidate_issues", len(all_rows), targets["target_issues_min"], targets["target_issues_max"], "high XML-safe plus boundary candidates"),
        ("xml_safe_issues", len(high_rows), targets["target_xml_safe_min"], targets["target_xml_safe_max"], "formal high-confidence XML-safe candidates"),
        ("boundary_issues", len(boundary_rows), targets["target_boundary_min"], targets["target_boundary_max"], "excluded from XML-safe repair-rate denominator"),
        ("balanced_issue_types", issue_types, targets["target_issue_types"], len(CORE_ISSUE_TYPES), "types meeting both instance and App quotas"),
    ]
    rows = []
    for metric, current, minimum, maximum, notes in metrics:
        rows.append({
            "metric": metric,
            "current": current,
            "minimum_target": minimum,
            "maximum_target": maximum,
            "gap_to_minimum": max(minimum - current, 0),
            "status": "met" if minimum <= current <= maximum else "below" if current < minimum else "above",
            "notes": notes,
        })
    rows.extend([
        {
            "metric": "max_app_contribution_ratio",
            "current": round(max_app_ratio, 6),
            "minimum_target": 0,
            "maximum_target": targets["max_app_contribution_ratio"],
            "gap_to_minimum": 0,
            "status": "met" if max_app_ratio <= targets["max_app_contribution_ratio"] else "above",
            "notes": "must be at most the configured maximum",
        },
        {
            "metric": "easy_issue_ratio",
            "current": round(easy_ratio, 6),
            "minimum_target": 0,
            "maximum_target": targets["max_easy_issue_ratio"],
            "gap_to_minimum": 0,
            "status": "met" if easy_ratio <= targets["max_easy_issue_ratio"] else "above",
            "notes": "must be at most the configured maximum",
        },
        {
            "metric": "repositories_inventory",
            "current": len(repository_rows),
            "minimum_target": 0,
            "maximum_target": "",
            "gap_to_minimum": 0,
            "status": "informational",
            "notes": f"{sum(row.get('source_classification') == 'traditional_xml' for row in repository_rows)} contain traditional layout XML",
        },
        {
            "metric": "xml_inventory_scanned",
            "current": len(xml_rows),
            "minimum_target": 0,
            "maximum_target": "",
            "gap_to_minimum": 0,
            "status": "informational",
            "notes": "XML summaries are emitted only for scanned repositories",
        },
    ])
    return rows


def write_analysis(
    output_root: Path,
    high: list[dict],
    review: list[dict],
    boundary: list[dict],
    repository_rows: list[dict],
    xml_rows: list[dict],
    config: dict,
) -> dict:
    issue_rows = distribution_rows(high, review, boundary, config)
    difficulties = difficulty_rows(high, boundary)
    app_rows = app_contribution_rows(high, boundary)
    gaps = gap_rows(high, boundary, repository_rows, xml_rows, issue_rows, config)
    write_csv(output_root / "issue_type_distribution.csv", issue_rows, list(issue_rows[0]))
    write_csv(output_root / "difficulty_distribution.csv", difficulties, list(difficulties[0]))
    write_csv(output_root / "app_contribution_distribution.csv", app_rows, list(app_rows[0]) if app_rows else ["package_name", "app_name", "repository_url", "candidate_count", "candidate_ratio", "xml_count", "issue_type_count"])
    write_csv(output_root / "dataset_gap_report.csv", gaps, list(gaps[0]))
    return {
        "eligible_high_xml_safe": len(_eligible(high)),
        "review_required": len(review),
        "eligible_boundary": len(_eligible(boundary)),
        "issue_types_meeting_quota": sum(row["quota_met"] for row in issue_rows),
        "all_minimum_targets_met": all(row["status"] in {"met", "informational"} for row in gaps),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    high = read_csv(args.output_root / "high_confidence_candidates.csv")
    review = read_csv(args.output_root / "review_required_candidates.csv")
    boundary = read_csv(args.output_root / "boundary_candidates.csv")
    repositories = read_csv(args.output_root / "repository_summary.csv")
    xml_rows = read_csv(args.output_root / "xml_summary.csv")
    result = write_analysis(args.output_root, high, review, boundary, repositories, xml_rows, config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
