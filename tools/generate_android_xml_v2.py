#!/usr/bin/env python3
"""Isolated V2 Android XML repair runner for the approved internal pilot."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("one_shot_baseline", "v2_no_rag", "v2_full")
VALIDATED_CODES = {
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
}
GROUP_MAX_ROUNDS = {
    "one_shot_baseline": 1,
    "v2_no_rag": 2,
    "v2_full": 2,
}

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.generate import (  # noqa: E402
    MODEL_PROVIDER_CHOICES,
    ModelError,
    model_error_metadata,
    run_model_with_metadata,
    validate_model_configuration,
)
from tools.generate_android_xml import (  # noqa: E402
    build_operation_retry_prompt,
    error_count,
    evaluate_and_commit_candidate,
    format_files,
    format_issues,
    issue_files,
    issue_quality,
    issue_report,
    issue_severity,
    package_paths,
    prepare_output,
    repair_rate,
    repairability_counts,
    run_xml_checker,
    save_json_artifact,
    save_report,
    save_round_artifact,
    save_safety_report,
    validate_repair_safety,
)
from tools.retrieval.app_context import (  # noqa: E402
    retrieve_app_context_for_issues,
)
from tools.retrieval.build_rag_prompt import format_document  # noqa: E402
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.retrieval.v2_hybrid import retrieve_for_issues  # noqa: E402
from tools.run_android_xml_experiment import build_baseline_prompt  # noqa: E402


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def v2_actionable_issues(issues):
    return [
        issue
        for issue in issues
        if issue_severity(issue) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
        and issue.get("code") in VALIDATED_CODES
    ]


def v2_deferred_issues(issues):
    actionable_ids = {id(issue) for issue in v2_actionable_issues(issues)}
    return [issue for issue in issues if id(issue) not in actionable_ids]


def format_app_context(results):
    if not results:
        return "No App-source evidence was retrieved for these components."
    sections = []
    for index, item in enumerate(results, 1):
        sections.append(
            f"### Context {index}: {item['path']}:{item['line_start']}-"
            f"{item['line_end']}\n"
            f"Issue: {item.get('issue_code')} at {item.get('issue_selector')}\n"
            f"Kind: {item['kind']}\n"
            "```\n"
            f"{item['excerpt']}\n"
            "```"
        )
    return "\n\n".join(sections)


def compact_knowledge_trace(results):
    return [
        {
            key: result.get(key)
            for key in (
                "doc_id",
                "reason",
                "lexical_score",
                "dense_score",
                "hybrid_score",
                "metadata",
                "issue_index",
                "issue_code",
            )
        }
        for result in results
    ]


def build_v2_prompt(
    issues,
    res_dir,
    source_root,
    use_normative_rag,
    use_app_context,
):
    knowledge_results = []
    if use_normative_rag:
        knowledge_results = retrieve_for_issues(
            issues,
            load_documents(),
            per_issue_limit=3,
            prompt_limit=6,
            direct_limit=2,
            candidate_limit=20,
        )
    context_results = []
    if use_app_context:
        context_results = retrieve_app_context_for_issues(
            source_root,
            issues,
            per_issue_limit=4,
            prompt_limit=12,
        )
    if knowledge_results:
        knowledge_text = "\n\n".join(
            format_document(result["document"])
            for result in knowledge_results
        )
    elif use_normative_rag:
        knowledge_text = "No sufficiently relevant Android XML knowledge was retrieved."
    else:
        knowledge_text = "Normative RAG is disabled for this comparison group."
    context_text = (
        format_app_context(context_results)
        if use_app_context
        else "App-context retrieval is disabled for this comparison group."
    )
    files = issue_files(issues, res_dir)
    prompt = f"""You are an accessibility-focused Android XML repair assistant.

Repair only the reported high-confidence XML-safe accessibility errors.
Preserve behavior, element types, ids, styles, dimensions, hierarchy, include tags, input restrictions, and existing resource references.
Make the smallest necessary changes and do not rewrite unrelated files.
Prefer stable string resources over hardcoded accessibility text.
Do not hide meaningful images from accessibility services.
Do not set a fixed contentDescription on stateful controls.
Use App-source evidence only to infer the purpose of the exact current-App component. Do not invent behavior that the evidence does not support.

Retrieved Android accessibility knowledge:

{knowledge_text}

Retrieved evidence from the current frozen App source tree:

{context_text}

Detected Android XML accessibility errors:

{format_issues(issues, res_dir)}

Current XML files:

{format_files(files, res_dir)}

