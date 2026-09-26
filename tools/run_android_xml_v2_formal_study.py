#!/usr/bin/env python3
"""Run the registered V2.2 raw-baseline versus full-system comparison."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import prepare_android_xml_v2_formal_study as prepared  # noqa: E402
from tools import run_android_xml_v2_rag_experiment as v2  # noqa: E402
from tools.android_xml_contract_v2_1 import apply_model_result  # noqa: E402
from tools.android_xml_rag_prompt_contract import build_prompt_pair  # noqa: E402
from tools.generate import (  # noqa: E402
    ModelError,
    model_error_metadata,
    run_model_with_metadata,
    validate_model_configuration,
)
from tools.generate_android_xml import (  # noqa: E402
    build_operation_retry_prompt,
    error_count,
    issue_quality,
    prepare_output,
    run_xml_checker,
    save_report,
    save_round_artifact,
    save_safety_report,
    validate_repair_safety,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.run_android_xml_experiment import (  # noqa: E402
    build_baseline_prompt,
    model_call_summary,
)
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    audit_model_operations,
    now_iso,
    recorded_path,
    sha256_file,
    validate_pilot_operation_scope,
    write_json,
)


PROTOCOL_PATH = prepared.PROTOCOL_PATH
PREPARED_ROOT = prepared.DEFAULT_OUTPUT
FORMAL_MANIFEST = PREPARED_ROOT / "formal_manifest.json"
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_formal/multimodel_v2_2"
GROUPS = prepared.GROUPS
DETECTOR_PROFILE = "expanded_v3"

RESULT_FIELDS = (
    "protocol_id",
    "model_key",
    "model_display_name",
    "provider",
    "model",
    "task_id",
    "app_name",
    "screen_name",
    "candidate_ids",
    "issue_types",
    "issue_subtypes",
    "group",
    "status",
    "stop_reason",
    "before_candidate_error_count",
    "after_candidate_error_count",
    "candidate_repair_rate",
    "complete_candidate_repair",
    "before_total_error_count",
    "after_total_error_count",
    "warning_count",
    "info_count",
    "model_calls",
    "successful_model_calls",
    "failed_model_calls",
    "provider_attempts",
    "network_retries",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_ms",
    "semantic_rounds_completed",
    "rejected_attempt_count",
    "operation_parse_invalid_count",
    "hardcoded_accessibility_value_count",
    "interaction_attribute_removal_count",
    "structural_operation_count",
    "changed_file_count",
    "changed_files",
    "safety_finding_count",
    "output_path",
    "notes",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(RESULT_FIELDS),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def verify_prepared_inputs() -> list[str]:
    result = prepared.verify()
    errors = list(result["errors"])
    if not FORMAL_MANIFEST.is_file():
        return errors + ["formal prepared manifest is missing"]
    manifest = load_json(FORMAL_MANIFEST)
    for name, expected in manifest.get("implementation_hashes", {}).items():
        current = prepared.implementation_hashes().get(name)
        if not current or current["sha256"] != expected["sha256"]:
            errors.append(f"prepared implementation changed: {name}")
    tasks = PREPARED_ROOT / "formal_tasks.csv"
    if (
        not tasks.is_file()
        or sha256_file(tasks) != manifest.get("formal_tasks_sha256")
    ):
        errors.append("prepared formal task matrix changed")
    boundary = PREPARED_ROOT / "boundary_gate.csv"
    if (
        not boundary.is_file()
        or sha256_file(boundary) != manifest.get("boundary_gate_sha256")
    ):
        errors.append("prepared boundary gate changed")
    return errors


def selected_models(protocol: dict, requested: str | None) -> list[dict]:
    by_key = {model["key"]: model for model in protocol["models"]}
    if not requested:
        return list(protocol["models"])
    keys = [item.strip() for item in requested.split(",") if item.strip()]
    unknown = sorted(set(keys) - set(by_key))
    if unknown:
        raise SystemExit("unknown model key(s): " + ", ".join(unknown))
    return [by_key[key] for key in keys]


@contextmanager
def provider_environment(model: dict):
    names = [model["base_url_env"]]
    values = {model["base_url_env"]: model["base_url"]}
    if model["provider"] == "openai":
        names.append("OPENAI_API_STYLE")
        values["OPENAI_API_STYLE"] = model.get("api_style", "responses")
    if model["provider"] == "anthropic":
        names.append("ANTHROPIC_AUTH_STYLE")
        values["ANTHROPIC_AUTH_STYLE"] = model.get(
            "auth_style",
            "x_api_key",
        )
    names.append("LLM_MAX_OUTPUT_TOKENS")
    values["LLM_MAX_OUTPUT_TOKENS"] = "16384"
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update(values)
    try:
        yield os.environ.get(model["api_key_env"])
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def candidate_evaluate_and_commit(
    output_package: Path,
    input_res: Path,
    current_issues: list[dict],
    task: dict,
    model_output: str,
) -> tuple[list[Path], list[dict]]:
    """Commit only a structurally safe change that reduces frozen targets."""
    output_package = output_package.resolve()
    with tempfile.TemporaryDirectory(
        prefix="android_xml_v2_formal_candidate_",
        dir=str(output_package.parent),
    ) as temp:
        candidate_package = Path(temp) / "package"
        shutil.copytree(output_package, candidate_package)
        changed = apply_model_result(candidate_package, model_output)
        candidate_res = candidate_package / "res"
        candidate_issues = run_xml_checker(
            candidate_res,
            detector_profile=DETECTOR_PROFILE,
        )
        safety = validate_repair_safety(input_res, candidate_res)
        if safety:
            codes = ", ".join(
                item.get("code", "UNKNOWN") for item in safety
            )
            raise ValueError(
                "candidate failed structural safety validation: " + codes
            )
        before_targets = v2.match_frozen_issues(
            current_issues,
            task,
            output_package / "res",
        )
        after_targets = v2.match_frozen_issues(
            candidate_issues,
            task,
            candidate_res,
        )
        if len(after_targets) >= len(before_targets):
            raise ValueError(
                "candidate did not reduce frozen target errors: "
                f"before={len(before_targets)}, after={len(after_targets)}"
            )
        if error_count(candidate_issues) >= error_count(current_issues):
            raise ValueError(
                "candidate did not reduce total high-confidence errors: "
                f"before={error_count(current_issues)}, "
                f"after={error_count(candidate_issues)}"
            )
        committed = []
        for candidate_path in changed:
            relative = candidate_path.relative_to(candidate_package.resolve())
            destination = output_package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_path, destination)
            committed.append(destination)
        return sorted(committed), candidate_issues


def empty_operation_quality() -> dict:
    return {
        "operation_parse_valid": False,
        "operation_count": 0,
        "string_resource_addition_count": 0,
        "hardcoded_accessibility_value_count": 0,
        "interaction_attribute_removal_count": 0,
        "structural_operation_count": 0,
    }


def audit_response(response: str) -> dict:
    try:
        return audit_model_operations(response)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            **empty_operation_quality(),
            "audit_error": str(exc),
        }


def model_call(
    model: dict,
    api_key: str,
    prompt: str,
) -> tuple[str, dict]:
    result = run_model_with_metadata(
        model["provider"],
        model["model"],
        prompt,
        api_key,
    )
    return result["content"], result["metadata"]


def run_raw_baseline(
    task: dict,
    model: dict,
    api_key: str,
    output: Path,
    selected: list[dict],
    initial_issues: list[dict],
) -> tuple[list[dict], list[dict], list[dict], str, str]:
    prompt = build_baseline_prompt(output / "res")
    _, expected_prompt_hash = prepared.initial_prompt(
        task,
        "raw_baseline",
    )
    if prepared.text_sha256(prompt) != expected_prompt_hash:
        raise RuntimeError(
            f"{task['task_id']}: initial Baseline prompt changed after freeze"
        )
    save_round_artifact(output, "raw_baseline_prompt.txt", prompt)
    calls = []
    attempts = []
    changed = []
    status = "no_improvement"
    stop_reason = "one_shot_completed_without_target_reduction"
    current_issues = initial_issues
    try:
        response, metadata = model_call(model, api_key, prompt)
        calls.append(metadata)
        save_round_artifact(output, "model_response.txt", response)
        quality = audit_response(response)
        attempt = {
            "round": 1,
            "attempt": 1,
            "operation_quality": quality,
            "status": "rejected",
        }
        try:
            validate_pilot_operation_scope(
                response,
                selected,
                output / "res",
            )
            accepted, current_issues = candidate_evaluate_and_commit(
                output,
                (ROOT / task["input_package"]) / "res",
                initial_issues,
                task,
                response,
            )
            changed.extend(accepted)
            attempt["status"] = "accepted"
            status = "completed"
            stop_reason = "one_shot_target_reduction"
        except (ET.ParseError, TypeError, ValueError) as exc:
            attempt["error"] = str(exc)
        attempts.append(attempt)
    except ModelError as exc:
        calls.append(
            model_error_metadata(
                exc,
                model["provider"],
                model["model"],
            )
        )
        status = "infrastructure_failed"
        stop_reason = "model_provider_error"
        attempts.append({
            "round": 1,
            "attempt": 1,
            "status": "infrastructure_failed",
            "error": str(exc),
            "operation_quality": empty_operation_quality(),
        })
    return current_issues, calls, attempts, status, stop_reason


def run_full_enhanced(
    task: dict,
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
    status = "no_improvement"
    stop_reason = "max_rounds"
    max_rounds = int(settings["max_semantic_rounds"])
    max_attempts = int(settings["max_format_correction_attempts_per_round"])
    input_res = (ROOT / task["input_package"]) / "res"

    for round_number in range(1, max_rounds + 1):
        selected = v2.match_frozen_issues(
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
            documents,
            per_issue_limit=2,
            prompt_limit=2,
        )
        base_prompt = pair["rag"]
        if (
            round_number == 1
            and prepared.text_sha256(base_prompt)
            != task["prompt_sha256"]["rag_topk2"]
        ):
            raise RuntimeError(
                f"{task['task_id']}: initial Full prompt changed after freeze"
            )
        save_round_artifact(
            output,
            f"repair_prompt_round_{round_number}.txt",
            base_prompt,
        )
        write_json(
            output / "reports"
            / f"retrieval_trace_round_{round_number}.json",
            pair["trace"],
        )
        prompt = base_prompt
        accepted = False
        for attempt_number in range(1, max_attempts + 1):
            try:
                response, metadata = model_call(model, api_key, prompt)
                calls.append(metadata)
            except ModelError as exc:
                calls.append(
                    model_error_metadata(
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
                    "operation_quality": empty_operation_quality(),
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
            quality = audit_response(response)
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
                _, current_issues = candidate_evaluate_and_commit(
                    output,
                    input_res,
                    current_issues,
                    task,
                    response,
                )
                attempt["status"] = "accepted"
                accepted = True
            except (ET.ParseError, TypeError, ValueError) as exc:
                attempt["error"] = str(exc)
                prompt = build_operation_retry_prompt(
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

    remaining = v2.match_frozen_issues(
        current_issues,
        task,
        output / "res",
    )
    if not remaining:
        status = "completed"
        stop_reason = "zero_frozen_target_errors"
    elif len(remaining) < int(task["candidate_count"]):
        status = "partial"
    return current_issues, calls, attempts, status, stop_reason


def final_state(
    task: dict,
    model: dict,
    group: str,
    output: Path,
    initial_issues: list[dict],
    final_issues: list[dict],
    calls: list[dict],
    attempts: list[dict],
    status: str,
    stop_reason: str,
    started_at: str,
) -> dict:
    input_res = (ROOT / task["input_package"]) / "res"
    output_res = output / "res"
    before = v2.match_frozen_issues(
        initial_issues,
        task,
        output_res,
        require_all=True,
    )
    after = v2.match_frozen_issues(final_issues, task, output_res)
    if status != "infrastructure_failed":
        if not after:
            status = "completed"
        elif len(after) < len(before):
            status = "partial"
        else:
            status = "no_improvement"
    safety = validate_repair_safety(input_res, output_res)
    save_report(output, final_issues, "android_xml_a11y_report_after.json")
    save_safety_report(output, safety)
    summary = model_call_summary(calls)
    usage = summary.get("usage", {})
    qualities = [
        item.get("operation_quality", {}) for item in attempts
    ]
    changed = sorted({
        path.relative_to(output).as_posix()
        for path in output_res.rglob("*.xml")
        if (
            not (input_res / path.relative_to(output_res)).exists()
            or path.read_bytes()
            != (input_res / path.relative_to(output_res)).read_bytes()
        )
    })
    quality = issue_quality(final_issues)
    state = {
        "schema_version": 1,
        "protocol_id": load_json(PROTOCOL_PATH)["protocol_id"],
        "model_key": model["key"],
        "model_display_name": model["display_name"],
        "provider": model["provider"],
        "model": model["model"],
        "task_id": task["task_id"],
        "app_name": task["app_name"],
        "screen_name": task["screen_name"],
        "candidate_ids": task["candidate_ids"],
        "issue_types": task["issue_types"],
        "issue_subtypes": task["issue_subtypes"],
        "group": group,
        "status": status,
        "stop_reason": stop_reason,
        "before_candidate_error_count": len(before),
        "after_candidate_error_count": len(after),
        "candidate_repair_rate": (
            (len(before) - len(after)) / len(before) if before else None
        ),
        "complete_candidate_repair": len(after) == 0,
        "before_total_error_count": error_count(initial_issues),
        "after_total_error_count": error_count(final_issues),
        "warning_count": quality[1],
        "info_count": quality[2],
        "model_calls": len(calls),
        "model_call_summary": summary,
        "semantic_rounds_completed": len({
            item["round"]
            for item in attempts
            if item.get("status") == "accepted"
        }),
        "rejected_attempt_count": sum(
            item.get("status") == "rejected" for item in attempts
        ),
        "operation_parse_invalid_count": sum(
            not item.get("operation_quality", {}).get(
                "operation_parse_valid",
                False,
            )
            for item in attempts
            if item.get("status") != "infrastructure_failed"
        ),
        "hardcoded_accessibility_value_count": sum(
            int(item.get("hardcoded_accessibility_value_count", 0))
            for item in qualities
        ),
        "interaction_attribute_removal_count": sum(
            int(item.get("interaction_attribute_removal_count", 0))
            for item in qualities
        ),
        "structural_operation_count": sum(
            int(item.get("structural_operation_count", 0))
            for item in qualities
        ),
        "changed_file_count": len(changed),
        "changed_files": changed,
        "safety_finding_count": len(safety),
        "attempts": attempts,
        "started_at": started_at,
        "completed_at": now_iso(),
        "output_path": recorded_path(output),
        "notes": "",
    }
    state.update({
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
    })
    write_json(output / "reports/formal_run.json", state)
    return state


def run_one(
    task: dict,
    model: dict,
    group: str,
    api_key: str,
    documents: list[dict],
    output_root: Path,
    resume: bool,
) -> dict:
    output = (
        output_root
        / "runs"
        / model["key"]
        / task["task_id"]
        / group
    )
    state_path = output / "reports/formal_run.json"
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
        detector_profile=DETECTOR_PROFILE,
    )
    selected = v2.match_frozen_issues(
        initial_issues,
        task,
        output / "res",
        require_all=True,
    )
    save_report(output, initial_issues, "android_xml_a11y_report_before.json")
    if group == "raw_baseline":
        result = run_raw_baseline(
            task,
            model,
            api_key,
            output,
            selected,
            initial_issues,
        )
    else:
        settings = load_json(PROTOCOL_PATH)["main_comparison"]["groups"][
            "full_enhanced"
        ]
        result = run_full_enhanced(
            task,
            model,
            api_key,
            output,
            initial_issues,
            documents,
            settings,
        )
    final_issues, calls, attempts, status, stop_reason = result
    return final_state(
        task,
        model,
        group,
        output,
        initial_issues,
        final_issues,
        calls,
        attempts,
        status,
        stop_reason,
        started_at,
    )


def state_row(state: dict) -> dict:
    values = {
        **state,
        "candidate_ids": ";".join(state.get("candidate_ids", [])),
        "issue_types": ";".join(state.get("issue_types", [])),
        "issue_subtypes": ";".join(state.get("issue_subtypes", [])),
        "changed_files": ";".join(state.get("changed_files", [])),
    }
    return {field: values.get(field, "") for field in RESULT_FIELDS}


def existing_states(output_root: Path) -> list[dict]:
    states = []
    runs = output_root / "runs"
    if not runs.is_dir():
        return states
    for path in sorted(runs.rglob("reports/formal_run.json")):
        try:
            states.append(load_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return states


def summarize(output_root: Path) -> dict:
    states = existing_states(output_root)
    summary_path = output_root / "formal_results.csv"
    write_csv(summary_path, [state_row(state) for state in states])
    manifest = {
        "schema_version": 1,
        "protocol_id": load_json(PROTOCOL_PATH)["protocol_id"],
        "updated_at": now_iso(),
        "recorded_group_runs": len(states),
        "completed_group_runs": sum(
            state.get("status") != "infrastructure_failed"
            for state in states
        ),
        "infrastructure_failed_group_runs": sum(
            state.get("status") == "infrastructure_failed"
            for state in states
        ),
        "model_counts": {
            model_key: sum(
                state.get("model_key") == model_key for state in states
            )
            for model_key in sorted({
                state.get("model_key") for state in states
            })
            if model_key
        },
        "summary": recorded_path(summary_path),
    }
    write_json(output_root / "run_manifest.json", manifest)
    return manifest


def run(args) -> dict:
    errors = verify_prepared_inputs()
    if errors:
        raise SystemExit(
            "V2 formal prepared-input validation failed:\n- "
            + "\n- ".join(errors)
        )
    protocol = load_json(PROTOCOL_PATH)
    source = load_json(prepared.SOURCE_MANIFEST)
    models = selected_models(protocol, args.models)
    tasks = source["tasks"]
    documents = load_documents()
    total = len(models) * len(tasks) * len(GROUPS)
    index = 0
    for model in models:
        with provider_environment(model) as api_key:
            if not api_key:
                raise SystemExit(
                    f"missing API key environment: {model['api_key_env']}"
                )
            validate_model_configuration(model["provider"], api_key)
            for task in tasks:
                for group in prepared.group_order(
                    model["key"],
                    task["task_id"],
                ):
                    index += 1
                    print(
                        f"[{index}/{total}] {model['key']} / "
                        f"{task['task_id']} / {group}"
                    )
                    run_one(
                        task,
                        model,
                        group,
                        api_key,
                        documents,
                        args.output,
                        args.resume,
                    )
    return summarize(args.output)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--models", required=True)
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


def main() -> None:
    args = parser().parse_args()
    args.output = args.output.resolve()
    if args.command == "verify":
        errors = verify_prepared_inputs()
        result = {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "model_calls": 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if errors:
            raise SystemExit(1)
    elif args.command == "run":
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = summarize(args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
