#!/usr/bin/env python3
"""Verify and prepare the registered V2.2 formal experiment matrix."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.run_android_xml_experiment import build_baseline_prompt  # noqa: E402
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    recorded_path,
    sha256_file,
    tree_digest,
)


PROTOCOL_PATH = ROOT / "experiments/android_xml_v2_formal/protocol_v2_2.json"
RESULT_LOCK_PATH = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "FINAL_TEST_RESULT_LOCK.json"
)
SOURCE_MATRIX = ROOT / "experiments/android_xml_v2_rag/test_v2_1/matrix"
SOURCE_MANIFEST = SOURCE_MATRIX / "frozen_manifest.json"
SOURCE_PROMPTS = SOURCE_MATRIX / "frozen_prompts"
SOURCE_BOUNDARY = SOURCE_MATRIX / "boundary_gate.csv"
DEFAULT_OUTPUT = (
    ROOT / "experiments/android_xml_v2_formal/multimodel_v2_2/prepared"
)
GROUPS = ("raw_baseline", "full_enhanced")

TASK_FIELDS = (
    "model_key",
    "model",
    "provider",
    "task_id",
    "app_name",
    "screen_name",
    "candidate_count",
    "candidate_ids",
    "group",
    "minimum_model_calls",
    "maximum_model_calls",
    "input_package",
    "input_resource_sha256",
    "initial_prompt_sha256",
    "output_path",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict], fields=TASK_FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def implementation_hashes() -> dict:
    paths = {
        "preparer": Path(__file__).resolve(),
        "formal_runner": ROOT / "tools/run_android_xml_v2_formal_study.py",
        "protocol": PROTOCOL_PATH,
        "result_lock": RESULT_LOCK_PATH,
        "source_manifest": SOURCE_MANIFEST,
        "detector": ROOT / "tools/evaluation/android_xml_a11y_check.py",
        "baseline_prompt": ROOT / "tools/run_android_xml_experiment.py",
        "rag_prompt_contract": ROOT / "tools/android_xml_rag_prompt_contract.py",
        "retriever": ROOT / "tools/retrieval/v2_hybrid.py",
        "knowledge": ROOT / "knowledge/rag/knowledge_documents.json",
        "operation_executor": ROOT / "tools/generate_android_xml.py",
        "operation_contract": ROOT / "tools/android_xml_contract_v2_1.py",
    }
    return {
        name: {
            "path": recorded_path(path),
            "sha256": sha256_file(path),
        }
        for name, path in paths.items()
    }


def verify_result_lock() -> list[str]:
    errors = []
    if not RESULT_LOCK_PATH.is_file():
        return ["completed RAG Test result lock is missing"]
    lock = load_json(RESULT_LOCK_PATH)
    if lock.get("status") != "locked":
        errors.append("completed RAG Test result is not locked")
    for relative, expected in lock.get("locked_files", {}).items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"locked result file missing: {relative}")
        elif sha256_file(path) != expected:
            errors.append(f"locked result file changed: {relative}")
    return errors


def verify_registered_inputs() -> tuple[dict, dict, list[str]]:
    errors = verify_result_lock()
    protocol = load_json(PROTOCOL_PATH)
    source = load_json(SOURCE_MANIFEST)
    dataset = protocol["dataset"]
    if protocol.get("status") != "registered_before_model_execution":
        errors.append("formal protocol is not registered")
    if sha256_file(SOURCE_MANIFEST) != dataset["source_manifest_sha256"]:
        errors.append("frozen source manifest changed")
    if source.get("dataset_sha256") != dataset["dataset_sha256"]:
        errors.append("frozen dataset hash differs from formal protocol")
    expected_counts = {
        "task_count": dataset["repair_task_count"],
        "candidate_count": dataset["xml_safe_candidate_count"],
        "boundary_candidate_count": dataset["boundary_candidate_count"],
        "repair_app_count": dataset["repair_app_count"],
    }
    for key, expected in expected_counts.items():
        if source.get(key) != expected:
            errors.append(
                f"source manifest {key} changed: "
                f"{source.get(key)} != {expected}"
            )
    if sha256_file(
        ROOT / dataset["eligibility_exclusions"]
    ) != dataset["eligibility_exclusions_sha256"]:
        errors.append("eligibility exclusions changed")
    if sha256_file(SOURCE_BOUNDARY) != source["boundary_gate_sha256"]:
        errors.append("boundary gate changed")
    if tuple(protocol["main_comparison"]["groups"]) != GROUPS:
        errors.append("registered main-comparison groups changed")

    seen = set()
    for task in source.get("tasks", []):
        task_id = task["task_id"]
        if task_id in seen:
            errors.append(f"duplicate frozen task: {task_id}")
        seen.add(task_id)
        package = ROOT / task["input_package"]
        if not package.is_dir():
            errors.append(f"frozen input package missing: {task_id}")
        elif tree_digest(package / "res") != task["input_resource_sha256"]:
            errors.append(f"frozen input package changed: {task_id}")
        prompt = SOURCE_PROMPTS / task_id / "rag_topk2_prompt.txt"
        expected_prompt = task["prompt_sha256"]["rag_topk2"]
        if not prompt.is_file():
            errors.append(f"frozen RAG prompt missing: {task_id}")
        elif sha256_file(prompt) != expected_prompt:
            errors.append(f"frozen RAG prompt changed: {task_id}")
    return protocol, source, errors


def group_order(model_key: str, task_id: str) -> tuple[str, str]:
    digest = int(
        hashlib.sha256(f"{model_key}|{task_id}".encode()).hexdigest(),
        16,
    )
    return GROUPS if digest % 2 == 0 else tuple(reversed(GROUPS))


def task_call_bounds(protocol: dict, group: str) -> tuple[int, int]:
    settings = protocol["main_comparison"]["groups"][group]
    if group == "raw_baseline":
        return 1, 1
    rounds = int(settings["max_semantic_rounds"])
    attempts = int(settings["max_format_correction_attempts_per_round"])
    return 1, rounds * attempts


def initial_prompt(task: dict, group: str) -> tuple[str, str]:
    if group == "raw_baseline":
        package = ROOT / task["input_package"]
        prompt = build_baseline_prompt(package / "res")
        return prompt, text_sha256(prompt)
    path = SOURCE_PROMPTS / task["task_id"] / "rag_topk2_prompt.txt"
    return path.read_text(encoding="utf-8"), sha256_file(path)


def build_execution_rows(protocol: dict, source: dict) -> list[dict]:
    rows = []
    output_root = ROOT / protocol["execution"]["output_root"]
    for model in protocol["models"]:
        for task in source["tasks"]:
            for group in group_order(model["key"], task["task_id"]):
                minimum, maximum = task_call_bounds(protocol, group)
                _, prompt_hash = initial_prompt(task, group)
                rows.append({
                    "model_key": model["key"],
                    "model": model["model"],
                    "provider": model["provider"],
                    "task_id": task["task_id"],
                    "app_name": task["app_name"],
                    "screen_name": task["screen_name"],
                    "candidate_count": task["candidate_count"],
                    "candidate_ids": ";".join(task["candidate_ids"]),
                    "group": group,
                    "minimum_model_calls": minimum,
                    "maximum_model_calls": maximum,
                    "input_package": task["input_package"],
                    "input_resource_sha256": task["input_resource_sha256"],
                    "initial_prompt_sha256": prompt_hash,
                    "output_path": recorded_path(
                        output_root
                        / "runs"
                        / model["key"]
                        / task["task_id"]
                        / group
                    ),
                })
    return rows


def verify() -> dict:
    protocol, source, errors = verify_registered_inputs()
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "model_count": len(protocol["models"]),
        "repair_task_count": source["task_count"],
        "xml_safe_candidate_count": source["candidate_count"],
        "boundary_candidate_count": source["boundary_candidate_count"],
        "planned_group_runs": (
            len(protocol["models"]) * source["task_count"] * len(GROUPS)
        ),
        "model_calls": 0,
    }


def prepare(output: Path, force: bool = False) -> dict:
    protocol, source, errors = verify_registered_inputs()
    if errors:
        raise SystemExit(
            "V2 formal study validation failed:\n- " + "\n- ".join(errors)
        )
    if output.exists() and any(output.iterdir()):
        if not force:
            raise SystemExit(
                f"prepared output already exists: {output}; use --force"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    rows = build_execution_rows(protocol, source)
    tasks_path = output / "formal_tasks.csv"
    write_csv(tasks_path, rows)
    shutil.copy2(SOURCE_BOUNDARY, output / "boundary_gate.csv")

    minimum_calls = sum(int(row["minimum_model_calls"]) for row in rows)
    maximum_calls = sum(int(row["maximum_model_calls"]) for row in rows)
    plan = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "status": "prepared_no_model_execution",
        "dataset_version": source["dataset_version"],
        "dataset_sha256": source["dataset_sha256"],
        "model_count": len(protocol["models"]),
        "models": [
            {
                key: model[key]
                for key in ("key", "display_name", "provider", "model")
            }
            for model in protocol["models"]
        ],
        "groups": list(GROUPS),
        "repair_task_count": source["task_count"],
        "xml_safe_candidate_count": source["candidate_count"],
        "repair_app_count": source["repair_app_count"],
        "boundary_candidate_count": source["boundary_candidate_count"],
        "condition_run_count": len(rows),
        "minimum_model_calls": minimum_calls,
        "maximum_model_calls": maximum_calls,
        "actual_model_calls": 0,
        "boundary_model_calls": 0,
        "tasks_csv": recorded_path(tasks_path),
    }
    write_json(output / "formal_execution_plan.json", plan)

    manifest = {
        **plan,
        "implementation_hashes": implementation_hashes(),
        "formal_tasks_sha256": sha256_file(tasks_path),
        "boundary_gate_sha256": sha256_file(output / "boundary_gate.csv"),
        "source_result_lock": recorded_path(RESULT_LOCK_PATH),
        "source_result_lock_sha256": sha256_file(RESULT_LOCK_PATH),
        "input_isolation": {
            "fresh_copy_per_model_group_task": True,
            "cross_group_output_access": False,
            "cross_model_output_access": False,
            "previous_test_output_in_prompt": False,
        },
    }
    write_json(output / "formal_manifest.json", manifest)
    return plan


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    prepare_parser.add_argument("--force", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "verify":
        result = verify()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["errors"]:
            raise SystemExit(1)
    else:
        result = prepare(args.output.resolve(), args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
