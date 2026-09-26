#!/usr/bin/env python3
"""Prepare, verify, or run the frozen V2.1 final Test comparison."""
import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import run_android_xml_v2_rag_experiment as runner
from tools.android_xml_contract_v2_1 import (
    CONTRACT_VERSION,
    evaluate_and_commit_candidate,
)
from tools.generate import MODEL_PROVIDER_CHOICES
from tools.evaluation.collect_android_xml_package import (
    RESOURCE_DIR_PREFIXES,
    find_res_dir,
    included_layout_names,
    layout_name,
)
from tools.run_android_xml_rag_pilot import recorded_path, sha256_file


TEST_CSV = ROOT / "outputs/v2_dataset/v2.0.0/v2_test.csv"
DATASET_METADATA = ROOT / "outputs/v2_dataset/v2.0.0/v2_dataset_metadata.json"
DATASET_CHECKSUMS = ROOT / "outputs/v2_dataset/v2.0.0/v2_checksums.sha256"
PROTOCOL_PATH = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/protocol_test_v2_1.json"
)
ELIGIBILITY_EXCLUSIONS = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "test_eligibility_exclusions.csv"
)
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_rag/test_v2_1/matrix"
ORIGINAL_IMPLEMENTATION_HASHES = runner.implementation_hashes
UNRESOLVED_INCLUDE_RECORDS = []


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_locked_file_hashes(protocol: dict) -> list[str]:
    errors = []
    for name, expected in protocol["development_lock"]["files"].items():
        path = ROOT / name
        if not path.is_file():
            errors.append(f"locked Development file missing: {name}")
        elif sha256_file(path) != expected:
            errors.append(f"locked Development file changed: {name}")
    return errors


def verify_test_dataset_files() -> tuple[dict, list[dict]]:
    metadata = load_json(DATASET_METADATA)
    protocol = load_json(PROTOCOL_PATH)
    errors = []
    if metadata.get("status") != "frozen":
        errors.append("V2 dataset is not frozen")
    if metadata.get("dataset_sha256") != protocol["dataset"]["dataset_sha256"]:
        errors.append("V2 dataset hash differs from the Test protocol")
    checksums = {}
    for line in DATASET_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        checksums[name] = digest
    for path in (TEST_CSV, DATASET_METADATA):
        expected = checksums.get(path.name)
        if not expected or sha256_file(path) != expected:
            errors.append(f"dataset checksum mismatch: {path.name}")
    errors.extend(verify_locked_file_hashes(protocol))
    expected_exclusion_hash = protocol["eligibility_audit"][
        "exclusions_sha256"
    ]
    if (
        not ELIGIBILITY_EXCLUSIONS.is_file()
        or sha256_file(ELIGIBILITY_EXCLUSIONS) != expected_exclusion_hash
    ):
        errors.append("pre-model Test eligibility exclusions changed")
    if errors:
        raise SystemExit("V2 final Test validation failed:\n- " + "\n- ".join(errors))
    rows = runner.load_csv(TEST_CSV)
    if any(row.get("dataset_split") != "test" for row in rows):
        raise SystemExit("V2 Test CSV contains a non-test row")
    exclusion_rows = runner.load_csv(ELIGIBILITY_EXCLUSIONS)
    excluded_ids = {row["candidate_id"] for row in exclusion_rows}
    frozen_ids = {row["candidate_id"] for row in rows}
    if not excluded_ids <= frozen_ids:
        raise SystemExit("Test eligibility audit contains unknown candidate IDs")
    eligible_rows = [
        row for row in rows if row["candidate_id"] not in excluded_ids
    ]
    return metadata, eligible_rows


