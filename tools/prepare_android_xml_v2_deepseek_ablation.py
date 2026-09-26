#!/usr/bin/env python3
"""Prepare the registered DeepSeek V2.3 component ablation study."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.build_v2_frozen_dataset import (  # noqa: E402
    candidate_selector,
    element_candidates,
)
from tools import run_android_xml_v2_40app_formal_study as formal40  # noqa: E402
from tools import run_android_xml_v2_formal_study as formal  # noqa: E402
from tools import prepare_android_xml_v2_formal_study as base_formal_preparer  # noqa: E402
from tools import run_android_xml_v2_rag_experiment as v2  # noqa: E402
from tools.android_xml_rag_prompt_contract import (  # noqa: E402
    audit_prompt_pair,
    build_prompt_pair,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    all_attrs,
    apply_explicit_styles,
    load_style_resources,
)
from tools.generate_android_xml import (  # noqa: E402
    issue_severity,
    run_xml_checker,
    save_report,
)
from tools.prepare_android_xml_v2_40app_formal_study import (  # noqa: E402
    SOURCE_MANIFEST,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    now_iso,
    prune_entrypoint_variants,
    recorded_path,
    sha256_file,
    tree_digest,
    write_json,
)
from tools.run_android_xml_v2_final_test import (  # noqa: E402
    collect_test_package,
)


FORMAL_ROOT = (
    ROOT
    / "experiments/android_xml_v2_formal/"
    "multimodel_v2_3_40app"
)
FORMAL_RESULTS = FORMAL_ROOT / "formal_results.csv"
FORMAL_RUNS = FORMAL_ROOT / "runs/deepseek_v4_pro"
BOUNDARY_DATASET = ROOT / "outputs/v2_dataset/v2.0.0/v2_boundary.csv"
OUTPUT_ROOT = (
    ROOT
    / "experiments/android_xml_v2_ablation/"
    "deepseek_v2_3"
)
PREPARED_ROOT = OUTPUT_ROOT / "prepared"
PROTOCOL_PATH = OUTPUT_ROOT / "protocol_v2_3.json"
REFERENCE_FULL = PREPARED_ROOT / "reference_full_enhanced.csv"
REFERENCE_LOCK = PREPARED_ROOT / "reference_full_state_lock.json"
EQUAL_BUDGET_ROOT = OUTPUT_ROOT / "equal_budget_40app"
EQUAL_BUDGET_RESULTS = EQUAL_BUDGET_ROOT / "equal_budget_results.csv"
EQUAL_BUDGET_LOCK = EQUAL_BUDGET_ROOT / "EQUAL_BUDGET_RESULT_LOCK.json"
REFERENCE_SINGLE_PASS = PREPARED_ROOT / "reference_single_pass.csv"
BOUNDARY_MANIFEST = PREPARED_ROOT / "boundary_manifest.json"
REPAIR_MANIFEST = PREPARED_ROOT / "repair_manifest.json"

PROTOCOL_ID = "android_xml_v2_deepseek_ablation_v2_3"
REPAIR_VARIANTS = ("no_rag_iterative",)
BOUNDARY_VARIANT = "no_repairability_filter"

FORMAL_RUNNER_CONFIG_FIELDS = (
    "prepared",
    "PROTOCOL_PATH",
    "PREPARED_ROOT",
    "FORMAL_MANIFEST",
    "DEFAULT_OUTPUT",
    "GROUPS",
)
FORMAL_PREPARER_CONFIG_FIELDS = (
    "PROTOCOL_PATH",
    "RESULT_LOCK_PATH",
    "SOURCE_MATRIX",
    "SOURCE_MANIFEST",
    "SOURCE_PROMPTS",
    "SOURCE_BOUNDARY",
    "DEFAULT_OUTPUT",
    "GROUPS",
    "implementation_hashes",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


@contextmanager
def temporary_formal40_configuration():
    runner_snapshot = {
        name: getattr(formal, name)
        for name in FORMAL_RUNNER_CONFIG_FIELDS
    }
    preparer_snapshot = {
        name: getattr(base_formal_preparer, name)
        for name in FORMAL_PREPARER_CONFIG_FIELDS
    }
    formal40.configure_runner()
    try:
        yield
    finally:
        for name, value in runner_snapshot.items():
            setattr(formal, name, value)
        for name, value in preparer_snapshot.items():
            setattr(base_formal_preparer, name, value)


def verify_deepseek_formal_results() -> tuple[list[dict], list[str]]:
    with temporary_formal40_configuration():
        errors = formal.verify_prepared_inputs()
    if not FORMAL_RESULTS.is_file():
        return [], errors + ["DeepSeek formal summary is missing"]
    rows = [
        row
        for row in read_csv(FORMAL_RESULTS)
        if row.get("model_key") == "deepseek_v4_pro"
    ]
    if len(rows) != 220:
        errors.append(f"DeepSeek formal row count is {len(rows)}, not 220")
    keys = {
        (row["task_id"], row["group"]) for row in rows
    }
    if len(keys) != len(rows):
        errors.append("DeepSeek formal results contain duplicate task groups")
    if any(row["status"] == "infrastructure_failed" for row in rows):
        errors.append("DeepSeek formal results contain infrastructure failures")
    counts = {
        group: sum(row["group"] == group for row in rows)
        for group in ("raw_baseline", "full_enhanced")
    }
    if counts != {"raw_baseline": 110, "full_enhanced": 110}:
        errors.append(f"DeepSeek group counts changed: {counts}")
    full_rows = [
        row for row in rows if row["group"] == "full_enhanced"
    ]
    if sum(
        int(row["before_candidate_error_count"]) for row in full_rows
    ) != 136:
        errors.append("DeepSeek Full candidate denominator changed")
    return rows, errors


def full_state_lock(full_rows: list[dict]) -> dict:
    files = {}
    errors = []
    for row in full_rows:
        state = (
            ROOT
            / row["output_path"]
            / "reports/formal_run.json"
        )
        if not state.is_file():
            errors.append(f"missing Full state: {row['task_id']}")
            continue
        files[recorded_path(state)] = sha256_file(state)
    if errors:
        raise SystemExit("\n".join(errors))
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "model_key": "deepseek_v4_pro",
        "group": "full_enhanced",
        "state_count": len(files),
        "files": files,
    }


def verified_equal_budget_rows() -> list[dict]:
    if not EQUAL_BUDGET_LOCK.is_file() or not EQUAL_BUDGET_RESULTS.is_file():
        raise SystemExit(
            "40-App equal-budget RAG completion is missing. Run "
            "tools/run_android_xml_v2_external_rag_completion.py first."
        )
    lock = load_json(EQUAL_BUDGET_LOCK)
    if lock.get("status") != "locked":
        raise SystemExit("40-App equal-budget RAG result is not locked")
    if sha256_file(EQUAL_BUDGET_RESULTS) != lock["results_sha256"]:
        raise SystemExit("40-App equal-budget RAG result hash changed")
    rows = read_csv(EQUAL_BUDGET_RESULTS)
    if len(rows) != 220:
        raise SystemExit(
            f"40-App equal-budget result has {len(rows)} rows, not 220"
        )
    for group in ("no_rag", "rag_topk2"):
        selected = [row for row in rows if row["group"] == group]
        if len(selected) != 110:
            raise SystemExit(f"{group} does not contain 110 tasks")
        denominator = sum(
            int(row["before_candidate_error_count"]) for row in selected
        )
        if denominator != 136:
            raise SystemExit(
                f"{group} candidate denominator is {denominator}, not 136"
            )
    return rows


def boundary_rows() -> list[dict]:
    rows = [
        row
        for row in read_csv(BOUNDARY_DATASET)
        if row.get("dataset_split") == "test"
        and row.get("candidate_role") == "boundary"
    ]
    if len(rows) != 30:
        raise SystemExit(
            f"frozen Test boundary count is {len(rows)}, not 30"
        )
    return rows


def boundary_target_candidates(
    rows: list[dict],
    package_res: Path,
) -> list[dict]:
    expected_path = v2.resource_path(rows[0]["xml_path"])
    layout = package_res / expected_path
    root = ET.parse(layout).getroot()
    apply_explicit_styles(root, load_style_resources([package_res]))
    targets = []
    for row in rows:
        matches = element_candidates(root, row)
        if len(matches) != 1:
            raise ValueError(
                f"{row['candidate_id']}: expected one boundary node, "
                f"found {len(matches)}"
            )
        element = matches[0]
        codes = sorted(
            v2.CANDIDATE_CODES.get(
                (row["issue_type"], row["issue_subtype"]),
                set(),
            )
        )
        if not codes:
            raise ValueError(
                f"{row['candidate_id']}: no detector code mapping"
            )
        targets.append({
            "candidate_id": row["candidate_id"],
            "issue_type": row["issue_type"],
            "issue_subtype": row["issue_subtype"],
            "resource_path": expected_path,
            "selector": candidate_selector(element, root),
            "expected_codes": codes,
            "widget_id": row.get("widget_id", ""),
            "widget_type": row.get("widget_type", ""),
            "attributes": all_attrs(element),
        })
    return targets


def match_boundary_issues(
    issues: list[dict],
    task: dict,
    res_dir: Path,
    require_all: bool = False,
) -> list[dict]:
    matched = []
    seen = set()
    for target in task["target_candidates"]:
        candidates = [
            issue
            for issue in issues
            if issue.get("code") in set(target["expected_codes"])
            and v2.issue_resource_path(issue, res_dir)
            == target["resource_path"]
            and issue.get("selector") == target["selector"]
        ]
        if len(candidates) > 1:
            raise ValueError(
                f"{target['candidate_id']}: duplicate boundary issue"
            )
        if candidates:
            issue = dict(candidates[0])
            issue["v2_candidate_id"] = target["candidate_id"]
            matched.append(issue)
            seen.add(target["candidate_id"])
    if require_all:
        missing = [
            target["candidate_id"]
            for target in task["target_candidates"]
            if target["candidate_id"] not in seen
        ]
        if missing:
            raise ValueError(
                "boundary candidate(s) not reproduced: "
                + ", ".join(missing)
            )
    return matched


def prepare_boundary_tasks(output: Path) -> dict:
    rows = boundary_rows()
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["repository_url"], row["xml_path"])].append(row)
    documents = load_documents()
    tasks = []
    for index, candidate_rows in enumerate(
        [grouped[key] for key in sorted(grouped)],
        1,
    ):
        candidate_rows = sorted(
            candidate_rows,
            key=lambda row: row["candidate_id"],
        )
        task_id = v2.task_id_for(candidate_rows)
        print(f"[{index}/{len(grouped)}] boundary / {task_id}")
        first = candidate_rows[0]
        package = output / "boundary_inputs" / task_id
        collect_test_package(
            v2.source_res_dir(first),
            package,
            force=True,
            selected_layouts={Path(first["xml_path"]).stem},
        )
        prune_entrypoint_variants(package, {
            "screen_path": first["xml_path"],
            "screen_name": Path(first["xml_path"]).stem,
        })
        package_res = package / "res"
        targets = boundary_target_candidates(candidate_rows, package_res)
        task = {
            "task_id": task_id,
            "app_name": first["app_name"],
            "package_name": first["package_name"],
            "repository_url": first["repository_url"],
            "xml_path": first["xml_path"],
            "screen_name": Path(first["xml_path"]).stem,
            "candidate_ids": [
                row["candidate_id"] for row in candidate_rows
            ],
            "issue_types": sorted({
                row["issue_type"] for row in candidate_rows
            }),
            "issue_subtypes": sorted({
                row["issue_subtype"] for row in candidate_rows
            }),
            "target_candidates": targets,
            "candidate_count": len(candidate_rows),
            "input_package": recorded_path(package),
            "input_resource_sha256": tree_digest(package_res),
        }
        issues = run_xml_checker(
            package_res,
            detector_profile="expanded_v3",
        )
        selected = match_boundary_issues(
            issues,
            task,
            package_res,
            require_all=True,
        )
        pair = build_prompt_pair(
            selected,
            package_res,
            documents,
            per_issue_limit=2,
            prompt_limit=2,
        )
        audit = audit_prompt_pair(pair, selected)
        if not audit["passed"]:
            raise SystemExit(
                f"{task_id}: boundary prompt isolation failed: "
                + ", ".join(audit["failures"])
            )
        prompt_root = output / "boundary_prompts" / task_id
        prompt_root.mkdir(parents=True, exist_ok=True)
        prompt_path = prompt_root / "no_filter_rag_topk2_prompt.txt"
        prompt_path.write_text(pair["rag"], encoding="utf-8")
        write_json(
            prompt_root / "retrieval_trace.json",
            pair["trace"],
        )
        save_report(package, issues)
        task.update({
            "prompt_sha256": sha256_file(prompt_path),
            "retrieval_trace_sha256": sha256_file(
                prompt_root / "retrieval_trace.json"
            ),
        })
        write_json(prompt_root / "task.json", task)
        tasks.append(task)
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "status": "boundary_inputs_frozen",
        "model_calls": 0,
        "task_count": len(tasks),
        "candidate_count": sum(
            task["candidate_count"] for task in tasks
        ),
        "app_count": len({
            task["repository_url"] for task in tasks
        }),
        "tasks": tasks,
    }


def implementation_hashes() -> dict:
    paths = {
        "preparer": Path(__file__).resolve(),
        "runner": ROOT / "tools/run_android_xml_v2_deepseek_ablation.py",
        "formal_source_manifest": SOURCE_MANIFEST,
        "formal_prepared_manifest": (
            FORMAL_ROOT / "prepared/formal_manifest.json"
        ),
        "boundary_dataset": BOUNDARY_DATASET,
        "knowledge": ROOT / "knowledge/rag/knowledge_documents.json",
        "retriever": ROOT / "tools/retrieval/v2_hybrid.py",
        "prompt_contract": ROOT / "tools/android_xml_rag_prompt_contract.py",
        "detector": ROOT / "tools/evaluation/android_xml_a11y_check.py",
        "operation_executor": ROOT / "tools/generate_android_xml.py",
        "operation_contract": ROOT / "tools/android_xml_contract_v2_1.py",
        "equal_budget_completion_runner": (
            ROOT / "tools/run_android_xml_v2_external_rag_completion.py"
        ),
        "equal_budget_results": EQUAL_BUDGET_RESULTS,
        "equal_budget_lock": EQUAL_BUDGET_LOCK,
    }
    return {
        name: {
            "path": recorded_path(path),
            "sha256": sha256_file(path),
        }
        for name, path in paths.items()
    }


def protocol_payload(
    repair_manifest_sha256: str,
    boundary_manifest_sha256: str,
    reference_full_sha256: str,
    reference_lock_sha256: str,
    reference_single_pass_sha256: str,
    equal_budget_lock_sha256: str,
) -> dict:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "status": "registered_before_ablation_execution",
        "registered_at": now_iso(),
        "reference_model": {
            "key": "deepseek_v4_pro",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url_env": "DEEPSEEK_BASE_URL",
            "base_url": "https://api.deepseek.com",
        },
        "dataset": {
            "version": "v2.3-40app-repair-benchmark",
            "repair_apps": 40,
            "repair_tasks": 110,
            "xml_safe_candidates": 136,
            "boundary_apps": 14,
            "boundary_tasks": 24,
            "boundary_candidates": 30,
            "repair_manifest": recorded_path(REPAIR_MANIFEST),
            "repair_manifest_sha256": repair_manifest_sha256,
            "boundary_manifest": recorded_path(BOUNDARY_MANIFEST),
            "boundary_manifest_sha256": boundary_manifest_sha256,
        },
        "variants": {
            "full_enhanced": {
                "execution": "reuse_locked_formal_result",
                "new_model_calls": 0,
                "uses_rag": True,
                "uses_iterative_feedback": True,
                "uses_repairability_filter": True,
            },
            "no_rag_iterative": {
                "execution": "new",
                "tasks": 110,
                "uses_rag": False,
                "uses_iterative_feedback": True,
                "uses_repairability_filter": True,
                "max_semantic_rounds": 3,
                "max_format_correction_attempts_per_round": 3,
            },
            "single_pass": {
                "execution": "reuse_locked_equal_budget_rag_topk2",
                "new_model_calls": 0,
                "uses_rag": True,
                "rag_top_k": 2,
                "uses_iterative_feedback": False,
                "uses_repairability_filter": True,
                "max_semantic_rounds": 1,
                "max_format_correction_attempts_per_round": 3,
            },
            "no_repairability_filter": {
                "execution": "boundary_safety_challenge",
                "tasks": 24,
                "candidates": 30,
                "uses_rag": True,
                "rag_top_k": 2,
                "uses_repairability_filter": False,
                "model_calls_per_task": 1,
                "changes_committed": False,
                "primary_metrics": [
                    "unsafe_static_attempt_rate",
                    "executor_would_accept_rate",
                    "model_refusal_rate",
                ],
            },
        },
        "reference_full": {
            "summary": recorded_path(REFERENCE_FULL),
            "summary_sha256": reference_full_sha256,
            "state_lock": recorded_path(REFERENCE_LOCK),
            "state_lock_sha256": reference_lock_sha256,
        },
        "reference_single_pass": {
            "summary": recorded_path(REFERENCE_SINGLE_PASS),
            "summary_sha256": reference_single_pass_sha256,
            "source_equal_budget_lock": recorded_path(EQUAL_BUDGET_LOCK),
            "source_equal_budget_lock_sha256": equal_budget_lock_sha256,
        },
        "execution": {
            "new_condition_runs": 134,
            "minimum_new_model_calls": 134,
            "maximum_new_model_calls": 1014,
            "resume_infrastructure_failures_only": True,
            "repair_group_order": (
                "deterministically rotated by task_id"
            ),
            "boundary_not_in_xml_safe_denominator": True,
        },
        "prohibitions": [
            "Do not rerun the locked Full Enhanced condition.",
            "Do not change the 40-App inputs, candidate denominator, detector, RAG Top-2, Prompt, operation contract, or safety checks.",
            "Do not count boundary candidates in XML-safe repair rates.",
            "Do not commit boundary challenge modifications.",
            "Do not select or remove samples from ablation outcomes.",
            "Only infrastructure failures may be resumed.",
        ],
    }


def prepare(force: bool = False) -> dict:
    rows, errors = verify_deepseek_formal_results()
    if errors:
        raise SystemExit(
            "DeepSeek formal-result validation failed:\n- "
            + "\n- ".join(errors)
        )
    equal_budget_rows = verified_equal_budget_rows()
    if PREPARED_ROOT.exists() and any(PREPARED_ROOT.iterdir()):
        if not force:
            raise SystemExit(
                f"ablation preparation exists: {PREPARED_ROOT}; use --force"
            )
        shutil.rmtree(PREPARED_ROOT)
    PREPARED_ROOT.mkdir(parents=True, exist_ok=True)

    full_rows = [
        row for row in rows if row["group"] == "full_enhanced"
    ]
    write_csv(
        REFERENCE_FULL,
        full_rows,
        list(full_rows[0].keys()),
    )
    write_json(REFERENCE_LOCK, full_state_lock(full_rows))
    single_pass_rows = [
        {
            **row,
            "group": "single_pass",
        }
        for row in equal_budget_rows
        if row["group"] == "rag_topk2"
    ]
    write_csv(
        REFERENCE_SINGLE_PASS,
        single_pass_rows,
        list(single_pass_rows[0].keys()),
    )

    source = load_json(SOURCE_MANIFEST)
    repair_manifest = {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "status": "repair_inputs_reused_frozen",
        "model_calls": 0,
        "repair_app_count": source["repair_app_count"],
        "task_count": source["task_count"],
        "candidate_count": source["candidate_count"],
        "source_manifest": recorded_path(SOURCE_MANIFEST),
        "source_manifest_sha256": sha256_file(SOURCE_MANIFEST),
        "tasks": source["tasks"],
    }
    write_json(REPAIR_MANIFEST, repair_manifest)
    boundary_manifest = prepare_boundary_tasks(PREPARED_ROOT)
    write_json(BOUNDARY_MANIFEST, boundary_manifest)

    protocol = protocol_payload(
        sha256_file(REPAIR_MANIFEST),
        sha256_file(BOUNDARY_MANIFEST),
        sha256_file(REFERENCE_FULL),
        sha256_file(REFERENCE_LOCK),
        sha256_file(REFERENCE_SINGLE_PASS),
        sha256_file(EQUAL_BUDGET_LOCK),
    )
    protocol["implementation_hashes"] = implementation_hashes()
    write_json(PROTOCOL_PATH, protocol)
    return {
        "status": "prepared_no_model_execution",
        "repair_apps": repair_manifest["repair_app_count"],
        "repair_tasks": repair_manifest["task_count"],
        "xml_safe_candidates": repair_manifest["candidate_count"],
        "boundary_apps": boundary_manifest["app_count"],
        "boundary_tasks": boundary_manifest["task_count"],
        "boundary_candidates": boundary_manifest["candidate_count"],
        "full_results_reused": len(full_rows),
        "single_pass_results_reused": len(single_pass_rows),
        "new_condition_runs": protocol["execution"][
            "new_condition_runs"
        ],
        "model_calls": 0,
        "protocol": recorded_path(PROTOCOL_PATH),
    }


def verify() -> dict:
    errors = []
    for path in (
        PROTOCOL_PATH,
        REPAIR_MANIFEST,
        BOUNDARY_MANIFEST,
        REFERENCE_FULL,
        REFERENCE_LOCK,
        REFERENCE_SINGLE_PASS,
    ):
        if not path.is_file():
            errors.append(f"missing prepared file: {recorded_path(path)}")
    if errors:
        return {
            "status": "failed",
            "errors": errors,
            "model_calls": 0,
        }
    protocol = load_json(PROTOCOL_PATH)
    checks = {
        REPAIR_MANIFEST: protocol["dataset"][
            "repair_manifest_sha256"
        ],
        BOUNDARY_MANIFEST: protocol["dataset"][
            "boundary_manifest_sha256"
        ],
        REFERENCE_FULL: protocol["reference_full"]["summary_sha256"],
        REFERENCE_LOCK: protocol["reference_full"][
            "state_lock_sha256"
        ],
        REFERENCE_SINGLE_PASS: protocol["reference_single_pass"][
            "summary_sha256"
        ],
    }
    for path, expected in checks.items():
        if sha256_file(path) != expected:
            errors.append(f"prepared hash changed: {recorded_path(path)}")
    for name, expected in protocol["implementation_hashes"].items():
        current = implementation_hashes().get(name)
        if not current or current["sha256"] != expected["sha256"]:
            errors.append(f"implementation changed: {name}")
    lock = load_json(REFERENCE_LOCK)
    for relative, expected in lock["files"].items():
        path = ROOT / relative
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"locked Full state changed: {relative}")
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "repair_tasks": 110,
        "boundary_tasks": 24,
        "new_condition_runs": 134,
        "model_calls": 0,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("verify")
    return result


def main() -> None:
    args = parser().parse_args()
    result = (
        prepare(args.force)
        if args.command == "prepare"
        else verify()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
