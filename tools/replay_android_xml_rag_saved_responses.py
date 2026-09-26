#!/usr/bin/env python3
"""Replay frozen RAG experiment responses under the current safe executor."""
import argparse
import csv
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT
    / "experiments/android_xml_rag_contribution/equal_budget_v4_confirmation_20"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_rag_contribution/v4_1_zero_call_replay"
)
GROUPS = ("no_rag", "rag")
FIELDS = [
    "task_id",
    "group",
    "status",
    "before_target_error_count",
    "after_target_error_count",
    "before_error_count",
    "after_error_count",
    "safety_finding_count",
    "changed_files",
    "source_response_sha256",
    "notes",
]


sys.path.insert(0, str(ROOT))


from tools.generate_android_xml import (  # noqa: E402
    error_count,
    evaluate_and_commit_candidate,
    prepare_output,
    run_xml_checker,
    validate_repair_safety,
)
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    target_issues,
    validate_pilot_operation_scope,
)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replay_one(source, task, group):
    input_package = (ROOT / task["input_package"]).resolve()
    response_path = source / "runs" / task["task_id"] / group / "reports/model_response.txt"
    response = response_path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
        output = (Path(temp) / "package").resolve()
        prepare_output(input_package, output, force=True)
        before = run_xml_checker(output / "res", detector_profile="expanded_v3")
        selected_before = target_issues(before, task)
        status = "replayed"
        notes = ""
        changed = []
        try:
            validate_pilot_operation_scope(response, selected_before, output / "res")
            changed, after = evaluate_and_commit_candidate(
                output,
                input_package / "res",
                before,
                response,
                detector_profile="expanded_v3",
            )
        except (ValueError, ET.ParseError) as exc:
            status = "rejected"
            notes = str(exc)
            after = before
        selected_after = target_issues(after, task)
        safety = validate_repair_safety(input_package / "res", output / "res")
        return {
            "task_id": task["task_id"],
            "group": group,
            "status": status,
            "before_target_error_count": len(selected_before),
            "after_target_error_count": len(selected_after),
            "before_error_count": error_count(before),
            "after_error_count": error_count(after),
            "safety_finding_count": len(safety),
            "changed_files": ";".join(
                path.relative_to(output).as_posix() for path in changed
            ),
            "source_response_sha256": sha256_file(response_path),
            "notes": notes,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    manifest = json.loads(
        (source / "frozen_manifest.json").read_text(encoding="utf-8")
    )

    records = []
    total = len(manifest["tasks"]) * len(GROUPS)
    index = 0
    for task in manifest["tasks"]:
        for group in GROUPS:
            index += 1
            print(f"[{index}/{total}] {task['task_id']} / {group}")
            records.append(replay_one(source, task, group))

    output.mkdir(parents=True, exist_ok=True)
    with (output / "replay_results.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)

    summary = {}
    for group in GROUPS:
        rows = [record for record in records if record["group"] == group]
        before = sum(record["before_target_error_count"] for record in rows)
        after = sum(record["after_target_error_count"] for record in rows)
        summary[group] = {
            "task_count": len(rows),
            "target_errors_before": before,
            "target_errors_after": after,
            "repair_rate": (before - after) / before if before else None,
            "complete_task_count": sum(
                record["after_target_error_count"] == 0 for record in rows
            ),
            "rejected_task_count": sum(
                record["status"] == "rejected" for record in rows
            ),
            "safety_finding_count": sum(
                record["safety_finding_count"] for record in rows
            ),
        }
    payload = {
        "schema_version": 1,
        "replay_id": "android_xml_rag_v4_1_zero_call_replay",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": True,
        "model_calls": 0,
        "source_experiment": str(source),
        "source_manifest_sha256": sha256_file(source / "frozen_manifest.json"),
        "summary": summary,
    }
    (output / "replay_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
