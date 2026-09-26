#!/usr/bin/env python3
"""Prepare and run an equal-budget Android XML RAG versus No-RAG pilot."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENS = (
    ROOT
    / "experiments/android_xml_rag_contribution/confirmation_dataset_expanded_v3_1/pilot_screens.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_rag_contribution/equal_budget_v4_development_10"
)
PROTOCOL_ID = "android_xml_rag_equal_budget_v4_development"
DETECTOR_PROFILE = "expanded_v3"
GROUPS = ("no_rag", "rag")
RAG_SENSITIVE_CODES = {
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING",
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY",
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING",
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
}
STATEFUL_RAG_CODES = {"ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL"}
SUMMARY_FIELDS = [
    "task_id",
    "app_name",
    "category",
    "screen_name",
    "task_stratum",
    "target_codes",
    "rag_limit",
    "group",
    "provider",
    "model",
    "status",
    "before_target_error_count",
    "after_target_error_count",
    "target_repair_rate",
    "before_error_count",
    "after_error_count",
    "warning_count",
    "info_count",
    "model_calls",
    "provider_attempts",
    "network_retries",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_ms",
    "knowledge_document_count",
    "knowledge_document_ids",
    "changed_files",
    "safety_finding_count",
    "operation_parse_valid",
    "operation_count",
    "string_resource_addition_count",
    "hardcoded_accessibility_value_count",
    "interaction_attribute_removal_count",
    "structural_operation_count",
    "output_path",
    "notes",
]

sys.path.insert(0, str(ROOT))

from tools.android_xml_rag_prompt_contract import (  # noqa: E402
    audit_prompt_pair,
    build_prompt_pair,
    format_neutral_issues,
)
from tools.evaluation.collect_android_xml_package import collect  # noqa: E402
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    is_weak_input_name,
    load_string_resources,
    resolve_string,
)
from tools.generate import (  # noqa: E402
    MODEL_PROVIDER_CHOICES,
    ModelError,
    model_error_metadata,
    run_model_with_metadata,
    validate_model_configuration,
)
from tools.generate_android_xml import (  # noqa: E402
    error_count,
    evaluate_and_commit_candidate,
    extract_json_object,
    issue_quality,
    issue_severity,
    normalize_resource_path,
    prepare_output,
    run_xml_checker,
    save_report,
    save_round_artifact,
    save_safety_report,
    validate_repair_safety,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def slug(value):
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return normalized.strip("-") or "task"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(item for item in Path(root).rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def recorded_path(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_counts(row):
    return json.loads(row.get("actionable_code_counts") or "{}")


def selected_rows(
    rows,
    task_ids=None,
    include_common_controls=False,
    max_apps=None,
):
    selected = []
    requested = set(task_ids or [])
    candidates = list(rows)
    if include_common_controls and not requested:
        by_app = {}
        for index, row in enumerate(candidates):
            by_app.setdefault(row["app_name"], []).append((index, row))
        app_order = list(dict.fromkeys(row["app_name"] for row in candidates))
        if max_apps is not None:
            app_order = app_order[:max_apps]
        covered_codes = set()
        candidates = []
        for app in app_order:
            ranked = []
            for index, row in by_app.get(app, []):
                counts = parse_counts(row)
                available_codes = set(counts)
                sensitive_codes = available_codes & RAG_SENSITIVE_CODES
                non_stateful_sensitive = sensitive_codes - STATEFUL_RAG_CODES
                issue_count = int(
                    row.get("actionable_issue_count") or sum(counts.values())
                )
                excessive_count = max(issue_count - 12, 0)
                new_codes = available_codes - covered_codes
                score = (
                    -int(excessive_count > 0),
                    len(non_stateful_sensitive - covered_codes),
                    len(new_codes),
                    int(bool(sensitive_codes)),
                    -excessive_count,
                    len(available_codes),
                    min(issue_count, 12),
                    -index,
                )
                ranked.append((score, row))
            if not ranked:
                continue
            chosen = max(ranked, key=lambda item: item[0])[1]
            candidates.append(chosen)
            covered_codes.update(parse_counts(chosen))

    for row in candidates:
        available_codes = set(parse_counts(row))
        codes = sorted(
            available_codes
            if include_common_controls
            else available_codes & RAG_SENSITIVE_CODES
        )
        if not codes:
            continue
        task_id = f"{slug(row['app_name'])}--{slug(row['screen_name'])}"
        if requested and task_id not in requested:
            continue
        counts = parse_counts(row)
        selected.append({
            **row,
            "task_id": task_id,
            "task_stratum": (
                "rag_sensitive"
                if available_codes & RAG_SENSITIVE_CODES
                else "common_control"
            ),
            "target_codes": codes,
            "expected_target_count": sum(counts[code] for code in codes),
        })
    if requested:
        missing = requested - {row["task_id"] for row in selected}
        if missing:
            raise SystemExit("Unknown RAG pilot task(s): " + ", ".join(sorted(missing)))
    return selected


def target_issues(issues, task):
    codes = set(task["target_codes"])
    return [
        issue
        for issue in issues
        if issue_severity(issue) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
        and issue.get("code") in codes
    ]


def selected_resource_path(screen_path):
    normalized = str(screen_path).replace("\\", "/")
    if normalized.startswith("res/"):
        return normalized.removeprefix("res/")
    marker = "/res/"
    if marker not in normalized:
        raise ValueError(f"Screen path does not contain /res/: {screen_path}")
    return normalized.split(marker, 1)[1]


def screen_res_dir(task):
    screen = Path(task["source_path"]) / task["screen_path"]
    for parent in screen.parents:
        if parent.name == "res" and parent.is_dir():
            return parent
    raise FileNotFoundError(
        f"Cannot locate res directory for selected screen: {screen}"
    )


def prune_entrypoint_variants(package, task):
    selected = selected_resource_path(task["screen_path"])
    for path in (Path(package) / "res").glob(f"layout*/*{Path(selected).suffix}"):
        if path.stem != task["screen_name"]:
            continue
        relative = path.relative_to(Path(package) / "res").as_posix()
        if relative != selected:
            path.unlink()


def freeze_hashes():
    paths = {
        "runner": Path(__file__).resolve(),
        "knowledge": ROOT / "knowledge/rag/knowledge_documents.json",
        "retriever": ROOT / "tools/retrieval/v2_hybrid.py",
        "prompt_contract": ROOT / "tools/android_xml_rag_prompt_contract.py",
        "detector": ROOT / "tools/evaluation/android_xml_a11y_check.py",
        "operation_executor": ROOT / "tools/generate_android_xml.py",
    }
    return {
        name: {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)}
        for name, path in paths.items()
    }


def prepare(args):
    rows = selected_rows(
        load_csv(args.screens),
        args.tasks,
        include_common_controls=args.include_common_controls,
        max_apps=args.max_apps,
    )
    documents = load_documents()
    input_root = args.output / "frozen_inputs"
    prompt_root = args.output / "frozen_prompts"
    if args.force and args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)

    tasks = []
    for index, task in enumerate(rows, 1):
        print(f"[{index}/{len(rows)}] prepare / {task['task_id']}")
        package = input_root / task["task_id"]
        collect(
            screen_res_dir(task),
            package,
            force=args.force,
            selected_layouts={task["screen_name"]},
        )
        prune_entrypoint_variants(package, task)
        issues = run_xml_checker(package / "res", detector_profile=DETECTOR_PROFILE)
        selected = target_issues(issues, task)
        if not selected:
            raise SystemExit(
                f"{task['task_id']}: frozen input has no target errors "
                f"for {', '.join(task['target_codes'])}"
            )
        expected_target_count = int(task.get("expected_target_count") or 0)
        if expected_target_count and len(selected) != expected_target_count:
            raise SystemExit(
                f"{task['task_id']}: target count changed during freezing; "
                f"expected={expected_target_count}, actual={len(selected)}"
            )
        pair = build_prompt_pair(
            selected,
            package / "res",
            documents,
            per_issue_limit=args.rag_limit,
            prompt_limit=args.rag_limit,
        )
        audit = audit_prompt_pair(pair, selected)
        if not audit["passed"]:
            raise SystemExit(
                f"{task['task_id']}: prompt isolation failed: "
                + ", ".join(audit["failures"])
            )
        task_prompt_root = prompt_root / task["task_id"]
        task_prompt_root.mkdir(parents=True, exist_ok=True)
        (task_prompt_root / "no_rag_prompt.txt").write_text(
            pair["no_rag"], encoding="utf-8"
        )
        (task_prompt_root / "rag_prompt.txt").write_text(
            pair["rag"], encoding="utf-8"
        )
        write_json(task_prompt_root / "retrieval_trace.json", pair["trace"])
        save_report(package, issues)
        record = {
            "task_id": task["task_id"],
            "app_id": task["app_id"],
            "app_name": task["app_name"],
            "category": task["category"],
            "screen_name": task["screen_name"],
            "task_stratum": task["task_stratum"],
            "screen_path": task["screen_path"],
            "source_path": task["source_path"],
            "target_codes": task["target_codes"],
            "target_error_count": len(selected),
            "rag_limit": args.rag_limit,
            "input_package": recorded_path(package),
            "input_resource_sha256": tree_digest(package / "res"),
            "prompt_isolation_passed": True,
            "prompt_sha256": {
                "no_rag": sha256_file(task_prompt_root / "no_rag_prompt.txt"),
                "rag": sha256_file(task_prompt_root / "rag_prompt.txt"),
            },
            "retrieved_document_ids": [
                item["doc_id"] for item in pair["trace"]["knowledge_documents"]
            ],
        }
        write_json(task_prompt_root / "task.json", record)
        tasks.append(record)

    manifest = {
        "schema_version": 1,
        "protocol_id": args.protocol_id,
        "created_at": now_iso(),
        "status": "prepared",
        "model_execution": False,
        "model_calls": 0,
        "detector_profile": DETECTOR_PROFILE,
        "groups": list(GROUPS),
        "model_calls_per_group_task": 1,
        "rag_limit": args.rag_limit,
        "include_common_controls": args.include_common_controls,
        "max_apps": args.max_apps,
        "conditions_differ_only_in_knowledge_block": True,
        "previous_output_shared_between_groups": False,
        "pre_registered_metrics": {
            "primary": [
                "target_repair_rate",
                "complete_target_repair",
            ],
            "quality_and_safety": [
                "hardcoded_accessibility_value_count",
                "interaction_attribute_removal_count",
                "structural_operation_count",
                "safety_finding_count",
            ],
            "cost": ["total_tokens", "duration_ms"],
        },
        "freeze_hashes": freeze_hashes(),
        "task_count": len(tasks),
        "tasks": tasks,
    }
    write_json(args.output / "frozen_manifest.json", manifest)
    print(json.dumps({
        "status": "prepared",
        "tasks": len(tasks),
        "groups": len(tasks) * len(GROUPS),
        "model_calls": 0,
        "manifest": str((args.output / "frozen_manifest.json").resolve()),
    }, ensure_ascii=False, indent=2))


def validate_freeze(manifest):
    errors = []
    current_hashes = freeze_hashes()
    for name, expected in manifest.get("freeze_hashes", {}).items():
        if current_hashes.get(name, {}).get("sha256") != expected.get("sha256"):
            errors.append(f"implementation changed: {name}")
    for task in manifest.get("tasks", []):
        package = ROOT / task["input_package"]
        if not package.is_dir():
            errors.append(f"input missing: {task['task_id']}")
        elif tree_digest(package / "res") != task["input_resource_sha256"]:
            errors.append(f"input changed: {task['task_id']}")
    return errors


def target_repair_rate(before, after):
    return (before - after) / before if before else None


def audit_model_operations(model_output):
    """Measure pre-registered output-quality proxies without changing execution."""
    payload = extract_json_object(model_output)
    operations = payload.get("operations") if isinstance(payload, dict) else None
    if not isinstance(operations, list):
        raise ValueError("模型输出必须包含 operations 数组。")

    accessibility_attributes = {
        "android:contentDescription",
        "android:hint",
        "android:text",
    }
    interaction_attributes = {
        "android:clickable",
        "android:focusable",
        "android:longClickable",
        "android:enabled",
        "android:onClick",
    }
    attribute_operations = {
        "set_attribute",
        "remove_attribute",
        "remove_attribute_value",
        "add_string_resource",
    }
    result = {
        "operation_parse_valid": True,
        "operation_count": len(operations),
        "string_resource_addition_count": 0,
        "hardcoded_accessibility_value_count": 0,
        "interaction_attribute_removal_count": 0,
        "structural_operation_count": 0,
    }
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("operations 中存在非对象条目。")
        op = operation.get("op")
        attribute = operation.get("attribute")
        value = str(operation.get("value", ""))
        if op == "add_string_resource":
            result["string_resource_addition_count"] += 1
        if (
            op == "set_attribute"
            and attribute in accessibility_attributes
            and value
            and not value.startswith("@")
        ):
            result["hardcoded_accessibility_value_count"] += 1
        if op == "remove_attribute" and attribute in interaction_attributes:
            result["interaction_attribute_removal_count"] += 1
        if op not in attribute_operations:
            result["structural_operation_count"] += 1
    return result


def validate_pilot_operation_scope(model_output, issues, res_dir):
    evidence = json.loads(format_neutral_issues(issues, res_dir))
    primary = set()
    related = {}
    for record in evidence:
        path = "res/" + record["file"].lstrip("/")
        primary.add((path, record["selector"]))
        for element in record.get("related_elements", []):
            related[(path, element["selector"])] = element
    payload = extract_json_object(model_output)
    operations = payload.get("operations") if isinstance(payload, dict) else None
    if not isinstance(operations, list):
        raise ValueError("模型输出必须包含 operations 数组。")
    added_strings = {
        operation.get("name"): operation.get("value")
        for operation in operations
        if isinstance(operation, dict)
        and operation.get("op") == "add_string_resource"
        and isinstance(operation.get("name"), str)
        and isinstance(operation.get("value"), str)
    }
    string_resources = {
        **load_string_resources([res_dir]),
        **added_strings,
    }
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"operation[{index}] 必须是对象。")
        if operation.get("op") == "add_string_resource":
            continue
        key = (
            normalize_resource_path(operation.get("path")),
            operation.get("selector"),
        )
        if key in primary:
            continue
        if key not in related:
            raise ValueError(
                f"operation[{index}] selector 不在冻结证据允许范围内: {key[1]}"
            )
        evidence = related[key]
        allowed_attribute = evidence["allowed_attribute"]
        if operation.get("op") != "set_attribute" or (
            operation.get("attribute") != allowed_attribute
        ):
            raise ValueError(
                f"operation[{index}] 辅助标签只允许在相关元素设置 {allowed_attribute}。"
            )
        required_value = evidence.get("required_value")
        if required_value is not None and operation.get("value") != required_value:
            raise ValueError(
                f"operation[{index}] 辅助标签只允许设置 "
                f"{allowed_attribute}=\"{required_value}\"。"
            )
        if evidence.get("allowed_value_kind") == (
            "existing_or_added_nonweak_string_resource"
        ):
            value = operation.get("value")
            match = re.fullmatch(r"@string/([A-Za-z0-9_.]+)", str(value or ""))
            name = match.group(1) if match else ""
            resolved = resolve_string(value, string_resources) if name else ""
            if (
                not name
                or name not in string_resources
                or not resolved
                or is_weak_input_name(resolved)
            ):
                raise ValueError(
                    f"operation[{index}] {allowed_attribute} 必须引用已存在或本次新增的"
                    "非空、非泛化字符串资源。"
                )


def run_one(task, group, args, documents):
    input_package = ROOT / task["input_package"]
    output = args.output / "runs" / task["task_id"] / group
    state_path = output / "reports/rag_pilot_run.json"
    if args.resume and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") not in {"running", "infrastructure_failed"}:
            return state
    prepare_output(input_package, output, force=True)
    input_res = input_package / "res"
    output_res = output / "res"
    before_issues = run_xml_checker(output_res, detector_profile=DETECTOR_PROFILE)
    selected = target_issues(before_issues, task)
    rag_limit = int(task.get("rag_limit") or 8)
    pair = build_prompt_pair(
        selected,
        output_res,
        documents,
        per_issue_limit=rag_limit,
        prompt_limit=rag_limit,
    )
    prompt = pair[group]
    expected_prompt_hash = task.get("prompt_sha256", {}).get(group)
    actual_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if expected_prompt_hash and actual_prompt_hash != expected_prompt_hash:
        raise SystemExit(
            f"{task['task_id']} / {group}: generated prompt differs from frozen prompt"
        )
    save_round_artifact(output, "repair_prompt.txt", prompt)
    trace = pair["trace"] if group == "rag" else {
        **pair["trace"],
        "knowledge_documents": [],
        "knowledge_document_count": 0,
        "knowledge_injected_characters": 0,
    }
    write_json(output / "reports/retrieval_trace.json", trace)
    save_report(output, before_issues, "android_xml_a11y_report_before.json")
    before_target = len(selected)
    state = {
        "schema_version": 1,
        "protocol_id": getattr(args, "protocol_id", PROTOCOL_ID),
        "task_id": task["task_id"],
        "app_name": task["app_name"],
        "category": task["category"],
        "screen_name": task["screen_name"],
        "task_stratum": task.get("task_stratum", "rag_sensitive"),
        "target_codes": task["target_codes"],
        "rag_limit": rag_limit,
        "group": group,
        "provider": args.provider,
        "model": args.model,
        "started_at": now_iso(),
        "status": "running",
        "model_calls": 1,
        "before_target_error_count": before_target,
        "before_error_count": error_count(before_issues),
        "knowledge_document_count": trace["knowledge_document_count"],
        "knowledge_document_ids": [
            item["doc_id"] for item in trace["knowledge_documents"]
        ],
        "changed_files": [],
        "safety_finding_count": 0,
    }
    try:
        result = run_model_with_metadata(
            args.provider,
            args.model,
            prompt,
            args.api_key,
        )
        state["model_call"] = result["metadata"]
        response = result["content"]
        save_round_artifact(output, "model_response.txt", response)
        try:
            operation_quality = audit_model_operations(response)
        except (ValueError, TypeError) as exc:
            operation_quality = {
                "operation_parse_valid": False,
                "operation_count": 0,
                "string_resource_addition_count": 0,
                "hardcoded_accessibility_value_count": 0,
                "interaction_attribute_removal_count": 0,
                "structural_operation_count": 0,
                "audit_error": str(exc),
            }
        state.update(operation_quality)
        write_json(
            output / "reports/model_operation_quality_report.json",
            operation_quality,
        )
        try:
            validate_pilot_operation_scope(response, selected, output_res)
            changed, after_issues = evaluate_and_commit_candidate(
                output,
                input_res,
                before_issues,
                response,
                detector_profile=DETECTOR_PROFILE,
            )
            state["changed_files"] = [
                path.relative_to(output).as_posix() for path in changed
            ]
        except (ValueError, ET.ParseError) as exc:
            state["notes"] = str(exc)
            after_issues = before_issues
    except ModelError as exc:
        state["status"] = "infrastructure_failed"
        state["notes"] = str(exc)
        state["model_call"] = model_error_metadata(
            exc, args.provider, args.model
        )
        after_issues = before_issues

    after_target = len(target_issues(after_issues, task))
    safety = validate_repair_safety(input_res, output_res)
    save_report(output, after_issues, "android_xml_a11y_report_after.json")
    save_safety_report(output, safety)
    if state["status"] != "infrastructure_failed":
        if after_target == 0:
            state["status"] = "completed"
        elif after_target < before_target:
            state["status"] = "partial"
        else:
            state["status"] = "no_improvement"
    quality = issue_quality(after_issues)
    state.update({
        "completed_at": now_iso(),
        "after_target_error_count": after_target,
        "target_repair_rate": target_repair_rate(before_target, after_target),
        "after_error_count": error_count(after_issues),
        "warning_count": quality[1],
        "info_count": quality[2],
        "safety_finding_count": len(safety),
        "output_path": recorded_path(output),
    })
    write_json(state_path, state)
    return state


def state_row(state):
    call = state.get("model_call", {})
    usage = call.get("usage", {})
    return {
        field: value
        for field, value in {
            **state,
            "provider_attempts": call.get("provider_attempts"),
            "network_retries": call.get("network_retries"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "duration_ms": call.get("duration_ms"),
            "knowledge_document_ids": ";".join(
                state.get("knowledge_document_ids", [])
            ),
            "target_codes": ";".join(state.get("target_codes", [])),
            "changed_files": ";".join(state.get("changed_files", [])),
            "notes": state.get("notes", ""),
        }.items()
        if field in SUMMARY_FIELDS
    }


def run(args):
    manifest_path = args.output / "frozen_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Run prepare first; frozen_manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    args.protocol_id = manifest["protocol_id"]
    errors = validate_freeze(manifest)
    if errors:
        raise SystemExit("Frozen pilot validation failed:\n- " + "\n- ".join(errors))
    validate_model_configuration(args.provider, args.api_key)
    tasks = manifest["tasks"]
    if args.tasks:
        requested = set(args.tasks)
        tasks = [task for task in tasks if task["task_id"] in requested]
        missing = requested - {task["task_id"] for task in tasks}
        if missing:
            raise SystemExit("Unknown RAG pilot task(s): " + ", ".join(sorted(missing)))
    documents = load_documents()
    states = []
    total = len(tasks) * len(GROUPS)
    index = 0
    for task in tasks:
        for group in GROUPS:
            index += 1
            print(f"[{index}/{total}] {task['task_id']} / {group}")
            states.append(run_one(task, group, args, documents))

    summary = args.output / "pilot_results.csv"
    with summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(state_row(state) for state in states)
    write_json(args.output / "run_manifest.json", {
        "schema_version": 1,
        "protocol_id": manifest["protocol_id"],
        "created_at": now_iso(),
        "provider": args.provider,
        "model": args.model,
        "task_count": len(tasks),
        "group_run_count": len(states),
        "completed_group_runs": sum(
            state["status"] in {"completed", "partial", "no_improvement"}
            for state in states
        ),
        "infrastructure_failed_group_runs": sum(
            state["status"] == "infrastructure_failed" for state in states
        ),
        "summary": recorded_path(summary),
    })
    print(json.dumps({
        "group_runs": len(states),
        "infrastructure_failed": sum(
            state["status"] == "infrastructure_failed" for state in states
        ),
        "summary": str(summary.resolve()),
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--screens", type=Path, default=DEFAULT_SCREENS)
        subparser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        subparser.add_argument("--protocol-id", default=PROTOCOL_ID)
        subparser.add_argument(
            "--tasks",
            type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        )
        subparser.add_argument("--force", action="store_true")
        subparser.add_argument("--resume", action="store_true")
        subparser.add_argument("--rag-limit", type=int, default=8)
        subparser.add_argument("--include-common-controls", action="store_true")
        subparser.add_argument("--max-apps", type=int)
        subparser.add_argument(
            "--provider", choices=MODEL_PROVIDER_CHOICES, default="deepseek"
        )
        subparser.add_argument("--model", default="deepseek-v4-pro")
        subparser.add_argument("--api-key", default=None)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.rag_limit < 1:
        raise SystemExit("--rag-limit must be at least 1")
    if args.max_apps is not None and args.max_apps < 1:
        raise SystemExit("--max-apps must be at least 1")
    if args.command == "prepare":
        prepare(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
