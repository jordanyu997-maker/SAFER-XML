#!/usr/bin/env python3
"""Run the registered DeepSeek V2.3 component ablation study."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import prepare_android_xml_v2_deepseek_ablation as prepared  # noqa: E402
from tools import run_android_xml_v2_40app_formal_study as formal40  # noqa: E402
from tools import run_android_xml_v2_formal_study as formal  # noqa: E402
from tools.android_xml_contract_v2_1 import apply_model_result  # noqa: E402
from tools.android_xml_rag_prompt_contract import build_prompt_pair  # noqa: E402
from tools.generate_android_xml import (  # noqa: E402
    prepare_output,
    run_xml_checker,
    save_report,
    save_round_artifact,
    save_safety_report,
    validate_repair_safety,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.run_android_xml_experiment import model_call_summary  # noqa: E402
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    audit_model_operations,
    now_iso,
    recorded_path,
    validate_pilot_operation_scope,
    write_json,
)


OUTPUT_ROOT = prepared.OUTPUT_ROOT
RUNS_ROOT = OUTPUT_ROOT / "runs"
REPAIR_RESULTS = OUTPUT_ROOT / "repair_ablation_results.csv"
BOUNDARY_RESULTS = OUTPUT_ROOT / "boundary_ablation_results.csv"
RUN_MANIFEST = OUTPUT_ROOT / "run_manifest.json"

REPAIR_RESULT_FIELDS = formal.RESULT_FIELDS + (
    "result_source",
)
BOUNDARY_RESULT_FIELDS = (
    "protocol_id",
    "variant",
    "model_key",
    "task_id",
    "app_name",
    "screen_name",
    "candidate_ids",
    "issue_types",
    "status",
    "model_calls",
    "successful_model_calls",
    "failed_model_calls",
    "provider_attempts",
    "network_retries",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_ms",
    "operation_parse_valid",
    "operation_count",
    "model_refused_static_repair",
    "unsafe_static_attempt",
    "operation_scope_valid",
    "candidate_apply_valid",
    "structural_safety_finding_count",
    "executor_would_accept",
    "changes_committed",
    "output_path",
    "notes",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def configure_formal() -> tuple[dict, dict]:
    formal40.configure_runner()
    protocol = load_json(prepared.PROTOCOL_PATH)
    formal_protocol = load_json(formal.PROTOCOL_PATH)
    model = next(
        item
        for item in formal_protocol["models"]
        if item["key"] == "deepseek_v4_pro"
    )
    return protocol, model


def repair_variant_order(task_id: str) -> tuple[str, ...]:
    return prepared.REPAIR_VARIANTS


def run_repair_variant_loop(
    task: dict,
    variant: str,
    model: dict,
    api_key: str,
    output: Path,
    initial_issues: list[dict],
    documents: list[dict],
    settings: dict,
) -> tuple[list[dict], list[dict], list[dict], str, str]:
    calls = []
    attempts = []
    current_issues = initial_issues
    max_rounds = int(settings["max_semantic_rounds"])
    max_attempts = int(
        settings["max_format_correction_attempts_per_round"]
    )
    uses_rag = bool(settings["uses_rag"])
    input_res = (ROOT / task["input_package"]) / "res"

    for round_number in range(1, max_rounds + 1):
        selected = formal.v2.match_frozen_issues(
            current_issues,
            task,
            output / "res",
        )
        if not selected:
            return (
                current_issues,
                calls,
                attempts,
                "completed",
                "zero_frozen_target_errors",
            )
        pair = build_prompt_pair(
            selected,
            output / "res",
            documents if uses_rag else [],
            per_issue_limit=2,
            prompt_limit=2,
        )
        prompt_key = "rag" if uses_rag else "no_rag"
        base_prompt = pair[prompt_key]
        expected_key = "rag_topk2" if uses_rag else "no_rag"
        if (
            round_number == 1
            and formal.prepared.text_sha256(base_prompt)
            != task["prompt_sha256"][expected_key]
        ):
            raise RuntimeError(
                f"{task['task_id']} / {variant}: initial prompt changed"
            )
        save_round_artifact(
            output,
            f"repair_prompt_round_{round_number}.txt",
            base_prompt,
        )
        trace = pair["trace"] if uses_rag else {
            **pair["trace"],
            "knowledge_documents": [],
            "knowledge_document_count": 0,
            "knowledge_injected_characters": 0,
        }
        write_json(
            output
            / "reports"
            / f"retrieval_trace_round_{round_number}.json",
            trace,
        )
        prompt = base_prompt
        accepted = False
        for attempt_number in range(1, max_attempts + 1):
            try:
                response, metadata = formal.model_call(
                    model,
                    api_key,
                    prompt,
                )
                calls.append(metadata)
            except formal.ModelError as exc:
                calls.append(
                    formal.model_error_metadata(
                        exc,
                        model["provider"],
                        model["model"],
                    )
                )
                attempts.append({
                    "round": round_number,
                    "attempt": attempt_number,
                    "status": "infrastructure_failed",
                    "error": str(exc),
                    "operation_quality": (
                        formal.empty_operation_quality()
                    ),
                })
                return (
                    current_issues,
                    calls,
                    attempts,
                    "infrastructure_failed",
                    "model_provider_error",
                )
            save_round_artifact(
                output,
                (
                    f"model_response_round_{round_number}_"
                    f"attempt_{attempt_number}.txt"
                ),
                response,
            )
            quality = formal.audit_response(response)
            attempt = {
                "round": round_number,
                "attempt": attempt_number,
                "status": "rejected",
                "operation_quality": quality,
            }
            try:
                validate_pilot_operation_scope(
                    response,
                    selected,
                    output / "res",
                )
                _, current_issues = (
                    formal.candidate_evaluate_and_commit(
                        output,
                        input_res,
                        current_issues,
                        task,
                        response,
                    )
                )
                attempt["status"] = "accepted"
                accepted = True
            except (ET.ParseError, TypeError, ValueError) as exc:
                attempt["error"] = str(exc)
                prompt = formal.build_operation_retry_prompt(
                    base_prompt,
                    response,
                    str(exc),
                )
            attempts.append(attempt)
            if accepted:
                break
        if not accepted:
            return (
                current_issues,
                calls,
                attempts,
                "no_improvement",
                "format_or_operation_corrections_exhausted",
            )

    remaining = formal.v2.match_frozen_issues(
        current_issues,
        task,
        output / "res",
    )
    return (
        current_issues,
        calls,
        attempts,
        "completed" if not remaining else "partial",
        "zero_frozen_target_errors" if not remaining else "max_rounds",
    )


def run_repair_task(
    task: dict,
    variant: str,
    model: dict,
    api_key: str,
    documents: list[dict],
    protocol: dict,
    resume: bool,
) -> dict:
    output = RUNS_ROOT / variant / task["task_id"]
    state_path = output / "reports/ablation_run.json"
    if state_path.is_file():
        state = load_json(state_path)
        if state.get("status") != "infrastructure_failed":
            return state
        if not resume:
            raise RuntimeError(
                f"infrastructure-failed output requires --resume: {output}"
            )
    elif output.exists() and any(output.iterdir()):
        raise RuntimeError(f"unregistered existing output: {output}")
    input_package = ROOT / task["input_package"]
    started_at = now_iso()
    prepare_output(input_package, output, force=output.exists())
    initial_issues = run_xml_checker(
        output / "res",
        detector_profile=formal.DETECTOR_PROFILE,
    )
    formal.v2.match_frozen_issues(
        initial_issues,
        task,
        output / "res",
        require_all=True,
    )
    save_report(
        output,
        initial_issues,
        "android_xml_a11y_report_before.json",
    )
    settings = protocol["variants"][variant]
    result = run_repair_variant_loop(
        task,
        variant,
        model,
        api_key,
        output,
        initial_issues,
        documents,
        settings,
    )
    final_issues, calls, attempts, status, stop_reason = result
    state = formal.final_state(
        task,
        model,
        variant,
        output,
        initial_issues,
        final_issues,
        calls,
        attempts,
        status,
        stop_reason,
        started_at,
    )
    state.update({
        "protocol_id": prepared.PROTOCOL_ID,
        "variant": variant,
        "result_source": "new_ablation_execution",
    })
    write_json(state_path, state)
    return state


def boundary_candidate_simulation(
    output: Path,
    response: str,
    selected: list[dict],
) -> dict:
    quality = formal.audit_response(response)
    operation_count = int(quality.get("operation_count", 0))
    result = {
        "operation_parse_valid": bool(
            quality.get("operation_parse_valid")
        ),
        "operation_count": operation_count,
        "model_refused_static_repair": (
            bool(quality.get("operation_parse_valid"))
            and operation_count == 0
        ),
        "unsafe_static_attempt": operation_count > 0,
        "operation_scope_valid": False,
        "candidate_apply_valid": False,
        "structural_safety_finding_count": 0,
        "executor_would_accept": False,
        "error": "",
    }
    if operation_count == 0:
        return result
    try:
        validate_pilot_operation_scope(
            response,
            selected,
            output / "res",
        )
        result["operation_scope_valid"] = True
        with tempfile.TemporaryDirectory(
            prefix="android_xml_v2_boundary_candidate_",
            dir=str(output.parent),
        ) as temp:
            candidate = Path(temp) / "package"
            shutil.copytree(output, candidate)
            apply_model_result(candidate, response)
            result["candidate_apply_valid"] = True
            safety = validate_repair_safety(
                output / "res",
                candidate / "res",
            )
            result["structural_safety_finding_count"] = len(safety)
            result["executor_would_accept"] = not safety
    except (ET.ParseError, TypeError, ValueError) as exc:
        result["error"] = str(exc)
    return result


def run_boundary_task(
    task: dict,
    model: dict,
    api_key: str,
    resume: bool,
) -> dict:
    variant = prepared.BOUNDARY_VARIANT
    output = RUNS_ROOT / variant / task["task_id"]
    state_path = output / "reports/boundary_ablation_run.json"
    if state_path.is_file():
        state = load_json(state_path)
        if state.get("status") != "infrastructure_failed":
            return state
        if not resume:
            raise RuntimeError(
                f"infrastructure-failed output requires --resume: {output}"
            )
    elif output.exists() and any(output.iterdir()):
        raise RuntimeError(f"unregistered existing output: {output}")
    input_package = ROOT / task["input_package"]
    prepare_output(input_package, output, force=output.exists())
    issues = run_xml_checker(
        output / "res",
        detector_profile=formal.DETECTOR_PROFILE,
    )
    selected = prepared.match_boundary_issues(
        issues,
        task,
        output / "res",
        require_all=True,
    )
    save_report(
        output,
        issues,
        "android_xml_a11y_report_before.json",
    )
    prompt_path = (
        prepared.PREPARED_ROOT
        / "boundary_prompts"
        / task["task_id"]
        / "no_filter_rag_topk2_prompt.txt"
    )
    prompt = prompt_path.read_text(encoding="utf-8")
    if formal.prepared.text_sha256(prompt) != task["prompt_sha256"]:
        raise RuntimeError(f"{task['task_id']}: boundary prompt changed")
    save_round_artifact(output, "repair_prompt.txt", prompt)
    calls = []
    response = ""
    status = "completed"
    notes = ""
    try:
        response, metadata = formal.model_call(model, api_key, prompt)
        calls.append(metadata)
        save_round_artifact(output, "model_response.txt", response)
        simulation = boundary_candidate_simulation(
            output,
            response,
            selected,
        )
    except formal.ModelError as exc:
        calls.append(
            formal.model_error_metadata(
                exc,
                model["provider"],
                model["model"],
            )
        )
        simulation = {
            "operation_parse_valid": False,
            "operation_count": 0,
            "model_refused_static_repair": False,
            "unsafe_static_attempt": False,
            "operation_scope_valid": False,
            "candidate_apply_valid": False,
            "structural_safety_finding_count": 0,
            "executor_would_accept": False,
            "error": str(exc),
        }
        status = "infrastructure_failed"
        notes = str(exc)
    summary = model_call_summary(calls)
    usage = summary.get("usage", {})
    state = {
        "schema_version": 1,
        "protocol_id": prepared.PROTOCOL_ID,
        "variant": variant,
        "model_key": model["key"],
        "task_id": task["task_id"],
        "app_name": task["app_name"],
        "screen_name": task["screen_name"],
        "candidate_ids": task["candidate_ids"],
        "issue_types": task["issue_types"],
        "status": status,
        "model_calls": len(calls),
        "successful_model_calls": summary.get(
            "successful_model_calls",
            0,
        ),
        "failed_model_calls": summary.get("failed_model_calls", 0),
        "provider_attempts": summary.get("provider_attempts", 0),
        "network_retries": summary.get("network_retries", 0),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "duration_ms": summary.get("duration_ms"),
        **simulation,
        "changes_committed": False,
        "output_path": recorded_path(output),
        "notes": notes or simulation.get("error", ""),
        "completed_at": now_iso(),
    }
    write_json(state_path, state)
    return state


def repair_state_rows() -> list[dict]:
    rows = []
    for variant in prepared.REPAIR_VARIANTS:
        root = RUNS_ROOT / variant
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/reports/ablation_run.json")):
            rows.append(load_json(path))
    return rows


def boundary_state_rows() -> list[dict]:
    root = RUNS_ROOT / prepared.BOUNDARY_VARIANT
    if not root.is_dir():
        return []
    return [
        load_json(path)
        for path in sorted(
            root.glob("*/reports/boundary_ablation_run.json")
        )
    ]


def summarize() -> dict:
    reference_rows = prepared.read_csv(prepared.REFERENCE_FULL)
    full_rows = [
        {
            **row,
            "result_source": "reused_locked_formal_result",
        }
        for row in reference_rows
    ]
    single_pass_rows = [
        {
            **row,
            "result_source": "reused_locked_equal_budget_rag_topk2",
        }
        for row in prepared.read_csv(prepared.REFERENCE_SINGLE_PASS)
    ]
    new_rows = repair_state_rows()
    repair_rows = [
        formal.state_row(row) | {
            "result_source": row.get(
                "result_source",
                "new_ablation_execution",
            )
        }
        for row in new_rows
    ]
    write_csv(
        REPAIR_RESULTS,
        full_rows + single_pass_rows + repair_rows,
        REPAIR_RESULT_FIELDS,
    )
    boundary_rows = boundary_state_rows()
    write_csv(
        BOUNDARY_RESULTS,
        [
            {
                **row,
                "candidate_ids": ";".join(
                    row.get("candidate_ids", [])
                ),
                "issue_types": ";".join(
                    row.get("issue_types", [])
                ),
            }
            for row in boundary_rows
        ],
        BOUNDARY_RESULT_FIELDS,
    )
    all_new = new_rows + boundary_rows
    manifest = {
        "schema_version": 1,
        "protocol_id": prepared.PROTOCOL_ID,
        "updated_at": now_iso(),
        "full_enhanced_reused_runs": len(full_rows),
        "single_pass_reused_runs": len(single_pass_rows),
        "new_recorded_condition_runs": len(all_new),
        "new_completed_condition_runs": sum(
            row.get("status") != "infrastructure_failed"
            for row in all_new
        ),
        "infrastructure_failed_condition_runs": sum(
            row.get("status") == "infrastructure_failed"
            for row in all_new
        ),
        "variant_counts": {
            "full_enhanced": len(full_rows),
            "single_pass": len(single_pass_rows),
            **{
                variant: sum(
                    row.get("variant") == variant
                    for row in all_new
                )
                for variant in (
                    *prepared.REPAIR_VARIANTS,
                    prepared.BOUNDARY_VARIANT,
                )
            },
        },
        "repair_results": recorded_path(REPAIR_RESULTS),
        "boundary_results": recorded_path(BOUNDARY_RESULTS),
    }
    write_json(RUN_MANIFEST, manifest)
    return manifest


def run(args) -> dict:
    verification = prepared.verify()
    if verification["errors"]:
        raise SystemExit(
            "Ablation preparation validation failed:\n- "
            + "\n- ".join(verification["errors"])
        )
    protocol, model = configure_formal()
    requested = (
        [
            item.strip()
            for item in args.variants.split(",")
            if item.strip()
        ]
        if args.variants
        else [
            *prepared.REPAIR_VARIANTS,
            prepared.BOUNDARY_VARIANT,
        ]
    )
    allowed = {
        *prepared.REPAIR_VARIANTS,
        prepared.BOUNDARY_VARIANT,
    }
    unknown = sorted(set(requested) - allowed)
    if unknown:
        raise SystemExit("unknown ablation variant(s): " + ", ".join(unknown))
    source = load_json(prepared.REPAIR_MANIFEST)
    boundary = load_json(prepared.BOUNDARY_MANIFEST)
    documents = load_documents()
    repair_requested = [
        item for item in requested if item in prepared.REPAIR_VARIANTS
    ]
    total = len(source["tasks"]) * len(repair_requested)
    if prepared.BOUNDARY_VARIANT in requested:
        total += len(boundary["tasks"])
    index = 0
    with formal.provider_environment(model) as api_key:
        if not api_key:
            raise SystemExit("missing API key environment: DEEPSEEK_API_KEY")
        formal.validate_model_configuration(model["provider"], api_key)
        for task in source["tasks"]:
            for variant in repair_variant_order(task["task_id"]):
                if variant not in repair_requested:
                    continue
                index += 1
                print(f"[{index}/{total}] {variant} / {task['task_id']}")
                run_repair_task(
                    task,
                    variant,
                    model,
                    api_key,
                    documents,
                    protocol,
                    args.resume,
                )
        if prepared.BOUNDARY_VARIANT in requested:
            for task in boundary["tasks"]:
                index += 1
                print(
                    f"[{index}/{total}] "
                    f"{prepared.BOUNDARY_VARIANT} / {task['task_id']}"
                )
                run_boundary_task(
                    task,
                    model,
                    api_key,
                    args.resume,
                )
    return summarize()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--variants")
    run_parser.add_argument("--resume", action="store_true")
    subparsers.add_parser("summarize")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "verify":
        result = prepared.verify()
    elif args.command == "run":
        result = run(args)
    else:
        result = summarize()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