def test_implementation_hashes() -> dict:
    hashes = ORIGINAL_IMPLEMENTATION_HASHES()
    extension = ROOT / "tools/android_xml_contract_v2_1.py"
    hashes.update({
        "final_test_runner": {
            "path": recorded_path(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "operation_contract_extension": {
            "path": recorded_path(extension),
            "sha256": sha256_file(extension),
            "version": CONTRACT_VERSION,
        },
    })
    for name, digest in load_json(PROTOCOL_PATH)["development_lock"][
        "files"
    ].items():
        hashes[f"development_lock:{name}"] = {
            "path": name,
            "sha256": digest,
        }
    return hashes


def collect_test_package(
    source,
    output,
    force=False,
    selected_layouts=None,
):
    """Collect available XML while recording unresolved dependency includes."""
    res_dir = find_res_dir(Path(source))
    available = {}
    for path in res_dir.rglob("*.xml"):
        name = layout_name(path, res_dir)
        if name:
            available.setdefault(name, []).append(path)
    requested = set(selected_layouts or [])
    missing_entries = requested - set(available)
    if missing_entries:
        raise FileNotFoundError(
            "找不到入口 layout 资源："
            + ", ".join(f"@layout/{name}" for name in sorted(missing_entries))
        )

    resolved = set()
    missing_includes = set()
    pending = list(requested)
    while pending:
        name = pending.pop()
        if name in resolved or name in missing_includes:
            continue
        paths = available.get(name)
        if not paths:
            missing_includes.add(name)
            continue
        resolved.add(name)
        for path in paths:
            pending.extend(
                included_layout_names(path) - resolved - missing_includes
            )

    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()) and not force:
        raise FileExistsError(f"输出目录已存在且非空：{output}。如需覆盖请加 --force。")
    output.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(res_dir.rglob("*.xml")):
        if path.name == ".DS_Store" or "/build/" in path.as_posix():
            continue
        relative = path.relative_to(res_dir)
        top_dir = relative.parts[0] if relative.parts else ""
        if not top_dir.startswith(RESOURCE_DIR_PREFIXES):
            continue
        if top_dir.startswith("layout") and requested and path.stem not in resolved:
            continue
        target = output / "res" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(target)

    if missing_includes:
        UNRESOLVED_INCLUDE_RECORDS.append({
            "source_res": recorded_path(res_dir),
            "entry_layouts": sorted(requested),
            "unresolved_includes": sorted(missing_includes),
            "policy": "preserved_reference_no_synthetic_resource",
        })
    return res_dir, copied


def configure_runner() -> None:
    runner.DEVELOPMENT_CSV = TEST_CSV
    runner.PROTOCOL_PATH = PROTOCOL_PATH
    runner.RAG_TOP_K_VALUES = (2,)
    runner.CONDITIONS = ("no_rag", "rag_topk2")
    runner.verify_dataset_files = verify_test_dataset_files
    runner.evaluate_and_commit_candidate = evaluate_and_commit_candidate
    runner.implementation_hashes = test_implementation_hashes
    runner.collect = collect_test_package


def finalize_prepared_output(output: Path) -> dict:
    manifest_path = output / "frozen_manifest.json"
    manifest = load_json(manifest_path)
    protocol = load_json(PROTOCOL_PATH)
    manifest.update({
        "status": "test_inputs_frozen",
        "dataset_split": "test",
        "test_set_loaded": True,
        "test_model_execution_completed": False,
        "test_app_count": manifest.pop("development_app_count"),
        "development_lock": protocol["development_lock"],
        "eligibility_audit": protocol["eligibility_audit"],
        "unresolved_include_records": list(UNRESOLVED_INCLUDE_RECORDS),
    })
    runner.write_json(manifest_path, manifest)
    development_tasks = output / "development_tasks.csv"
    test_tasks = output / "test_tasks.csv"
    if development_tasks.exists():
        development_tasks.replace(test_tasks)
    return {
        "status": manifest["status"],
        "test_apps": manifest["test_app_count"],
        "repair_apps": manifest["repair_app_count"],
        "boundary_apps": manifest["boundary_app_count"],
        "repair_tasks": manifest["task_count"],
        "xml_safe_candidates": manifest["candidate_count"],
        "boundary_candidates": manifest["boundary_candidate_count"],
        "prepared_condition_runs": manifest["condition_run_count"],
        "model_calls": 0,
        "conditions": manifest["conditions"],
        "output": str(output.resolve()),
    }


def verify_prepared_output(output: Path) -> dict:
    errors = runner.validate_freeze(output)
    manifest_path = output / "frozen_manifest.json"
    if not manifest_path.is_file():
        errors.append("frozen Test manifest missing")
    else:
        manifest = load_json(manifest_path)
        if manifest.get("dataset_split") != "test":
            errors.append("frozen manifest is not Test")
        if manifest.get("test_set_loaded") is not True:
            errors.append("Test load state is not recorded")
        if manifest.get("test_model_execution_completed") is not False:
            errors.append("Test execution state is invalid before model run")
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "test_set_loaded": True,
        "model_calls": 0,
        "output": str(output.resolve()),
    }


def finalize_run_output(output: Path) -> dict:
    source_results = output / "development_results.csv"
    test_results = output / "test_results.csv"
    if source_results.exists():
        source_results.replace(test_results)
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest.update({
        "status": "final_test_executed",
        "dataset_split": "test",
        "test_set_loaded": True,
        "test_model_execution_completed": True,
        "summary": recorded_path(test_results),
        "development_lock": load_json(PROTOCOL_PATH)["development_lock"],
    })
    runner.write_json(manifest_path, manifest)
    return {
        "status": manifest["status"],
        "group_runs": manifest["condition_run_count"],
        "completed_group_runs": manifest["completed_condition_runs"],
        "infrastructure_failed": (
            manifest["infrastructure_failed_condition_runs"]
        ),
        "test_set_loaded": True,
        "summary": str(test_results.resolve()),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        subparser.add_argument("--force", action="store_true")
        subparser.add_argument("--resume", action="store_true")
        subparser.add_argument(
            "--tasks",
            type=lambda value: [
                item.strip() for item in value.split(",") if item.strip()
            ],
        )
        subparser.add_argument(
            "--provider",
            choices=MODEL_PROVIDER_CHOICES,
            default="deepseek",
        )
        subparser.add_argument("--model", default="deepseek-v4-pro")
        subparser.add_argument("--api-key", default=None)
    return result


def main() -> None:
    args = parser().parse_args()
    args.output = args.output.resolve()
    configure_runner()
    if args.command == "prepare":
        runner.prepare(args)
        result = finalize_prepared_output(args.output)
    elif args.command == "verify":
        result = verify_prepared_output(args.output)
        if result["errors"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(1)
    else:
        runner.run(args)
        result = finalize_run_output(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
