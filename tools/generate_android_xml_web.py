#!/usr/bin/env python3
"""Run the current SAFER-XML pipeline for an arbitrary web upload.

This runner is intentionally separate from frozen experiment executors. It
reuses their detector, retrieval, operation contract, and safety validators
without changing any implementation hash recorded by the formal study.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import generate_android_xml as base  # noqa: E402
from tools.android_xml_contract_v2_1 import (  # noqa: E402
    evaluate_and_commit_candidate,
)
from tools.android_xml_rag_prompt_contract import build_prompt_pair  # noqa: E402
from tools.generate import (  # noqa: E402
    MODEL_PROVIDER_CHOICES,
    ModelError,
    model_error_metadata,
    run_model_with_metadata,
    validate_model_configuration,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402


DETECTOR_PROFILE = "expanded_v3"
RAG_TOP_K = 2
PROMPT_CONTRACT = "v4_structured_hybrid"
OPERATION_CONTRACT = "android_xml_operation_contract_v2_1"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def initial_state(provider, model, max_rounds, max_attempts, initial_issues):
    return {
        "schema_version": 1,
        "pipeline": "SAFER-XML",
        "provider": provider,
        "model": model,
        "status": "running",
        "started_at": now_iso(),
        "max_rounds": max_rounds,
        "max_model_attempts_per_round": max_attempts,
        "uses_rag": True,
        "uses_detector_feedback": max_rounds > 1,
        "repairability_filtering": True,
        "detector_profile": DETECTOR_PROFILE,
        "retrieval_contract": PROMPT_CONTRACT,
        "rag_top_k": RAG_TOP_K,
        "operation_contract": OPERATION_CONTRACT,
        "initial_issue_quality": list(base.issue_quality(initial_issues)),
        "initial_error_count": base.error_count(initial_issues),
        "initial_repairability": base.repairability_counts(initial_issues),
        "rounds": [],
    }


def finish(output, input_res, issues, run_state, status, stop_reason):
    safety = base.validate_repair_safety(input_res, output / "res")
    base.save_report(output, issues)
    base.save_safety_report(output, safety)
    run_state.update({
        "status": status,
        "stop_reason": stop_reason,
        "completed_at": now_iso(),
        "final_issue_quality": list(base.issue_quality(issues)),
        "final_error_count": base.error_count(issues),
        "repair_rate": base.repair_rate(
            run_state["initial_error_count"],
            base.error_count(issues),
        ),
        "final_repairability": base.repairability_counts(issues),
        "deferred_issues": base.deferred_issues(issues),
        "safety_finding_count": len(safety),
    })
    base.save_json_artifact(output, "repair_run.json", run_state)
    return run_state


def run(args):
    input_package, input_res = base.package_paths(Path(args.input))
    initial_issues = base.run_xml_checker(
        input_res,
        detector_profile=DETECTOR_PROFILE,
    )
    base.save_report(input_package, initial_issues)

    output = Path(args.output).resolve()
    base.prepare_output(input_package, output, args.force)
    output_res = output / "res"
    run_state = initial_state(
        args.provider,
        args.model,
        args.max_rounds,
        args.max_model_attempts,
        initial_issues,
    )
    base.save_json_artifact(output, "repair_run.json", run_state)
    documents = load_documents()
    no_improvement_rounds = 0

    for round_number in range(1, args.max_rounds + 1):
        issues = base.run_xml_checker(
            output_res,
            detector_profile=DETECTOR_PROFILE,
        )
        base.save_report(output, issues)
        base.save_report(
            output,
            issues,
            f"android_xml_a11y_report_round_{round_number}.json",
        )
        safety = base.validate_repair_safety(input_res, output_res)
        base.save_safety_report(output, safety)
        selected = base.repairable_issues(issues)
        deferred = base.deferred_issues(issues)
        current_errors = base.error_count(issues)
        round_state = {
            "round": round_number,
            "before_quality": list(base.issue_quality(issues)),
            "before_error_count": current_errors,
            "repairable_issue_count": len(selected),
            "deferred_issue_count": len(deferred),
            "attempts": [],
        }
        run_state["rounds"].append(round_state)

        if current_errors == 0 and not safety:
            status = "completed" if not issues else "completed_with_observations"
            return finish(
                output,
                input_res,
                issues,
                run_state,
                status,
                "zero_xml_safe_errors",
            )
        if safety:
            return finish(
                output,
                input_res,
                issues,
                run_state,
                "failed",
                "structural_safety_failed",
            )
        if not selected:
            return finish(
                output,
                input_res,
                issues,
                run_state,
                "stopped_non_repairable_errors",
                "no_xml_safe_errors",
            )

        pair = build_prompt_pair(
            selected,
            output_res,
            documents,
            per_issue_limit=RAG_TOP_K,
            prompt_limit=RAG_TOP_K,
        )
        base_prompt = pair["rag"]
        base.save_round_artifact(
            output,
            f"repair_prompt_round_{round_number}.txt",
            base_prompt,
        )
        base.save_json_artifact(
            output,
            f"retrieval_trace_round_{round_number}.json",
            pair["trace"],
        )
        validate_model_configuration(args.provider, args.api_key)
        prompt = base_prompt
        accepted = False

        for attempt_number in range(1, args.max_model_attempts + 1):
            attempt_state = {"attempt": attempt_number, "status": "running"}
            round_state["attempts"].append(attempt_state)
            base.save_round_artifact(
                output,
                f"repair_prompt_round_{round_number}_attempt_{attempt_number}.txt",
                prompt,
            )
            try:
                result = run_model_with_metadata(
                    args.provider,
                    args.model,
                    prompt,
                    args.api_key,
                )
            except ModelError as exc:
                attempt_state.update({
                    "status": "model_error",
                    "error": str(exc),
                    "model_call": model_error_metadata(
                        exc,
                        args.provider,
                        args.model,
                    ),
                })
                finish(
                    output,
                    input_res,
                    issues,
                    run_state,
                    "failed",
                    "model_provider_error",
                )
                raise

            response = result["content"]
            attempt_state["model_call"] = result["metadata"]
            base.save_round_artifact(
                output,
                f"model_response_round_{round_number}_attempt_{attempt_number}.txt",
                response,
            )
            try:
                changed, candidate_issues = evaluate_and_commit_candidate(
                    output,
                    input_res,
                    issues,
                    response,
                    detector_profile=DETECTOR_PROFILE,
                )
                attempt_state.update({
                    "status": "accepted",
                    "after_quality": list(base.issue_quality(candidate_issues)),
                    "after_error_count": base.error_count(candidate_issues),
                    "changed_files": [
                        path.relative_to(output).as_posix()
                        for path in changed
                    ],
                })
                round_state["after_error_count"] = base.error_count(candidate_issues)
                accepted = True
                break
            except (ET.ParseError, TypeError, ValueError) as exc:
                attempt_state.update({"status": "rejected", "error": str(exc)})
                base.save_round_artifact(
                    output,
                    f"operation_error_round_{round_number}_attempt_{attempt_number}.txt",
                    str(exc) + "\n",
                )
                if attempt_number < args.max_model_attempts:
                    prompt = base.build_operation_retry_prompt(
                        base_prompt,
                        response,
                        str(exc),
                    )

        if accepted:
            no_improvement_rounds = 0
        else:
            round_state["after_error_count"] = current_errors
            no_improvement_rounds += 1
        round_state["no_improvement_streak"] = no_improvement_rounds
        base.save_json_artifact(output, "repair_run.json", run_state)

        if no_improvement_rounds >= 2:
            final_issues = base.run_xml_checker(
                output_res,
                detector_profile=DETECTOR_PROFILE,
            )
            return finish(
                output,
                input_res,
                final_issues,
                run_state,
                "no_improvement",
                "no_improvement",
            )

    final_issues = base.run_xml_checker(
        output_res,
        detector_profile=DETECTOR_PROFILE,
    )
    if base.error_count(final_issues) == 0:
        status = "completed" if not final_issues else "completed_with_observations"
        reason = "zero_xml_safe_errors"
    else:
        status = "max_iterations"
        reason = "max_iterations"
    return finish(output, input_res, final_issues, run_state, status, reason)


def main():
    parser = argparse.ArgumentParser(
        description="Run SAFER-XML V2.1 for a web-uploaded Android resource package."
    )
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument(
        "--provider",
        choices=MODEL_PROVIDER_CHOICES,
        default="deepseek",
    )
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--max-model-attempts", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_rounds <= 3:
        raise SystemExit("--max-rounds must be between 1 and 3.")
    if not 1 <= args.max_model_attempts <= 3:
        raise SystemExit("--max-model-attempts must be between 1 and 3.")
    run(args)


if __name__ == "__main__":
    try:
        main()
    except ModelError as exc:
        print(f"Model configuration or invocation failed: {exc}", file=sys.stderr)
        sys.exit(1)