Return only a strict JSON object with no markdown or explanation:
{{
  "operations": [
    {{
      "op": "set_attribute",
      "path": "res/layout/example.xml",
      "selector": "/LinearLayout[1]/ImageButton[1]",
      "attribute": "android:contentDescription",
      "value": "@string/example_description"
    }},
    {{
      "op": "add_string_resource",
      "path": "res/values/strings.xml",
      "name": "example_description",
      "value": "Example description"
    }}
  ]
}}

Allowed operations are remove_attribute, set_attribute, remove_attribute_value, and add_string_resource.
For element operations, copy the exact absolute selector from the detected issue.
Do not output complete XML files, create files, delete files, or delete resources.
"""
    trace = {
        "source_root": str(Path(source_root).resolve()),
        "uses_normative_rag": use_normative_rag,
        "uses_app_context_rag": use_app_context,
        "dense_backend": "disabled_not_validated",
        "knowledge_documents": compact_knowledge_trace(knowledge_results),
        "knowledge_document_count": len(knowledge_results),
        "knowledge_injected_characters": len(knowledge_text),
        "app_context": context_results,
        "app_context_count": len(context_results),
        "app_context_injected_characters": len(context_text),
    }
    return prompt, trace


def group_prompt(group, issues, res_dir, source_root):
    if group == "one_shot_baseline":
        return build_baseline_prompt(res_dir), {
            "source_root": str(Path(source_root).resolve()),
            "uses_normative_rag": False,
            "uses_app_context_rag": False,
            "knowledge_documents": [],
            "knowledge_document_count": 0,
            "knowledge_injected_characters": 0,
            "app_context": [],
            "app_context_count": 0,
            "app_context_injected_characters": 0,
        }
    return build_v2_prompt(
        v2_actionable_issues(issues),
        res_dir,
        source_root,
        use_normative_rag=group == "v2_full",
        use_app_context=group == "v2_full",
    )


def finish_state(run_state, issues, input_res, output_package, status, stop_reason):
    safety = validate_repair_safety(input_res, output_package / "res")
    save_report(output_package, issues)
    save_safety_report(output_package, safety)
    run_state.update({
        "status": status,
        "stop_reason": stop_reason,
        "completed_at": now_iso(),
        "final_issue_quality": list(issue_quality(issues)),
        "final_error_count": error_count(issues),
        "final_eligible_error_count": len(v2_actionable_issues(issues)),
        "repair_rate": repair_rate(
            run_state["initial_error_count"],
            error_count(issues),
        ),
        "final_repairability": repairability_counts(issues),
        "deferred_issue_count": len(v2_deferred_issues(issues)),
        "safety_finding_count": len(safety),
    })
    save_json_artifact(output_package, "v2_repair_run.json", run_state)
    return run_state


def run_group(
    input_package,
    output_package,
    source_root,
    group,
    provider,
    model,
    api_key=None,
    max_format_corrections=3,
    force=False,
    dry_run=False,
):
    input_package, input_res = package_paths(Path(input_package))
    source_root = Path(source_root).resolve()
    if not source_root.is_dir():
        raise SystemExit(f"Current App source root does not exist: {source_root}")
    output_package = Path(output_package).resolve()
    initial_issues = run_xml_checker(input_res)
    prepare_output(input_package, output_package, force)
    output_res = output_package / "res"
    max_rounds = GROUP_MAX_ROUNDS[group]
    run_state = {
        "schema_version": 1,
        "protocol_id": "android_xml_v2_internal_pilot",
        "protocol_version": 2,
        "group": group,
        "provider": provider,
        "model": model,
        "source_root": str(source_root),
        "input_package": str(input_package),
        "started_at": now_iso(),
        "status": "dry_run" if dry_run else "running",
        "max_semantic_rounds": max_rounds,
        "max_format_corrections_per_round": max_format_corrections,
        "initial_issue_quality": list(issue_quality(initial_issues)),
        "initial_error_count": error_count(initial_issues),
        "initial_eligible_error_count": len(v2_actionable_issues(initial_issues)),
        "initial_repairability": repairability_counts(initial_issues),
        "semantic_rounds": [],
        "model_calls": 0,
        "format_corrections_used": 0,
        "rejected_attempts": 0,
    }
    save_json_artifact(output_package, "v2_repair_run.json", run_state)

    if dry_run:
        prompt, trace = group_prompt(group, initial_issues, output_res, source_root)
        save_round_artifact(output_package, "repair_prompt_round_1_attempt_1.txt", prompt)
        save_json_artifact(output_package, "retrieval_trace_round_1.json", trace)
        run_state["prompt_characters"] = len(prompt)
        return finish_state(
            run_state,
            initial_issues,
            input_res,
            output_package,
            "dry_run",
            "model_execution_disabled",
        )

    validate_model_configuration(provider, api_key)
    for round_number in range(1, max_rounds + 1):
        issues = run_xml_checker(output_res)
        save_report(
            output_package,
            issues,
            f"android_xml_a11y_report_round_{round_number}.json",
        )
        current_errors = error_count(issues)
        eligible = v2_actionable_issues(issues)
        if current_errors == 0:
            return finish_state(
                run_state, issues, input_res, output_package, "completed", "zero_errors"
            )
        if group != "one_shot_baseline" and not eligible:
            return finish_state(
                run_state,
                issues,
                input_res,
                output_package,
                "completed_with_deferred_errors",
                "no_validated_xml_safe_errors",
            )
        prompt, trace = group_prompt(group, issues, output_res, source_root)
        save_json_artifact(
            output_package,
            f"retrieval_trace_round_{round_number}.json",
            trace,
        )
        round_state = {
            "round": round_number,
            "before_error_count": current_errors,
            "eligible_error_count": len(eligible),
            "prompt_characters": len(prompt),
            "attempts": [],
        }
        run_state["semantic_rounds"].append(round_state)
        accepted = False
        attempt_prompt = prompt
        for attempt in range(1, max_format_corrections + 1):
            save_round_artifact(
                output_package,
                f"repair_prompt_round_{round_number}_attempt_{attempt}.txt",
                attempt_prompt,
            )
            attempt_state = {"attempt": attempt}
            round_state["attempts"].append(attempt_state)
            run_state["model_calls"] += 1
            if attempt > 1:
                run_state["format_corrections_used"] += 1
            try:
                result = run_model_with_metadata(
                    provider,
                    model,
                    attempt_prompt,
                    api_key,
                )
            except ModelError as exc:
                attempt_state.update({
                    "status": "model_error",
                    "error": str(exc),
                    "model_call": model_error_metadata(exc, provider, model),
                })
                run_state["failure"] = {
                    "code": "MODEL_PROVIDER_ERROR",
                    "message": str(exc),
                }
                return finish_state(
                    run_state,
                    issues,
                    input_res,
                    output_package,
                    "infrastructure_failed",
                    "model_provider_error",
                )
            response = result["content"]
            attempt_state["model_call"] = result["metadata"]
            save_round_artifact(
                output_package,
                f"model_response_round_{round_number}_attempt_{attempt}.txt",
                response,
            )
            try:
                changed, candidate_issues = evaluate_and_commit_candidate(
                    output_package,
                    input_res,
                    issues,
                    response,
                )
                attempt_state.update({
                    "status": "accepted",
                    "after_error_count": error_count(candidate_issues),
                    "changed_files": [
                        path.relative_to(output_package).as_posix()
                        for path in changed
                    ],
                })
                round_state["after_error_count"] = error_count(candidate_issues)
                accepted = True
                break
            except (ValueError, ET.ParseError) as exc:
                run_state["rejected_attempts"] += 1
                attempt_state.update({"status": "rejected", "error": str(exc)})
                save_round_artifact(
                    output_package,
                    f"operation_error_round_{round_number}_attempt_{attempt}.txt",
                    str(exc) + "\n",
                )
                if attempt < max_format_corrections:
                    attempt_prompt = build_operation_retry_prompt(
                        prompt,
                        response,
                        str(exc),
                    )
        save_json_artifact(output_package, "v2_repair_run.json", run_state)
        if not accepted:
            return finish_state(
                run_state,
                issues,
                input_res,
                output_package,
                "no_improvement",
                "semantic_round_failed_to_reduce_error_count",
            )

    final_issues = run_xml_checker(output_res)
    if error_count(final_issues) == 0:
        status = "completed"
        reason = "zero_errors"
    elif not v2_actionable_issues(final_issues):
        status = "completed_with_deferred_errors"
        reason = "no_validated_xml_safe_errors"
    else:
        status = "max_iterations"
        reason = "max_semantic_rounds"
    return finish_state(
        run_state,
        final_issues,
        input_res,
        output_package,
        status,
        reason,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Frozen Android XML input package")
    parser.add_argument("output", help="V2 group output directory")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--group", choices=GROUPS, required=True)
    parser.add_argument("--provider", choices=MODEL_PROVIDER_CHOICES, default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-format-corrections", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.max_format_corrections < 1:
        raise SystemExit("--max-format-corrections must be at least 1")
    state = run_group(
        args.input,
        args.output,
        args.source_root,
        args.group,
        args.provider,
        args.model,
        api_key=args.api_key,
        max_format_corrections=args.max_format_corrections,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(json.dumps({
        "group": state["group"],
        "status": state["status"],
        "initial_error_count": state["initial_error_count"],
        "final_error_count": state["final_error_count"],
        "model_calls": state["model_calls"],
        "output": str(Path(args.output).resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
