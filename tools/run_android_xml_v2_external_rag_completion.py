#!/usr/bin/env python3
"""Complete the locked one-call RAG comparison on the 13 new Apps."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import prepare_android_xml_v2_external_matrix as external  # noqa: E402
from tools import run_android_xml_v2_rag_experiment as runner  # noqa: E402
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    now_iso,
    recorded_path,
    sha256_file,
    write_json,
)


MATRIX = external.DEFAULT_OUTPUT
EXTERNAL_RESULTS = MATRIX / "development_results.csv"
EXTERNAL_RESULT_LOCK = MATRIX / "EXTERNAL_RESULT_LOCK.json"
BASE_RESULTS = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "matrix/test_results.csv"
)
BASE_RESULT_LOCK = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "FINAL_TEST_RESULT_LOCK.json"
)
COMBINED_ROOT = (
    ROOT
    / "experiments/android_xml_v2_ablation/deepseek_v2_3/"
    "equal_budget_40app"
)
COMBINED_RESULTS = COMBINED_ROOT / "equal_budget_results.csv"
COMBINED_LOCK = COMBINED_ROOT / "EQUAL_BUDGET_RESULT_LOCK.json"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def validate_rows(rows: list[dict], expected_tasks: int, expected_candidates: int) -> list[str]:
    errors = []
    conditions = {"no_rag", "rag_topk2"}
    if len(rows) != expected_tasks * 2:
        errors.append(
            f"result row count is {len(rows)}, expected {expected_tasks * 2}"
        )
    if {
        row.get("group") for row in rows
    } != conditions:
        errors.append("result conditions are not No-RAG and RAG Top-2")
    keys = {(row["task_id"], row["group"]) for row in rows}
    if len(keys) != len(rows):
        errors.append("result rows contain duplicate task conditions")
    if any(row["status"] == "infrastructure_failed" for row in rows):
        errors.append("result rows contain infrastructure failures")
    for condition in conditions:
        selected = [row for row in rows if row["group"] == condition]
        if len(selected) != expected_tasks:
            errors.append(f"{condition} task count changed")
        before = sum(
            int(row["before_candidate_error_count"]) for row in selected
        )
        if before != expected_candidates:
            errors.append(
                f"{condition} candidate denominator is {before}, "
                f"expected {expected_candidates}"
            )
    return errors


def lock_external_results() -> dict:
    rows = read_csv(EXTERNAL_RESULTS)
    errors = validate_rows(rows, 36, 43)
    if errors:
        raise SystemExit(
            "External equal-budget result validation failed:\n- "
            + "\n- ".join(errors)
        )
    states = {}
    for path in sorted(MATRIX.glob("runs/*/*/reports/v2_rag_run.json")):
        states[recorded_path(path)] = sha256_file(path)
    if len(states) != 72:
        raise SystemExit(
            f"external state count is {len(states)}, expected 72"
        )
    lock = {
        "schema_version": 1,
        "status": "locked",
        "locked_at": now_iso(),
        "app_count": 13,
        "task_count": 36,
        "candidate_count": 43,
        "condition_run_count": 72,
        "conditions": ["no_rag", "rag_topk2"],
        "results": recorded_path(EXTERNAL_RESULTS),
        "results_sha256": sha256_file(EXTERNAL_RESULTS),
        "state_files": states,
    }
    write_json(EXTERNAL_RESULT_LOCK, lock)
    return lock


def combine_results() -> dict:
    base = read_csv(BASE_RESULTS)
    external_rows = read_csv(EXTERNAL_RESULTS)
    base_errors = validate_rows(base, 74, 93)
    external_errors = validate_rows(external_rows, 36, 43)
    if base_errors or external_errors:
        raise SystemExit(
            "40-App equal-budget merge validation failed:\n- "
            + "\n- ".join(base_errors + external_errors)
        )
    rows = base + external_rows
    errors = validate_rows(rows, 110, 136)
    if errors:
        raise SystemExit(
            "Combined equal-budget result validation failed:\n- "
            + "\n- ".join(errors)
        )
    app_count = len({row["app_name"] for row in rows})
    if app_count != 40:
        raise SystemExit(
            f"combined result has {app_count} App names, expected 40"
        )
    write_csv(COMBINED_RESULTS, rows, runner.SUMMARY_FIELDS)
    lock = {
        "schema_version": 1,
        "status": "locked",
        "locked_at": now_iso(),
        "app_count": 40,
        "task_count": 110,
        "candidate_count": 136,
        "condition_run_count": 220,
        "conditions": ["no_rag", "rag_topk2"],
        "base_partition": {
            "result_lock": recorded_path(BASE_RESULT_LOCK),
            "result_lock_sha256": sha256_file(BASE_RESULT_LOCK),
            "task_count": 74,
            "candidate_count": 93,
        },
        "external_partition": {
            "result_lock": recorded_path(EXTERNAL_RESULT_LOCK),
            "result_lock_sha256": sha256_file(EXTERNAL_RESULT_LOCK),
            "task_count": 36,
            "candidate_count": 43,
        },
        "results": recorded_path(COMBINED_RESULTS),
        "results_sha256": sha256_file(COMBINED_RESULTS),
    }
    write_json(COMBINED_LOCK, lock)
    return lock


def verify() -> dict:
    external.configure_runner()
    errors = runner.validate_freeze(MATRIX)
    result = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "external_apps": 13,
        "external_tasks": 36,
        "external_candidates": 43,
        "planned_condition_runs": 72,
        "model_calls": 0,
    }
    return result


def run() -> dict:
    external.configure_runner()
    errors = runner.validate_freeze(MATRIX)
    if errors:
        raise SystemExit(
            "External matrix validation failed:\n- " + "\n- ".join(errors)
        )
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("missing API key environment: DEEPSEEK_API_KEY")
    args = argparse.Namespace(
        output=MATRIX,
        resume=True,
        tasks=None,
        provider="deepseek",
        model="deepseek-v4-pro",
        api_key=api_key,
    )
    runner.run(args)
    external_lock = lock_external_results()
    combined_lock = combine_results()
    return {
        "status": "completed_and_locked",
        "external_condition_runs": external_lock["condition_run_count"],
        "combined_apps": combined_lock["app_count"],
        "combined_tasks": combined_lock["task_count"],
        "combined_candidates": combined_lock["candidate_count"],
        "combined_condition_runs": combined_lock["condition_run_count"],
        "infrastructure_failed": 0,
        "combined_results": recorded_path(COMBINED_RESULTS),
    }


def main() -> None:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    subparsers = argument_parser.add_subparsers(
        dest="command",
        required=True,
    )
    subparsers.add_parser("verify")
    subparsers.add_parser("run")
    args = argument_parser.parse_args()
    result = verify() if args.command == "verify" else run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
