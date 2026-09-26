#!/usr/bin/env python3
"""Plan, run, resume, and summarize isolated Android XML ablations."""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.generate import validate_model_configuration  # noqa: E402
from tools.generate_android_xml import (  # noqa: E402
    run_xml_checker,
    save_report,
    save_safety_report,
    validate_repair_safety,
)
from tools.run_android_xml_experiment import (  # noqa: E402
    collect,
    issue_counts,
    model_call_summary,
    resource_hash,
    result_metrics,
    source_commit,
)
from tools.run_android_xml_multimodel import (  # noqa: E402
    load_protocol as load_subject_protocol,
    load_subjects,
)


DEFAULT_PROTOCOL = (
    ROOT / "experiments/android_xml_ablation/protocol_v1.json"
)
RESULT_FIELDS = [
    "protocol_id",
    "variant_key",
    "variant_display_name",
    "batch_status",
    "infrastructure_failure_reason",
    "app_id",
    "app_name",
    "category",
    "selected_interface_count",
    "input_resource_sha256",
    "before_error_count",
    "after_error_count",
    "error_repair_rate",
    "before_xml_safe_error_count",
    "after_xml_safe_error_count",
    "xml_safe_repair_rate",
    "after_warning_count",
    "after_info_count",
    "after_total_issue_count",
    "variant_status",
    "uses_rag",
    "uses_initial_detector_findings",
    "uses_iterative_detector_feedback",
    "uses_repairability_filtering",
    "max_rounds",
    "model_calls",
    "successful_model_calls",
    "failed_model_calls",
    "provider_attempts",
    "network_retries",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_ms",
    "rejected_attempts",
    "safety_findings",
    "run_path",
    "completed_at",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def relative(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def slug(value):
    import re
    result = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return result or "app"


def load_protocol(path):
    protocol = read_json(path)
    required = {
        "protocol_id",
        "status",
        "subject_protocol",
        "target_app_count",
        "provider",
        "model",
        "api_key_env",
        "base_url_env",
        "base_url",
        "settings",
        "variants",
        "output_root",
        "summary_csv",
        "run_manifest",
    }
    missing = sorted(required - set(protocol))
    if missing:
        raise SystemExit("消融协议缺少字段: " + ", ".join(missing))
    if protocol["status"] != "frozen":
        raise SystemExit("消融实验只能使用 status=frozen 的协议。")
    keys = [variant.get("key") for variant in protocol["variants"]]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise SystemExit("消融 variant key 必须存在且不能重复。")
    return protocol


def subjects_for(protocol):
    subject_protocol = load_subject_protocol(
        project_path(protocol["subject_protocol"])
    )
    subjects = load_subjects(subject_protocol)
    if len(subjects) != protocol["target_app_count"]:
        raise SystemExit("消融 App 数量与冻结协议不一致。")
    return subjects


def selected_variants(protocol, requested):
    variants = {variant["key"]: variant for variant in protocol["variants"]}
    if not requested:
        return list(protocol["variants"])
    keys = [value.strip() for value in requested.split(",") if value.strip()]
    unknown = sorted(set(keys) - set(variants))
    if unknown:
        raise SystemExit("未知消融变体: " + ", ".join(unknown))
    return [variants[key] for key in keys]


def selected_subjects(subjects, requested, limit):
    if requested:
        names = {
            value.strip().casefold()
            for value in requested.split(",") if value.strip()
        }
        subjects = [
            subject for subject in subjects
            if subject["app_name"].casefold() in names
            or subject["app_id"].casefold() in names
        ]
        if not subjects:
            raise SystemExit("--apps 没有匹配到 App。")
    if limit is not None:
        if limit < 1:
            raise SystemExit("--limit-apps 必须至少为 1。")
        subjects = subjects[:limit]
    return subjects


def run_path(protocol, variant, subject):
    return (
        project_path(protocol["output_root"])
        / variant["key"]
        / slug(subject["app_name"])
    )


def repair_rate(before, after):
    return None if before == 0 else (before - after) / before


def model_calls_from_repair_run(repair_run):
    return [
        attempt.get("model_call")
        for round_state in repair_run.get("rounds", [])
        for attempt in round_state.get("attempts", [])
        if isinstance(attempt.get("model_call"), dict)
    ]


def rejected_attempt_count(repair_run):
    return sum(
        attempt.get("status") == "rejected"
        for round_state in repair_run.get("rounds", [])
        for attempt in round_state.get("attempts", [])
    )


def infrastructure_failure(output):
    result_path = Path(output) / "ablation_result.json"
    if not result_path.exists():
        return "missing_ablation_result"
    try:
        result = read_json(result_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return "invalid_ablation_result"
    return result.get("infrastructure_failure_reason") or None


def completed(output):
    output = Path(output)
    return (output / "ablation_result.json").exists() and not infrastructure_failure(
        output
    )


def generator_command(protocol, variant, original, proposed):
    settings = protocol["settings"]
    command = [
        sys.executable,
        str(ROOT / "tools/generate_android_xml.py"),
        str(original),
        str(proposed),
        "--provider",
        protocol["provider"],
        "--model",
        protocol["model"],
        "--max-rounds",
        str(variant["max_rounds"]),
        "--max-model-attempts",
        str(settings["max_model_attempts_per_round"]),
        "--limit",
        str(settings["rag_limit"]),
        "--force",
    ]
    if not variant["uses_rag"]:
        command.append("--disable-rag")
    if not variant["uses_repairability_filtering"]:
        command.append("--disable-repairability-filter")
    return command


def task_environment(protocol):
    environment = os.environ.copy()
    api_key = environment.get(protocol["api_key_env"])
    provider_key_environment = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(protocol["provider"])
    if provider_key_environment and api_key:
        environment[provider_key_environment] = api_key
    environment[protocol["base_url_env"]] = protocol["base_url"]
    environment["LLM_MAX_OUTPUT_TOKENS"] = str(
        protocol["settings"]["max_output_tokens"]
    )
    if protocol["provider"] == "openai":
        environment["OPENAI_API_STYLE"] = protocol.get(
            "api_style", "responses"
        )
    if protocol["provider"] == "anthropic":
        environment["ANTHROPIC_AUTH_STYLE"] = protocol.get(
            "auth_style", "x_api_key"
        )
    return environment


def run_task(protocol, variant, subject, output, force=False):
    if output.exists():
        if not force:
            raise RuntimeError(f"输出目录已存在: {output}")
        shutil.rmtree(output)
    original = output / "original"
    proposed = output / "proposed"
    collect(
        Path(subject["source_path"]),
        original,
        selected_layouts=set(subject["layouts"]),
    )
    initial_issues = run_xml_checker(original / "res")
    save_report(original, initial_issues)
    input_hash = resource_hash(original / "res")
    expected_hash = subject.get("input_resource_sha256")
    if expected_hash and input_hash != expected_hash:
        raise RuntimeError(
            f"{subject['app_name']} 输入哈希变化，拒绝运行消融。"
        )
    config = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "variant": variant,
        "app_id": subject["app_id"],
        "app_name": subject["app_name"],
        "category": subject["category"],
        "layouts": subject["layouts"],
        "source_path": subject["source_path"],
        "source_commit": source_commit(Path(subject["source_path"])),
        "input_resource_sha256": input_hash,
        "provider": protocol["provider"],
        "model": protocol["model"],
        "api_key_environment": protocol["api_key_env"],
        "input_isolation": {
            "model_context": "stateless_single_request",
            "xml_source": "fresh_copy_from_frozen_subject",
            "allowed_prompt_sources": [
                "frozen_original_xml_resources",
                "current_variant_detector_findings",
                "knowledge_rag_documents_when_enabled",
                "current_variant_rejected_operation_when_retrying",
            ],
            "excluded_prompt_sources": [
                "other_model_outputs",
                "other_variant_outputs",
                "previous_experiment_results",
                "aggregate_statistics",
            ],
        },
        "created_at": now_iso(),
    }
    write_json(output / "ablation_config.json", config)
    started_at = now_iso()
    result = subprocess.run(
        generator_command(protocol, variant, original, proposed),
        capture_output=True,
        text=True,
        env=task_environment(protocol),
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "runner_stdout.txt").write_text(
        result.stdout, encoding="utf-8"
    )
    (output / "runner_stderr.txt").write_text(
        result.stderr, encoding="utf-8"
    )
    repair_run_path = proposed / "reports/repair_run.json"
    repair_run = read_json(repair_run_path) if repair_run_path.exists() else {}
    failure_code = repair_run.get("failure", {}).get("code")
    if failure_code == "MODEL_PROVIDER_ERROR":
        failure_reason = "model_provider_error"
    elif not repair_run_path.exists():
        failure_reason = "missing_repair_run"
    else:
        failure_reason = None
    if (proposed / "res").exists():
        final_issues = run_xml_checker(proposed / "res")
        safety = validate_repair_safety(original / "res", proposed / "res")
        save_report(proposed, final_issues)
        save_safety_report(proposed, safety)
    else:
        final_issues = initial_issues
        safety = []
    calls = model_calls_from_repair_run(repair_run)
    call_summary = model_call_summary(calls)
    comparison = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "variant_key": variant["key"],
        "app_id": subject["app_id"],
        "app_name": subject["app_name"],
        "started_at": started_at,
        "completed_at": now_iso(),
        "batch_status": (
            "infrastructure_failed" if failure_reason else "completed"
        ),
        "infrastructure_failure_reason": failure_reason,
        "return_code": result.returncode,
        "variant_status": repair_run.get("status", "runner_failed"),
        "original": issue_counts(initial_issues),
        "final": issue_counts(final_issues),
        "metrics": result_metrics(initial_issues, final_issues, safety),
        "model_calls": len(calls),
        "model_call_summary": call_summary,
        "rejected_attempts": rejected_attempt_count(repair_run),
    }
    write_json(output / "ablation_result.json", comparison)
    return comparison


def result_row(protocol, variant, subject, output):
    result = read_json(output / "ablation_result.json")
    initial = result.get("original", {})
    final = result.get("final", {})
    summary = result.get("model_call_summary", {})
    usage = summary.get("usage", {})
    before_errors = initial.get("error_count", 0)
    after_errors = final.get("error_count", before_errors)
    before_xml_safe = initial.get("repairable_error_count", 0)
    after_xml_safe = final.get("repairable_error_count", before_xml_safe)
    return {
        "protocol_id": protocol["protocol_id"],
        "variant_key": variant["key"],
        "variant_display_name": variant["display_name"],
        "batch_status": result.get("batch_status", "infrastructure_failed"),
        "infrastructure_failure_reason": result.get(
            "infrastructure_failure_reason"
        ) or "",
        "app_id": subject["app_id"],
        "app_name": subject["app_name"],
        "category": subject["category"],
        "selected_interface_count": len(subject["layouts"]),
        "input_resource_sha256": subject.get("input_resource_sha256"),
        "before_error_count": before_errors,
        "after_error_count": after_errors,
        "error_repair_rate": repair_rate(before_errors, after_errors),
        "before_xml_safe_error_count": before_xml_safe,
        "after_xml_safe_error_count": after_xml_safe,
        "xml_safe_repair_rate": repair_rate(
            before_xml_safe,
            after_xml_safe,
        ),
        "after_warning_count": final.get("warning_count", 0),
        "after_info_count": final.get("info_count", 0),
        "after_total_issue_count": final.get("total_issue_count", 0),
        "variant_status": result.get("variant_status", "runner_failed"),
        "uses_rag": variant["uses_rag"],
        "uses_initial_detector_findings": variant[
            "uses_initial_detector_findings"
        ],
        "uses_iterative_detector_feedback": variant[
            "uses_iterative_detector_feedback"
        ],
        "uses_repairability_filtering": variant[
            "uses_repairability_filtering"
        ],
        "max_rounds": variant["max_rounds"],
        "model_calls": result.get("model_calls", 0),
        "successful_model_calls": summary.get("successful_model_calls", 0),
        "failed_model_calls": summary.get("failed_model_calls", 0),
        "provider_attempts": summary.get("provider_attempts", 0),
        "network_retries": summary.get("network_retries", 0),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "duration_ms": summary.get("duration_ms", 0),
        "rejected_attempts": result.get("rejected_attempts", 0),
        "safety_findings": result.get("metrics", {}).get(
            "safety_findings", 0
        ),
        "run_path": relative(output),
        "completed_at": result.get("completed_at", ""),
    }


def summarize(protocol):
    subjects = subjects_for(protocol)
    subject_by_slug = {slug(subject["app_name"]): subject for subject in subjects}
    rows = []
    for variant in protocol["variants"]:
        variant_root = project_path(protocol["output_root"]) / variant["key"]
        if not variant_root.exists():
            continue
        for output in sorted(path for path in variant_root.iterdir() if path.is_dir()):
            subject = subject_by_slug.get(output.name)
            if subject and (output / "ablation_result.json").exists():
                rows.append(result_row(protocol, variant, subject, output))
    summary_path = project_path(protocol["summary_csv"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "updated_at": now_iso(),
        "recorded_runs": len(rows),
        "completed_runs": sum(row["batch_status"] == "completed" for row in rows),
        "infrastructure_failed_runs": sum(
            row["batch_status"] != "completed" for row in rows
        ),
        "variant_counts": dict(Counter(row["variant_key"] for row in rows)),
        "summary_csv": relative(summary_path),
        "rows": rows,
    }
    write_json(project_path(protocol["run_manifest"]), manifest)
    return manifest


def command_plan(args, protocol):
    subjects = selected_subjects(subjects_for(protocol), args.apps, args.limit_apps)
    variants = selected_variants(protocol, args.variants)
    plan = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "created_at": now_iso(),
        "provider": protocol["provider"],
        "model": protocol["model"],
        "variant_count": len(variants),
        "app_count": len(subjects),
        "task_count": len(variants) * len(subjects),
        "variants": variants,
        "apps": subjects,
    }
    path = project_path(protocol["output_root"]).parent / "experiment_plan.json"
    write_json(path, plan)
    print(json.dumps({
        "plan": relative(path),
        "variants": len(variants),
        "apps": len(subjects),
        "tasks": len(variants) * len(subjects),
    }, ensure_ascii=False, indent=2))


def command_run(args, protocol):
    api_key = os.environ.get(protocol["api_key_env"])
    if not api_key:
        raise SystemExit(
            f"缺少 API Key 环境变量: {protocol['api_key_env']}"
        )
    validate_model_configuration(protocol["provider"], api_key)
    subjects = selected_subjects(subjects_for(protocol), args.apps, args.limit_apps)
    variants = selected_variants(protocol, args.variants)
    tasks = [(variant, subject) for variant in variants for subject in subjects]
    for index, (variant, subject) in enumerate(tasks, 1):
        output = run_path(protocol, variant, subject)
        if args.resume and completed(output):
            print(
                f"[{index}/{len(tasks)}] 跳过已完成: "
                f"{variant['key']} / {subject['app_name']}"
            )
            continue
        if output.exists() and not args.force:
            print(f"[{index}/{len(tasks)}] 已存在但未完成，跳过: {output}")
            if args.fail_fast:
                break
            continue
        print(
            f"[{index}/{len(tasks)}] {variant['key']} / "
            f"{subject['app_name']}"
        )
        try:
            result = run_task(
                protocol, variant, subject, output, force=args.force
            )
        except Exception as exc:
            output.mkdir(parents=True, exist_ok=True)
            write_json(output / "ablation_result.json", {
                "schema_version": 1,
                "protocol_id": protocol["protocol_id"],
                "variant_key": variant["key"],
                "app_id": subject["app_id"],
                "app_name": subject["app_name"],
                "completed_at": now_iso(),
                "batch_status": "infrastructure_failed",
                "infrastructure_failure_reason": "runner_exception",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            print(f"  运行失败: {exc}", file=sys.stderr)
            if args.fail_fast:
                break
            continue
        if result.get("infrastructure_failure_reason"):
            print(
                "  基础设施失败: "
                + result["infrastructure_failure_reason"],
                file=sys.stderr,
            )
            if args.fail_fast:
                break
    manifest = summarize(protocol)
    print(json.dumps({
        "recorded_runs": manifest["recorded_runs"],
        "completed_runs": manifest["completed_runs"],
        "infrastructure_failed_runs": manifest["infrastructure_failed_runs"],
        "summary_csv": manifest["summary_csv"],
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Run a frozen, model-isolated Android XML ablation."
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        child = subparsers.add_parser(name)
        child.add_argument("--variants", help="Comma-separated variant keys")
        child.add_argument("--apps", help="Comma-separated App names or IDs")
        child.add_argument("--limit-apps", type=int)
        if name == "run":
            child.add_argument("--resume", action="store_true")
            child.add_argument("--force", action="store_true")
            child.add_argument("--fail-fast", action="store_true")
    subparsers.add_parser("summarize")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.command == "plan":
        command_plan(args, protocol)
    elif args.command == "run":
        command_run(args, protocol)
    else:
        manifest = summarize(protocol)
        print(json.dumps({
            "recorded_runs": manifest["recorded_runs"],
            "completed_runs": manifest["completed_runs"],
            "infrastructure_failed_runs": manifest[
                "infrastructure_failed_runs"
            ],
            "summary_csv": manifest["summary_csv"],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
