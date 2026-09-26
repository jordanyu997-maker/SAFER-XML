#!/usr/bin/env python3
"""Plan, run, and summarize the recorded Android XML multi-model study."""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.generate import api_client_headers  # noqa: E402


DEFAULT_PROTOCOL = (
    ROOT / "experiments" / "android_xml_multimodel" / "protocol_v1.json"
)

RESULT_FIELDS = [
    "protocol_id",
    "phase",
    "batch_status",
    "infrastructure_failure_reason",
    "model_key",
    "model_display_name",
    "provider",
    "requested_model",
    "detector_profile",
    "api_streaming",
    "baseline_resolved_models",
    "enhanced_resolved_models",
    "repetition",
    "app_id",
    "app_name",
    "category",
    "selected_interface_count",
    "input_resource_sha256",
    "before_error_count",
    "before_warning_count",
    "before_info_count",
    "before_total_issue_count",
    "before_xml_safe_error_count",
    "baseline_after_error_count",
    "enhanced_after_error_count",
    "baseline_after_warning_count",
    "enhanced_after_warning_count",
    "baseline_after_info_count",
    "enhanced_after_info_count",
    "baseline_after_total_issue_count",
    "enhanced_after_total_issue_count",
    "baseline_after_xml_safe_error_count",
    "enhanced_after_xml_safe_error_count",
    "baseline_error_repair_rate",
    "enhanced_error_repair_rate",
    "baseline_xml_safe_repair_rate",
    "enhanced_xml_safe_repair_rate",
    "baseline_status",
    "enhanced_status",
    "baseline_iterations",
    "enhanced_iterations",
    "baseline_rejected_outputs",
    "enhanced_rejected_attempts",
    "baseline_model_calls",
    "enhanced_model_calls",
    "baseline_successful_model_calls",
    "enhanced_successful_model_calls",
    "baseline_failed_model_calls",
    "enhanced_failed_model_calls",
    "baseline_provider_attempts",
    "enhanced_provider_attempts",
    "baseline_network_retries",
    "enhanced_network_retries",
    "baseline_http_statuses",
    "enhanced_http_statuses",
    "baseline_input_tokens",
    "baseline_output_tokens",
    "baseline_total_tokens",
    "enhanced_input_tokens",
    "enhanced_output_tokens",
    "enhanced_total_tokens",
    "baseline_duration_ms",
    "enhanced_duration_ms",
    "baseline_safety_findings",
    "enhanced_safety_findings",
    "source_review_status",
    "professional_review_status",
    "baseline_semantic_correct_count",
    "baseline_semantic_incorrect_count",
    "baseline_semantic_pending_count",
    "enhanced_semantic_correct_count",
    "enhanced_semantic_incorrect_count",
    "enhanced_semantic_pending_count",
    "notes",
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


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative_project_path(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def slug(value):
    result = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return result or "app"


def load_protocol(path):
    protocol = read_json(path)
    required = {
        "protocol_id",
        "status",
        "subject_manifest",
        "subject_protocol_version",
        "target_app_count",
        "repetitions",
        "models",
        "settings",
        "output_root",
    }
    missing = sorted(required - set(protocol))
    if missing:
        raise SystemExit(f"实验协议缺少字段: {', '.join(missing)}")
    keys = [model.get("key") for model in protocol["models"]]
    if len(keys) != len(set(keys)) or any(not key for key in keys):
        raise SystemExit("模型 key 必须存在且不能重复。")
    if protocol["repetitions"] < 1:
        raise SystemExit("repetitions 必须至少为 1。")
    return protocol


def load_subjects(protocol):
    manifest_path = project_path(protocol["subject_manifest"])
    manifest = read_json(manifest_path)
    candidates = [
        record
        for record in manifest.get("runs", [])
        if record.get("protocol_version") == protocol["subject_protocol_version"]
        and record.get("protocol_status") == "valid"
        and record.get("experiment_phase") == "formal"
    ]
    selected = {}
    for record in sorted(candidates, key=lambda item: item.get("completed_at", "")):
        selected[record["app_id"]] = record

    subjects = []
    for app_id, record in selected.items():
        previous_run = project_path(record["result_path"])
        config_path = previous_run / "experiment_config.json"
        if not config_path.exists():
            raise SystemExit(f"找不到旧实验配置: {config_path}")
        config = read_json(config_path)
        source = Path(config.get("source_path", ""))
        if not source.exists():
            raise SystemExit(
                f"{record['app_name']} 的源码目录不存在: {source}"
            )
        subjects.append({
            "app_id": app_id,
            "app_name": record["app_name"],
            "category": record["category"],
            "layouts": list(record["layouts"]),
            "source_path": str(source.resolve()),
            "source_commit": record.get("source_commit"),
            "input_resource_sha256": record.get("input_resource_sha256"),
            "previous_result_path": record["result_path"],
        })

    subjects.sort(key=lambda item: item["app_name"].casefold())
    expected = protocol["target_app_count"]
    if len(subjects) != expected:
        raise SystemExit(
            f"协议要求 {expected} 个 App，但旧正式索引得到 {len(subjects)} 个。"
        )
    return subjects


def selected_models(protocol, requested):
    models = {model["key"]: model for model in protocol["models"]}
    if not requested:
        return list(protocol["models"])
    keys = [item.strip() for item in requested.split(",") if item.strip()]
    unknown = sorted(set(keys) - set(models))
    if unknown:
        raise SystemExit(f"未知模型 key: {', '.join(unknown)}")
    return [models[key] for key in keys]


def selected_subjects(subjects, requested, limit_apps):
    if requested:
        names = {item.strip().casefold() for item in requested.split(",") if item.strip()}
        subjects = [
            subject
            for subject in subjects
            if subject["app_name"].casefold() in names
            or subject["app_id"].casefold() in names
        ]
        if not subjects:
            raise SystemExit("--apps 没有匹配到任何正式实验 App。")
    if limit_apps is not None:
        if limit_apps < 1:
            raise SystemExit("--limit-apps 必须至少为 1。")
        subjects = subjects[:limit_apps]
    return subjects


def repetition_numbers(protocol, requested):
    maximum = protocol["repetitions"]
    if not requested:
        return list(range(1, maximum + 1))
    numbers = []
    for item in requested.split(","):
        number = int(item.strip())
        if number < 1 or number > maximum:
            raise SystemExit(f"重复编号必须在 1 到 {maximum} 之间。")
        numbers.append(number)
    return sorted(set(numbers))


def build_tasks(protocol, models, subjects, repetitions, phase):
    output_root = project_path(protocol["output_root"])
    tasks = []
    for model in models:
        for repetition in repetitions:
            for subject in subjects:
                output = (
                    output_root
                    / phase
                    / model["key"]
                    / f"rep_{repetition:02d}"
                    / slug(subject["app_name"])
                )
                tasks.append({
                    "phase": phase,
                    "model": model,
                    "repetition": repetition,
                    "subject": subject,
                    "output": output,
                })
    return tasks


def task_command(protocol, task):
    settings = protocol["settings"]
    subject = task["subject"]
    model = task["model"]
    run_id = (
        f"{protocol['protocol_id']}_{task['phase']}_{model['key']}_"
        f"rep_{task['repetition']:02d}"
    )
    command = [
        sys.executable,
        str(ROOT / "tools" / "run_android_xml_experiment.py"),
        subject["source_path"],
        str(task["output"]),
        "--app-id",
        subject["app_id"],
        "--app-name",
        subject["app_name"],
        "--category",
        subject["category"],
        "--layouts",
        ",".join(subject["layouts"]),
        "--run-id",
        run_id,
        "--protocol-version",
        str(protocol.get("runner_protocol_version", 5)),
        "--protocol-id",
        protocol["protocol_id"],
        "--experiment-phase",
        task["phase"],
        "--provider",
        model["provider"],
        "--model",
        model["model"],
        "--max-rounds",
        str(settings["max_rounds"]),
        "--max-model-attempts",
        str(settings["max_model_attempts_per_round"]),
        "--rag-limit",
        str(settings["rag_limit"]),
        "--skip-manifest-update",
    ]
    detector_profile = settings.get("detector_profile")
    if detector_profile:
        command.extend(["--detector-profile", detector_profile])
    return command


def task_environment(protocol, model):
    environment = os.environ.copy()
    provider_key_environment = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(model["provider"])
    experiment_key = environment.get(model["api_key_env"])
    if provider_key_environment and experiment_key:
        environment[provider_key_environment] = experiment_key
    environment["LLM_MAX_OUTPUT_TOKENS"] = str(
        protocol["settings"]["max_output_tokens"]
    )
    environment[model["base_url_env"]] = model["base_url"]
    if model["provider"] == "openai":
        environment["OPENAI_API_STYLE"] = model.get(
            "api_style", "responses"
        )
    if model["provider"] == "anthropic":
        environment["ANTHROPIC_AUTH_STYLE"] = model.get(
            "auth_style", "x_api_key"
        )
    return environment


def load_preflight(protocol):
    path = project_path(protocol["preflight_report"])
    return read_json(path) if path.exists() else {"models": []}


def exact_verified_models(protocol):
    report = load_preflight(protocol)
    return {
        item.get("model_key")
        for item in report.get("models", [])
        if item.get("exact_model_id_available") is True
    }


def preflight_one(model):
    key_name = model["api_key_env"]
    api_key = os.environ.get(key_name)
    result = {
        "model_key": model["key"],
        "provider": model["provider"],
        "requested_model": model["model"],
        "models_url": model["models_url"],
        "checked_at": now_iso(),
        "api_key_environment": key_name,
        "api_key_present": bool(api_key),
        "exact_model_id_available": False,
    }
    if not api_key:
        result["status"] = "missing_api_key"
        return result

    headers = api_client_headers()
    if model["provider"] == "anthropic":
        auth_style = model.get("auth_style", "x_api_key")
        if auth_style == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_style == "x_api_key":
            headers["x-api-key"] = api_key
        else:
            result.update({
                "status": "invalid_auth_style",
                "error": f"Unsupported Anthropic auth_style: {auth_style}",
            })
            return result
        headers.update({
            "anthropic-version": os.environ.get(
                "ANTHROPIC_API_VERSION", "2023-06-01"
            ),
        })
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(model["models_url"], headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        result.update({
            "status": "http_error",
            "http_status": exc.code,
            "error": detail,
        })
        return result
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result.update({"status": "request_error", "error": str(exc)})
        return result

    model_ids = sorted({
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    })
    requested = model["model"]
    suggestions = [
        model_id
        for model_id in model_ids
        if any(part in model_id.casefold() for part in requested.casefold().split("-"))
    ][:30]
    result.update({
        "status": "available" if requested in model_ids else "model_not_found",
        "exact_model_id_available": requested in model_ids,
        "available_model_count": len(model_ids),
        "available_model_ids": model_ids,
        "similar_model_ids": suggestions,
    })
    return result


def command_plan(args, protocol):
    subjects = selected_subjects(
        load_subjects(protocol), args.apps, args.limit_apps
    )
    models = selected_models(protocol, args.models)
    repetitions = repetition_numbers(protocol, args.repetitions)
    tasks = build_tasks(protocol, models, subjects, repetitions, args.phase)
    payload = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "protocol_status": protocol["status"],
        "created_at": now_iso(),
        "phase": args.phase,
        "model_count": len(models),
        "subject_count": len(subjects),
        "repetitions": repetitions,
        "method_groups_per_task": protocol["groups"],
        "app_level_runs": len(tasks),
        "minimum_model_calls": len(tasks),
        "models": [
            {
                "key": model["key"],
                "provider": model["provider"],
                "model": model["model"],
                "model_id_status": model["model_id_status"],
            }
            for model in models
        ],
        "subjects": subjects,
        "tasks": [
            {
                "model_key": task["model"]["key"],
                "repetition": task["repetition"],
                "app_id": task["subject"]["app_id"],
                "app_name": task["subject"]["app_name"],
                "output": relative_project_path(task["output"]),
            }
            for task in tasks
        ],
    }
    plan_path = (
        project_path(protocol["output_root"]).parent
        / f"{args.phase}_experiment_plan.json"
    )
    write_json(plan_path, payload)
    print(json.dumps({
        "plan": relative_project_path(plan_path),
        "models": len(models),
        "apps": len(subjects),
        "repetitions": repetitions,
        "app_level_runs": len(tasks),
    }, ensure_ascii=False, indent=2))


def command_preflight(args, protocol):
    models = selected_models(protocol, args.models)
    existing = load_preflight(protocol)
    results = {
        item.get("model_key"): item
        for item in existing.get("models", [])
        if item.get("model_key")
    }
    selected_results = [preflight_one(model) for model in models]
    for result in selected_results:
        results[result["model_key"]] = result
    ordered_results = [
        results[model["key"]]
        for model in protocol["models"]
        if model["key"] in results
    ]
    report = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "checked_at": now_iso(),
        "models": ordered_results,
    }
    path = project_path(protocol["preflight_report"])
    write_json(path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(
        not item["exact_model_id_available"] for item in selected_results
    ):
        raise SystemExit(2)


def infrastructure_failure_reason(output):
    output = Path(output)
    comparison_path = output / "comparison_result.json"
    if not comparison_path.exists():
        return "missing_comparison_result"
    try:
        comparison = read_json(comparison_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return "invalid_comparison_result"

    groups = comparison.get("groups", {})
    if nested(groups, "baseline", "status") == "model_error":
        return "baseline_model_provider_error"

    if nested(groups, "proposed", "status") == "failed":
        repair_run_path = output / "proposed/reports/repair_run.json"
        if not repair_run_path.exists():
            return "enhanced_runner_failure"
        try:
            repair_run = read_json(repair_run_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return "invalid_enhanced_repair_record"
        failure_code = nested(repair_run, "failure", "code")
        if failure_code == "MODEL_PROVIDER_ERROR":
            return "enhanced_model_provider_error"
        if not failure_code:
            return "enhanced_runner_failure"
    return None


def completed_task(task):
    return infrastructure_failure_reason(task["output"]) is None


def command_run(args, protocol):
    if args.phase == "formal" and protocol["status"] != "frozen":
        raise SystemExit(
            "正式实验只能使用 status=frozen 的协议。请先完成模型ID预检并冻结协议。"
        )
    subjects = selected_subjects(
        load_subjects(protocol), args.apps, args.limit_apps
    )
    models = selected_models(protocol, args.models)
    repetitions = repetition_numbers(protocol, args.repetitions)
    verified = exact_verified_models(protocol)
    unverified = [model["key"] for model in models if model["key"] not in verified]
    if unverified and not (args.phase == "pilot" and args.allow_unverified):
        raise SystemExit(
            "以下模型尚未通过精确ID预检: " + ", ".join(unverified)
        )

    tasks = build_tasks(protocol, models, subjects, repetitions, args.phase)
    records = []
    for index, task in enumerate(tasks, 1):
        output = task["output"]
        if args.resume and completed_task(task):
            print(
                f"[{index}/{len(tasks)}] 跳过已完成: "
                f"{task['model']['key']} / {task['subject']['app_name']} / "
                f"rep {task['repetition']}"
            )
            continue
        if output.exists() and not args.force:
            print(
                f"[{index}/{len(tasks)}] 目录存在但未确认完成，跳过: {output}",
                file=sys.stderr,
            )
            records.append({
                "status": "existing_incomplete_output",
                "output": relative_project_path(output),
            })
            if args.fail_fast:
                break
            continue

        command = task_command(protocol, task)
        if args.force:
            command.append("--force")
        print(
            f"[{index}/{len(tasks)}] {task['model']['key']} / "
            f"{task['subject']['app_name']} / rep {task['repetition']}"
        )
        started_at = now_iso()
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=task_environment(protocol, task["model"]),
        )
        output.mkdir(parents=True, exist_ok=True)
        (output / "batch_stdout.txt").write_text(
            result.stdout, encoding="utf-8"
        )
        (output / "batch_stderr.txt").write_text(
            result.stderr, encoding="utf-8"
        )
        infrastructure_failure = infrastructure_failure_reason(output)
        state = {
            "protocol_id": protocol["protocol_id"],
            "phase": args.phase,
            "model_key": task["model"]["key"],
            "provider": task["model"]["provider"],
            "requested_model": task["model"]["model"],
            "repetition": task["repetition"],
            "app_id": task["subject"]["app_id"],
            "app_name": task["subject"]["app_name"],
            "started_at": started_at,
            "completed_at": now_iso(),
            "return_code": result.returncode,
            "status": (
                "infrastructure_failed"
                if infrastructure_failure
                else "completed"
            ),
            "infrastructure_failure_reason": infrastructure_failure,
            "output": relative_project_path(output),
        }
        write_json(output / "batch_run.json", state)
        records.append(state)
        if infrastructure_failure:
            print(result.stderr[-2000:], file=sys.stderr)
            if args.fail_fast:
                break

    batch_log = (
        project_path(protocol["output_root"]).parent
        / f"{args.phase}_last_batch.json"
    )
    write_json(batch_log, {
        "protocol_id": protocol["protocol_id"],
        "completed_at": now_iso(),
        "records": records,
    })
    summarize(protocol)


def nested(mapping, *keys, default=None):
    value = mapping
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def repair_rate(before, after):
    return (before - after) / before if before else None


def optional_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    try:
        return read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {} if default is None else default


def call_summary_count(summary, field):
    if summary.get(field) is not None:
        return summary[field]
    model_calls = summary.get("model_calls", 0) or 0
    if field == "successful_model_calls":
        return model_calls
    if field == "failed_model_calls":
        return 0
    if field == "network_retries":
        return max((summary.get("provider_attempts", 0) or 0) - model_calls, 0)
    return 0


def review_metric(review, group, metric):
    values = [
        groups.get(group, {}).get(metric)
        for groups in review.get("files", {}).values()
    ]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def run_notes(run_dir, baseline, enhanced, repair_run, review):
    notes = []
    operation_error = run_dir / "baseline/reports/operation_error.txt"
    if operation_error.exists():
        lines = operation_error.read_text(encoding="utf-8").splitlines()
        if lines:
            notes.append("baseline_operation_error=" + lines[0])
    failure = repair_run.get("failure", {})
    if failure.get("code"):
        notes.append("enhanced_failure=" + str(failure["code"]))
    if repair_run.get("stop_reason"):
        notes.append("enhanced_stop=" + str(repair_run["stop_reason"]))
    for group_name in ("baseline", "proposed"):
        text_value = review.get(group_name, {}).get("notes")
        if text_value:
            notes.append(f"{group_name}_review={text_value}")
    return "; ".join(notes)


def result_row(protocol, run_dir):
    config = read_json(run_dir / "experiment_config.json")
    comparison = read_json(run_dir / "comparison_result.json")
    batch = read_json(run_dir / "batch_run.json") if (
        run_dir / "batch_run.json"
    ).exists() else {}
    baseline = comparison["groups"]["baseline"]
    enhanced = comparison["groups"]["proposed"]
    before_safe = nested(
        comparison, "original", "repairable_error_count", default=0
    )
    baseline_safe = nested(
        baseline, "metrics", "final", "repairable_error_count", default=0
    )
    enhanced_safe = nested(
        enhanced, "metrics", "final", "repairable_error_count", default=0
    )
    baseline_calls = baseline.get("model_call_summary", {})
    enhanced_calls = enhanced.get("model_call_summary", {})
    baseline_usage = baseline_calls.get("usage", {})
    enhanced_usage = enhanced_calls.get("usage", {})
    repair_run = optional_json(run_dir / "proposed/reports/repair_run.json")
    review = optional_json(run_dir / "manual_review.json")
    enhanced_attempts = [
        attempt
        for round_state in repair_run.get("rounds", [])
        for attempt in round_state.get("attempts", [])
    ]
    baseline_before = nested(
        comparison, "original", "error_count", default=0
    )
    baseline_after = nested(
        baseline, "metrics", "final", "error_count", default=0
    )
    enhanced_after = nested(
        enhanced, "metrics", "final", "error_count", default=0
    )
    infrastructure_failure = infrastructure_failure_reason(run_dir)
    return {
        "protocol_id": config.get("protocol_id", protocol["protocol_id"]),
        "phase": batch.get("phase", "unknown"),
        "batch_status": (
            "infrastructure_failed"
            if infrastructure_failure
            else "completed"
        ),
        "infrastructure_failure_reason": infrastructure_failure or "",
        "model_key": batch.get("model_key", "unknown"),
        "model_display_name": next((
            model["display_name"]
            for model in protocol["models"]
            if model["key"] == batch.get("model_key")
        ), ""),
        "provider": config.get("provider"),
        "requested_model": config.get("model"),
        "detector_profile": config.get("detector_profile", "conservative_v1"),
        "api_streaming": bool(config.get("api_streaming", False)),
        "baseline_resolved_models": ";".join(
            baseline_calls.get("resolved_models", [])
        ),
        "enhanced_resolved_models": ";".join(
            enhanced_calls.get("resolved_models", [])
        ),
        "repetition": batch.get("repetition"),
        "app_id": config.get("app_id"),
        "app_name": config.get("app_name"),
        "category": config.get("category"),
        "selected_interface_count": len(config.get("layouts", [])),
        "input_resource_sha256": config.get("input_resource_sha256"),
        "before_error_count": baseline_before,
        "before_warning_count": nested(
            comparison, "original", "warning_count", default=0
        ),
        "before_info_count": nested(
            comparison, "original", "info_count", default=0
        ),
        "before_total_issue_count": nested(
            comparison, "original", "total_issue_count", default=0
        ),
        "before_xml_safe_error_count": before_safe,
        "baseline_after_error_count": baseline_after,
        "enhanced_after_error_count": enhanced_after,
        "baseline_after_warning_count": nested(
            baseline, "metrics", "final", "warning_count", default=0
        ),
        "enhanced_after_warning_count": nested(
            enhanced, "metrics", "final", "warning_count", default=0
        ),
        "baseline_after_info_count": nested(
            baseline, "metrics", "final", "info_count", default=0
        ),
        "enhanced_after_info_count": nested(
            enhanced, "metrics", "final", "info_count", default=0
        ),
        "baseline_after_total_issue_count": nested(
            baseline, "metrics", "final", "total_issue_count", default=0
        ),
        "enhanced_after_total_issue_count": nested(
            enhanced, "metrics", "final", "total_issue_count", default=0
        ),
        "baseline_after_xml_safe_error_count": baseline_safe,
        "enhanced_after_xml_safe_error_count": enhanced_safe,
        "baseline_error_repair_rate": repair_rate(
            baseline_before, baseline_after
        ),
        "enhanced_error_repair_rate": repair_rate(
            baseline_before, enhanced_after
        ),
        "baseline_xml_safe_repair_rate": repair_rate(before_safe, baseline_safe),
        "enhanced_xml_safe_repair_rate": repair_rate(before_safe, enhanced_safe),
        "baseline_status": baseline.get("status"),
        "enhanced_status": enhanced.get("status"),
        "baseline_iterations": 1 if baseline.get("model_calls", 0) else 0,
        "enhanced_iterations": sum(
            bool(round_state.get("attempts"))
            for round_state in repair_run.get("rounds", [])
        ),
        "baseline_rejected_outputs": int(
            baseline.get("status") == "invalid_model_output"
        ),
        "enhanced_rejected_attempts": sum(
            attempt.get("status") == "rejected"
            for attempt in enhanced_attempts
        ),
        "baseline_model_calls": baseline.get("model_calls", 0),
        "enhanced_model_calls": enhanced.get("model_calls", 0),
        "baseline_successful_model_calls": call_summary_count(
            baseline_calls, "successful_model_calls"
        ),
        "enhanced_successful_model_calls": call_summary_count(
            enhanced_calls, "successful_model_calls"
        ),
        "baseline_failed_model_calls": call_summary_count(
            baseline_calls, "failed_model_calls"
        ),
        "enhanced_failed_model_calls": call_summary_count(
            enhanced_calls, "failed_model_calls"
        ),
        "baseline_provider_attempts": baseline_calls.get("provider_attempts"),
        "enhanced_provider_attempts": enhanced_calls.get("provider_attempts"),
        "baseline_network_retries": call_summary_count(
            baseline_calls, "network_retries"
        ),
        "enhanced_network_retries": call_summary_count(
            enhanced_calls, "network_retries"
        ),
        "baseline_http_statuses": ";".join(
            str(value) for value in baseline_calls.get("http_statuses", [])
        ),
        "enhanced_http_statuses": ";".join(
            str(value) for value in enhanced_calls.get("http_statuses", [])
        ),
        "baseline_input_tokens": baseline_usage.get("input_tokens"),
        "baseline_output_tokens": baseline_usage.get("output_tokens"),
        "baseline_total_tokens": baseline_usage.get("total_tokens"),
        "enhanced_input_tokens": enhanced_usage.get("input_tokens"),
        "enhanced_output_tokens": enhanced_usage.get("output_tokens"),
        "enhanced_total_tokens": enhanced_usage.get("total_tokens"),
        "baseline_duration_ms": baseline_calls.get("duration_ms"),
        "enhanced_duration_ms": enhanced_calls.get("duration_ms"),
        "baseline_safety_findings": nested(
            baseline, "metrics", "safety_findings", default=0
        ),
        "enhanced_safety_findings": nested(
            enhanced, "metrics", "safety_findings", default=0
        ),
        "source_review_status": review.get(
            "source_review_status", "pending"
        ),
        "professional_review_status": review.get(
            "professional_review_status", "pending"
        ),
        "baseline_semantic_correct_count": review_metric(
            review, "baseline", "semantic_correct_count"
        ),
        "baseline_semantic_incorrect_count": review_metric(
            review, "baseline", "semantic_incorrect_count"
        ),
        "baseline_semantic_pending_count": review_metric(
            review, "baseline", "semantic_pending_count"
        ),
        "enhanced_semantic_correct_count": review_metric(
            review, "proposed", "semantic_correct_count"
        ),
        "enhanced_semantic_incorrect_count": review_metric(
            review, "proposed", "semantic_incorrect_count"
        ),
        "enhanced_semantic_pending_count": review_metric(
            review, "proposed", "semantic_pending_count"
        ),
        "notes": run_notes(
            run_dir, baseline, enhanced, repair_run, review
        ),
        "run_path": relative_project_path(run_dir),
        "completed_at": comparison.get("completed_at"),
    }


def summarize(protocol):
    output_root = project_path(protocol["output_root"])
    rows = []
    for comparison_path in sorted(output_root.glob("*/*/rep_*/*/comparison_result.json")):
        try:
            rows.append(result_row(protocol, comparison_path.parent))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(
                f"忽略无法汇总的运行 {comparison_path.parent}: {exc}",
                file=sys.stderr,
            )
    summary_path = project_path(protocol["summary_csv"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    completed_rows = [
        row for row in rows if row["batch_status"] == "completed"
    ]
    infrastructure_failed_rows = [
        row for row in rows
        if row["batch_status"] == "infrastructure_failed"
    ]
    manifest = {
        "schema_version": 2,
        "protocol_id": protocol["protocol_id"],
        "protocol_status": protocol["status"],
        "updated_at": now_iso(),
        "recorded_app_level_runs": len(rows),
        "completed_app_level_runs": len(completed_rows),
        "infrastructure_failed_app_level_runs": len(
            infrastructure_failed_rows
        ),
        "expected_formal_app_level_runs": (
            protocol["target_app_count"]
            * len(protocol["models"])
            * protocol["repetitions"]
        ),
        "summary_csv": relative_project_path(summary_path),
        "runs": rows,
    }
    manifest_path = project_path(protocol["run_manifest"])
    write_json(manifest_path, manifest)
    print(json.dumps({
        "recorded_app_level_runs": len(rows),
        "completed_app_level_runs": len(completed_rows),
        "infrastructure_failed_app_level_runs": len(
            infrastructure_failed_rows
        ),
        "summary_csv": relative_project_path(summary_path),
        "run_manifest": relative_project_path(manifest_path),
    }, ensure_ascii=False, indent=2))
    return rows


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the frozen Android XML multi-model experiment."
    )
    parser.add_argument(
        "--protocol",
        default=str(DEFAULT_PROTOCOL),
        help="Multi-model protocol JSON path.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("plan", "run"):
        child = subparsers.add_parser(name)
        child.add_argument("--phase", choices=["pilot", "formal"], default="formal")
        child.add_argument("--models", help="Comma-separated model keys")
        child.add_argument("--apps", help="Comma-separated app names or IDs")
        child.add_argument("--repetitions", help="Comma-separated repetition numbers")
        child.add_argument("--limit-apps", type=int)
    run = subparsers.choices["run"]
    run.add_argument("--resume", action="store_true")
    run.add_argument("--force", action="store_true")
    run.add_argument("--fail-fast", action="store_true")
    run.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Only permits an unverified pilot; never bypasses formal freezing.",
    )

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--models", help="Comma-separated model keys")
    subparsers.add_parser("summarize")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.command == "plan":
        command_plan(args, protocol)
    elif args.command == "preflight":
        command_preflight(args, protocol)
    elif args.command == "run":
        command_run(args, protocol)
    elif args.command == "summarize":
        summarize(protocol)


if __name__ == "__main__":
    main()
