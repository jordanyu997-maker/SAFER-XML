#!/usr/bin/env python3
"""Upgrade formal Android XML manual-review files to schema version 2."""
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from tools.run_android_xml_experiment import (
    ROOT,
    manual_review_for_run,
    severity_count_by_file,
    load_issue_report,
    write_json,
)


def migrate_run(run_dir: Path):
    config = json.loads((run_dir / "experiment_config.json").read_text(encoding="utf-8"))
    original = load_issue_report(
        run_dir / "original/reports/android_xml_a11y_report.json"
    )
    baseline = load_issue_report(
        run_dir / "baseline/reports/android_xml_a11y_report.json"
    )
    proposed = load_issue_report(
        run_dir / "proposed/reports/android_xml_a11y_report.json"
    )
    review = manual_review_for_run(
        run_dir,
        config,
        severity_count_by_file(original, "error"),
        severity_count_by_file(baseline, "error"),
        severity_count_by_file(proposed, "error"),
    )
    write_json(run_dir / "manual_review.json", review)


def main():
    manifest_path = ROOT / "experiments/android_xml/experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    migrated = 0
    for record in manifest.get("runs", []):
        run_dir = ROOT / record["result_path"]
        required = (
            run_dir / "experiment_config.json",
            run_dir / "original/reports/android_xml_a11y_report.json",
            run_dir / "baseline/reports/android_xml_a11y_report.json",
            run_dir / "proposed/reports/android_xml_a11y_report.json",
        )
        if not all(path.exists() for path in required):
            continue
        migrate_run(run_dir)
        migrated += 1
    print(f"Migrated {migrated} review records.")


if __name__ == "__main__":
    main()
