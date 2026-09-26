#!/usr/bin/env python3
"""Verify checksums, frozen dataset shape, and exclusion of run outputs."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    failures = []
    for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing: {relative}")
        elif sha256(path) != expected:
            failures.append(f"checksum: {relative}")

    tasks_path = ROOT / "experiments/android_xml_v2_formal/multimodel_v2_3_40app/prepared/formal_tasks.csv"
    with tasks_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    models = {row["model_key"] for row in rows}
    tasks = {row["task_id"] for row in rows}
    groups = {row["group"] for row in rows}
    if len(rows) != 660 or len(models) != 3 or len(tasks) != 110 or groups != {"raw_baseline", "full_enhanced"}:
        failures.append(
            f"registered task matrix shape: rows={len(rows)} models={len(models)} tasks={len(tasks)} groups={sorted(groups)}"
        )

    manifest_path = ROOT / "experiments/android_xml_v2_formal/multimodel_v2_3_40app/source_matrix/frozen_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_shape = {
        "repair_app_count": 40,
        "task_count": 110,
        "candidate_count": 136,
        "boundary_candidate_count": 30,
    }
    for key, expected in expected_shape.items():
        if manifest.get(key) != expected:
            failures.append(f"frozen manifest {key}: {manifest.get(key)!r} != {expected}")

    excluded_outputs = [
        "data/archives/ablation_details.tar.gz",
        "data/archives/formal_run_details.tar.gz",
        "experiments/android_xml_v2_formal/multimodel_v2_3_40app/formal_results.csv",
        "experiments/android_xml_v2_formal/multimodel_v2_3_40app/run_manifest.json",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/boundary_ablation_results.csv",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/repair_ablation_results.csv",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/run_manifest.json",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/equal_budget_40app/equal_budget_results.csv",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/equal_budget_40app/EQUAL_BUDGET_RESULT_LOCK.json",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/prepared/reference_full_enhanced.csv",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/prepared/reference_single_pass.csv",
        "experiments/android_xml_v2_ablation/deepseek_v2_3/prepared/reference_full_state_lock.json",
    ]
    failures.extend(
        f"excluded output is present: {relative}"
        for relative in excluded_outputs
        if (ROOT / relative).exists()
    )

    if failures:
        raise SystemExit("Verification failed:\n- " + "\n- ".join(failures))
    print(
        "OK: checksums verified; frozen public artifact contains "
        f"{manifest['repair_app_count']} apps and {manifest['task_count']} tasks; "
        "recorded outputs are absent."
    )


if __name__ == "__main__":
    main()
