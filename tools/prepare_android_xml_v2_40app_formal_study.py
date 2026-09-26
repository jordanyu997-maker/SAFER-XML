#!/usr/bin/env python3
"""Freeze and prepare the 40-App V2.3 formal comparison matrix."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import prepare_android_xml_v2_formal_study as formal  # noqa: E402
from tools.prepare_android_xml_v2_external_matrix import (  # noqa: E402
    verify as verify_external_matrix,
)
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    recorded_path,
    sha256_file,
)


BASE_MATRIX = ROOT / "experiments/android_xml_v2_rag/test_v2_1/matrix"
BASE_MANIFEST = BASE_MATRIX / "frozen_manifest.json"
BASE_PROMPTS = BASE_MATRIX / "frozen_prompts"
BASE_BOUNDARY = BASE_MATRIX / "boundary_gate.csv"
EXTERNAL_MATRIX = (
    ROOT / "experiments/android_xml_v2_external_extension/top2_matrix"
)
EXTERNAL_MANIFEST = EXTERNAL_MATRIX / "frozen_manifest.json"
EXTERNAL_PROMPTS = EXTERNAL_MATRIX / "frozen_prompts"
COMBINED_CANDIDATES = (
    ROOT
    / "outputs/v2_dataset/v2.1_external_extension/"
    "combined_40_app_xml_safe_manifest.csv"
)
RESULT_LOCK_PATH = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "FINAL_TEST_RESULT_LOCK.json"
)
ELIGIBILITY_EXCLUSIONS = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "test_eligibility_exclusions.csv"
)
SOURCE_MATRIX = (
    ROOT
    / "experiments/android_xml_v2_formal/"
    "multimodel_v2_3_40app/source_matrix"
)
SOURCE_MANIFEST = SOURCE_MATRIX / "frozen_manifest.json"
SOURCE_PROMPTS = SOURCE_MATRIX / "frozen_prompts"
SOURCE_BOUNDARY = SOURCE_MATRIX / "boundary_gate.csv"
PROTOCOL_PATH = (
    ROOT
    / "experiments/android_xml_v2_formal/"
    "protocol_v2_3_40app.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_v2_formal/"
    "multimodel_v2_3_40app/prepared"
)
FORMAL_RUN_ROOT = (
    ROOT
    / "experiments/android_xml_v2_formal/"
    "multimodel_v2_3_40app"
)
GROUPS = formal.GROUPS
group_order = formal.group_order
initial_prompt = formal.initial_prompt
text_sha256 = formal.text_sha256

EXPECTED_BASE_MANIFEST_SHA256 = (
    "1fa66fd41cfd0498d7419bb88b57a6c5c69840c8fc77128f4cc03f208e57d71f"
)
EXPECTED_EXTERNAL_MANIFEST_SHA256 = (
    "de817921956eb1ae54e999610058154a27a4db90ce5af39496ffa0efc3f65854"
)
EXPECTED_COMBINED_CANDIDATE_SHA256 = (
    "bfc3f9420bd863d2329462a8b4b48c23eb2ff173c56465c1c757f6b66723d4f0"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_source_components() -> tuple[dict, dict, list[str]]:
    errors = formal.verify_result_lock()
    if not BASE_MANIFEST.is_file():
        errors.append("base V2 Test manifest is missing")
        base = {}
    else:
        base = load_json(BASE_MANIFEST)
        if sha256_file(BASE_MANIFEST) != EXPECTED_BASE_MANIFEST_SHA256:
            errors.append("base V2 Test manifest changed")
    external_check = verify_external_matrix(EXTERNAL_MATRIX)
    errors.extend(external_check["errors"])
    if not EXTERNAL_MANIFEST.is_file():
        errors.append("external extension manifest is missing")
        external = {}
    else:
        external = load_json(EXTERNAL_MANIFEST)
        if (
            sha256_file(EXTERNAL_MANIFEST)
            != EXPECTED_EXTERNAL_MANIFEST_SHA256
        ):
            errors.append("external extension manifest changed")
    if (
        not COMBINED_CANDIDATES.is_file()
        or sha256_file(COMBINED_CANDIDATES)
        != EXPECTED_COMBINED_CANDIDATE_SHA256
    ):
        errors.append("combined 40-App candidate manifest changed")
    return base, external, errors


def protocol_payload(source_manifest_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "protocol_id": "android_xml_v2_multimodel_40app_v2_3",
        "status": "registered_before_model_execution",
        "registered_at": "2026-07-28T00:00:00+08:00",
        "dataset": {
            "version": "v2.3-40app-repair-benchmark",
            "dataset_sha256": EXPECTED_COMBINED_CANDIDATE_SHA256,
            "split": "locked_test_plus_untouched_external_extension",
            "source_manifest": recorded_path(SOURCE_MANIFEST),
            "source_manifest_sha256": source_manifest_sha256,
            "eligibility_exclusions": recorded_path(
                ELIGIBILITY_EXCLUSIONS
            ),
            "eligibility_exclusions_sha256": sha256_file(
                ELIGIBILITY_EXCLUSIONS
            ),
            "repair_task_count": 110,
            "xml_safe_candidate_count": 136,
            "repair_app_count": 40,
            "boundary_candidate_count": 30,
            "base_partition": {
                "repair_apps": 27,
                "repair_tasks": 74,
                "xml_safe_candidates": 93,
                "prior_result_lock": recorded_path(RESULT_LOCK_PATH),
            },
            "external_partition": {
                "repair_apps": 13,
                "repair_tasks": 36,
                "xml_safe_candidates": 43,
                "prior_model_calls": 0,
            },
        },
        "models": [
            {
                "key": "deepseek_v4_pro",
                "display_name": "DeepSeek V4 Pro",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "api_key_env": "DEEPSEEK_API_KEY",
                "base_url_env": "DEEPSEEK_BASE_URL",
                "base_url": "https://api.deepseek.com",
                "api_style": "chat_completions",
            },
            {
                "key": "gpt_5_6_sol",
                "display_name": "GPT 5.6 SOL",
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "api_key_env": "ANDROID_XML_GPT_API_KEY",
                "base_url_env": "OPENAI_BASE_URL",
                "base_url": "https://rkapi.com/v1",
                "api_style": "responses",
            },
            {
                "key": "claude_opus_4_8",
                "display_name": "Claude Opus 4.8",
                "provider": "anthropic",
                "model": "claude-opus-4-8",
                "api_key_env": "ANDROID_XML_CLAUDE_API_KEY",
                "base_url_env": "ANTHROPIC_BASE_URL",
                "base_url": "https://rkapi.com",
                "api_style": "messages",
                "auth_style": "bearer",
            },
        ],
        "main_comparison": {
            "groups": {
                "raw_baseline": {
                    "uses_detector_findings_in_prompt": False,
                    "uses_rag": False,
                    "uses_iterative_feedback": False,
                    "semantic_rounds": 1,
                    "format_correction_attempts_per_round": 1,
                    "description": (
                        "Generic Android accessibility instruction over "
                        "original XML, one model call."
                    ),
                },
                "full_enhanced": {
                    "uses_detector_findings_in_prompt": True,
                    "uses_rag": True,
                    "rag_top_k": 2,
                    "uses_iterative_feedback": True,
                    "max_semantic_rounds": 3,
                    "max_format_correction_attempts_per_round": 3,
                    "uses_repairability_filter": True,
                    "description": (
                        "Severity-aware detector, frozen XML-safe scope, "
                        "RAG Top-2, feedback, transactional execution, and "
                        "safety validation."
                    ),
                },
            },
            "controlled_identically": [
                "model identity within each pair",
                "frozen input package",
                "frozen candidate denominator",
                "JSON operation schema",
                "transactional operation executor",
                "structural safety validation",
                "candidate-level evaluator",
            ],
            "budget_policy": (
                "System-level effectiveness comparison. Calls, tokens, and "
                "latency are reported because procedures differ."
            ),
            "group_order": (
                "deterministically rotated by model_key and task_id"
            ),
            "repetitions": 1,
        },
        "metrics": {
            "primary": [
                "candidate_repair_rate",
                "complete_candidate_repair_rate",
            ],
            "paired": [
                "wins_ties_losses",
                "paired_task_repair_rate_delta",
                "fixed_seed_bootstrap_95_percent_ci",
                "two_sided_exact_sign_test",
            ],
            "safety": [
                "safety_finding_count",
                "hardcoded_accessibility_value_count",
                "interaction_attribute_removal_count",
                "structural_operation_count",
                "rejected_attempt_count",
            ],
            "cost": [
                "model_calls",
                "provider_attempts",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "duration_ms",
            ],
        },
        "execution": {
            "detector_profile": "expanded_v3",
            "rag_top_k": 2,
            "max_output_tokens": 16384,
            "resume_only_infrastructure_failures": True,
            "fresh_copy_per_model_group_task": True,
            "cross_group_output_access": False,
            "cross_model_output_access": False,
            "output_root": recorded_path(FORMAL_RUN_ROOT),
        },
        "isolation": {
            "external_partition_selected_from_source_evidence_only": True,
            "external_partition_prior_model_calls": 0,
            "prior_outputs_not_in_prompts": True,
            "cross_condition_output_access": False,
            "cross_model_output_access": False,
        },
        "prohibitions": [
            "Do not modify frozen source inputs or prior Test results.",
            "Do not tune prompts, retrieval, detector, knowledge, safety, or samples from new outcomes.",
            "Do not pass another model or group output into the current prompt.",
            "Do not count boundary candidates in XML-safe repair rates.",
            "Do not rerun successful records selectively.",
            "Do not treat provider or network failure as a repair failure.",
        ],
    }


def copy_prompt_tree(
    tasks: list[dict],
    source: Path,
    destination: Path,
) -> None:
    for task in tasks:
        task_id = task["task_id"]
        source_task = source / task_id
        target_task = destination / task_id
        if not source_task.is_dir():
            raise FileNotFoundError(
                f"frozen prompt directory missing: {source_task}"
            )
        if target_task.exists():
            raise ValueError(f"duplicate frozen task ID: {task_id}")
        shutil.copytree(source_task, target_task)


def build_combined_source(force: bool = False) -> dict:
    base, external, errors = verify_source_components()
    if errors:
        raise SystemExit(
            "40-App source validation failed:\n- " + "\n- ".join(errors)
        )
    if SOURCE_MATRIX.exists() and any(SOURCE_MATRIX.iterdir()):
        if not force:
            raise SystemExit(
                f"combined source already exists: {SOURCE_MATRIX}; use --force"
            )
        shutil.rmtree(SOURCE_MATRIX)
    SOURCE_PROMPTS.mkdir(parents=True, exist_ok=True)
    base_tasks = base["tasks"]
    external_tasks = external["tasks"]
    all_tasks = base_tasks + external_tasks
    task_ids = [task["task_id"] for task in all_tasks]
    if len(task_ids) != len(set(task_ids)):
        raise SystemExit("base and external matrices contain duplicate task IDs")
    copy_prompt_tree(base_tasks, BASE_PROMPTS, SOURCE_PROMPTS)
    copy_prompt_tree(external_tasks, EXTERNAL_PROMPTS, SOURCE_PROMPTS)
    shutil.copy2(BASE_BOUNDARY, SOURCE_BOUNDARY)
    app_urls = {task["repository_url"] for task in all_tasks}
    if len(app_urls) != 40:
        raise SystemExit(f"combined repair App count is {len(app_urls)}, not 40")
    manifest = {
        "schema_version": 1,
        "dataset_version": "v2.3-40app-repair-benchmark",
        "dataset_sha256": EXPECTED_COMBINED_CANDIDATE_SHA256,
        "status": "combined_40app_inputs_frozen",
        "created_before_model_execution": True,
        "model_calls": 0,
        "conditions": ["no_rag", "rag_topk2"],
        "repair_app_count": len(app_urls),
        "task_count": len(all_tasks),
        "candidate_count": sum(
            int(task["candidate_count"]) for task in all_tasks
        ),
        "boundary_candidate_count": base["boundary_candidate_count"],
        "boundary_gate_sha256": sha256_file(SOURCE_BOUNDARY),
        "partitions": {
            "existing_v2_test": {
                "manifest": recorded_path(BASE_MANIFEST),
                "manifest_sha256": sha256_file(BASE_MANIFEST),
                "repair_apps": base["repair_app_count"],
                "tasks": base["task_count"],
                "candidates": base["candidate_count"],
            },
            "external_extension": {
                "manifest": recorded_path(EXTERNAL_MANIFEST),
                "manifest_sha256": sha256_file(EXTERNAL_MANIFEST),
                "repair_apps": external["external_app_count"],
                "tasks": external["task_count"],
                "candidates": external["candidate_count"],
                "prior_model_calls": 0,
            },
        },
        "tasks": all_tasks,
    }
    if manifest["task_count"] != 110:
        raise SystemExit("combined repair task count is not 110")
    if manifest["candidate_count"] != 136:
        raise SystemExit("combined XML-safe candidate count is not 136")
    write_json(SOURCE_MANIFEST, manifest)
    protocol = protocol_payload(sha256_file(SOURCE_MANIFEST))
    write_json(PROTOCOL_PATH, protocol)
    return manifest


def implementation_hashes() -> dict:
    paths = {
        "preparer": Path(__file__).resolve(),
        "formal_runner": ROOT / "tools/run_android_xml_v2_40app_formal_study.py",
        "protocol": PROTOCOL_PATH,
        "result_lock": RESULT_LOCK_PATH,
        "source_manifest": SOURCE_MANIFEST,
        "combined_candidates": COMBINED_CANDIDATES,
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


def configure_formal_preparer() -> None:
    formal.PROTOCOL_PATH = PROTOCOL_PATH
    formal.RESULT_LOCK_PATH = RESULT_LOCK_PATH
    formal.SOURCE_MATRIX = SOURCE_MATRIX
    formal.SOURCE_MANIFEST = SOURCE_MANIFEST
    formal.SOURCE_PROMPTS = SOURCE_PROMPTS
    formal.SOURCE_BOUNDARY = SOURCE_BOUNDARY
    formal.DEFAULT_OUTPUT = DEFAULT_OUTPUT
    formal.GROUPS = GROUPS
    formal.implementation_hashes = implementation_hashes


def prepare(output: Path, force: bool = False) -> dict:
    build_combined_source(force=force)
    configure_formal_preparer()
    return formal.prepare(output, force=force)


def verify() -> dict:
    configure_formal_preparer()
    if not SOURCE_MANIFEST.is_file() or not PROTOCOL_PATH.is_file():
        return {
            "status": "failed",
            "errors": ["40-App source matrix or protocol is missing"],
            "model_calls": 0,
        }
    result = formal.verify()
    source = load_json(SOURCE_MANIFEST)
    if source.get("repair_app_count") != 40:
        result["errors"].append("combined repair App count changed")
    if source.get("task_count") != 110:
        result["errors"].append("combined repair task count changed")
    if source.get("candidate_count") != 136:
        result["errors"].append("combined candidate count changed")
    result["status"] = "passed" if not result["errors"] else "failed"
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    prepare_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("verify")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "prepare":
        result = prepare(args.output.resolve(), args.force)
    else:
        result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
