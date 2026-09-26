#!/usr/bin/env python3
"""Prepare and verify the untouched 13-App external V2 extension matrix."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import run_android_xml_v2_rag_experiment as runner  # noqa: E402
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    recorded_path,
    sha256_file,
)
from tools.run_android_xml_v2_final_test import (  # noqa: E402
    collect_test_package,
)


DATASET_ROOT = ROOT / "outputs/v2_dataset/v2.1_external_extension"
EXTERNAL_CSV = DATASET_ROOT / "external_xml_safe_candidates.csv"
DATASET_METADATA = DATASET_ROOT / "external_dataset_metadata.json"
DATASET_CHECKSUMS = DATASET_ROOT / "checksums.sha256"
PROTOCOL_PATH = (
    ROOT
    / "experiments/android_xml_v2_external_extension/"
    "protocol_v2_1_external.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_v2_external_extension/"
    "top2_matrix"
)
ORIGINAL_IMPLEMENTATION_HASHES = runner.implementation_hashes


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_checksums() -> dict[str, str]:
    rows = {}
    for line in DATASET_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        rows[name] = digest
    return rows


def verify_external_dataset_files() -> tuple[dict, list[dict]]:
    metadata = load_json(DATASET_METADATA)
    protocol = load_json(PROTOCOL_PATH)
    dataset = protocol["dataset"]
    errors = []
    checksums = expected_checksums()
    if metadata.get("status") != "frozen":
        errors.append("external extension is not frozen")
    for path, key in (
        (EXTERNAL_CSV, "candidate_csv_sha256"),
        (DATASET_METADATA, "metadata_sha256"),
    ):
        expected = dataset[key]
        if sha256_file(path) != expected:
            errors.append(f"registered hash mismatch: {path.name}")
        if checksums.get(path.name) != expected:
            errors.append(f"checksum manifest mismatch: {path.name}")
    hard_checks = metadata.get("hard_checks", {})
    failed_checks = sorted(
        name for name, passed in hard_checks.items() if passed is not True
    )
    if failed_checks:
        errors.append("external hard checks failed: " + ", ".join(failed_checks))
    rows = runner.load_csv(EXTERNAL_CSV)
    if len({row["repository_url"] for row in rows}) != dataset["external_app_count"]:
        errors.append("external app count changed")
    if len(rows) != dataset["xml_safe_candidate_count"]:
        errors.append("external candidate count changed")
    task_count = len({
        (row["repository_url"], row["xml_path"]) for row in rows
    })
    if task_count != dataset["repair_task_count"]:
        errors.append("external repair task count changed")
    for row in rows:
        if (
            row.get("dataset_split") != "external_test"
            or row.get("candidate_role") != "xml_safe"
            or row.get("severity") != "error"
            or row.get("confidence") != "high"
            or row.get("xml_safe") != "true"
            or row.get("consistency_status") != "passed"
        ):
            errors.append(
                f"{row.get('candidate_id', 'unknown')}: invalid external row"
            )
    if errors:
        raise SystemExit(
            "External V2 extension validation failed:\n- "
            + "\n- ".join(errors)
        )
    metadata = dict(metadata)
    metadata["dataset_sha256"] = dataset["candidate_csv_sha256"]
    return metadata, rows


def implementation_hashes() -> dict:
    paths = {
        "matrix_preparer": Path(__file__).resolve(),
        "shared_rag_runner": ROOT / "tools/run_android_xml_v2_rag_experiment.py",
        "protocol": PROTOCOL_PATH,
        "external_candidates": EXTERNAL_CSV,
        "external_metadata": DATASET_METADATA,
        "knowledge": ROOT / "knowledge/rag/knowledge_documents.json",
        "retriever": ROOT / "tools/retrieval/v2_hybrid.py",
        "prompt_contract": ROOT / "tools/android_xml_rag_prompt_contract.py",
        "detector": ROOT / "tools/evaluation/android_xml_a11y_check.py",
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


def configure_runner() -> None:
    runner.DEVELOPMENT_CSV = EXTERNAL_CSV
    runner.DATASET_METADATA = DATASET_METADATA
    runner.DATASET_CHECKSUMS = DATASET_CHECKSUMS
    runner.PROTOCOL_PATH = PROTOCOL_PATH
    runner.RAG_TOP_K_VALUES = (2,)
    runner.CONDITIONS = ("no_rag", "rag_topk2")
    runner.verify_dataset_files = verify_external_dataset_files
    runner.implementation_hashes = implementation_hashes
    runner.collect = collect_test_package


def finalize_prepared_output(output: Path) -> dict:
    manifest_path = output / "frozen_manifest.json"
    manifest = load_json(manifest_path)
    metadata = load_json(DATASET_METADATA)
    manifest.update({
        "status": "external_inputs_frozen",
        "dataset_version": metadata["dataset_version"],
        "dataset_split": "external_test",
        "test_set_loaded": False,
        "external_app_count": manifest.pop("development_app_count"),
        "selection_policy": metadata["selection_policy"],
        "isolation_hard_checks": metadata["hard_checks"],
        "external_candidate_csv_sha256": sha256_file(EXTERNAL_CSV),
        "external_metadata_sha256": sha256_file(DATASET_METADATA),
    })
    runner.write_json(manifest_path, manifest)
    source_tasks = output / "development_tasks.csv"
    external_tasks = output / "external_tasks.csv"
    if source_tasks.exists():
        source_tasks.replace(external_tasks)
    return {
        "status": manifest["status"],
        "external_apps": manifest["external_app_count"],
        "repair_tasks": manifest["task_count"],
        "xml_safe_candidates": manifest["candidate_count"],
        "prepared_condition_runs": manifest["condition_run_count"],
        "model_calls": 0,
        "conditions": manifest["conditions"],
        "output": str(output.resolve()),
    }


def prepare(output: Path, force: bool) -> dict:
    configure_runner()
    args = argparse.Namespace(output=output, force=force)
    runner.prepare(args)
    return finalize_prepared_output(output)


def verify(output: Path) -> dict:
    configure_runner()
    errors = runner.validate_freeze(output)
    manifest_path = output / "frozen_manifest.json"
    if not manifest_path.is_file():
        errors.append("external frozen manifest missing")
    else:
        manifest = load_json(manifest_path)
        if manifest.get("status") != "external_inputs_frozen":
            errors.append("external matrix status is not frozen")
        if manifest.get("dataset_split") != "external_test":
            errors.append("external matrix split changed")
        if manifest.get("model_calls") != 0:
            errors.append("external preparation unexpectedly called a model")
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "model_calls": 0,
        "output": str(output.resolve()),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    prepare_parser.add_argument("--force", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


def main() -> None:
    args = parser().parse_args()
    output = args.output.resolve()
    if args.command == "prepare":
        result = prepare(output, args.force)
    else:
        result = verify(output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
