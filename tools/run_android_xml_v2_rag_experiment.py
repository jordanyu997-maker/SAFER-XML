#!/usr/bin/env python3
"""Prepare, verify, or run the frozen V2 Development RAG comparison."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "outputs/v2_dataset/v2.0.0"
DEVELOPMENT_CSV = DATASET_ROOT / "v2_development.csv"
DATASET_METADATA = DATASET_ROOT / "v2_dataset_metadata.json"
DATASET_CHECKSUMS = DATASET_ROOT / "v2_checksums.sha256"
PROTOCOL_PATH = ROOT / "experiments/android_xml_v2_rag/protocol_v2.json"
DEFAULT_OUTPUT_PARENT = ROOT / "experiments/android_xml_v2_rag"
RAG_TOP_K_VALUES = (2, 4, 8)
CONDITIONS = ("no_rag",) + tuple(
    f"rag_topk{top_k}" for top_k in RAG_TOP_K_VALUES
)
DETECTOR_PROFILE = "expanded_v3"

TASK_FIELDS = (
    "task_id",
    "app_name",
    "package_name",
    "repository_url",
    "xml_path",
    "screen_name",
    "candidate_count",
    "candidate_ids",
    "issue_types",
    "issue_subtypes",
    "target_codes",
    "rag_top_k_values",
    "effective_top_k_values",
    "input_package",
    "input_resource_sha256",
)
BOUNDARY_FIELDS = (
    "candidate_id",
    "app_name",
    "package_name",
    "repository_url",
    "xml_path",
    "issue_type",
    "issue_subtype",
    "candidate_role",
    "decision",
    "model_calls",
    "correct_static_repair_refusal",
    "notes",
)
SUMMARY_FIELDS = (
    "task_id",
    "app_name",
    "screen_name",
    "candidate_ids",
    "issue_types",
    "issue_subtypes",
    "target_codes",
    "group",
    "provider",
    "model",
    "status",
    "before_candidate_error_count",
    "after_candidate_error_count",
    "candidate_repair_rate",
    "complete_candidate_repair",
    "before_total_error_count",
    "after_total_error_count",
    "warning_count",
    "info_count",
    "model_calls",
    "provider_attempts",
    "network_retries",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_ms",
    "requested_top_k",
    "effective_top_k",
    "knowledge_document_count",
    "knowledge_document_ids",
    "changed_files",
    "changed_file_count",
    "safety_finding_count",
    "operation_parse_valid",
    "operation_count",
    "string_resource_addition_count",
    "hardcoded_accessibility_value_count",
    "interaction_attribute_removal_count",
    "structural_operation_count",
    "output_path",
    "notes",
)

sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.build_v2_frozen_dataset import (  # noqa: E402
    candidate_selector,
    element_candidates,
)
from scripts.source_prescreen.scan_android_xml import (  # noqa: E402
    CODE_CLASSIFICATION,
    git_value,
)
from tools.android_xml_rag_prompt_contract import (  # noqa: E402
    audit_prompt_pair,
    build_prompt_pair,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    all_attrs,
    apply_explicit_styles,
    load_style_resources,
)
from tools.evaluation.collect_android_xml_package import collect  # noqa: E402
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
    issue_quality,
    issue_severity,
    prepare_output,
    run_xml_checker,
    save_report,
    save_round_artifact,
    save_safety_report,
    validate_repair_safety,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    audit_model_operations,
    now_iso,
    prune_entrypoint_variants,
    recorded_path,
    sha256_file,
    target_repair_rate,
    tree_digest,
    validate_pilot_operation_scope,
    write_json,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return normalized.strip("-") or "task"


def file_sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def task_id_for(rows: list[dict]) -> str:
    first = rows[0]
    suffix = hashlib.sha256(
        (first["repository_url"] + "|" + first["xml_path"]).encode("utf-8")
    ).hexdigest()[:8]
    return f"{slug(first['app_name'])}--{slug(Path(first['xml_path']).stem)}--{suffix}"


def source_res_dir(row: dict) -> Path:
    xml_path = Path(row["repository_path"]) / row["xml_path"]
    for parent in xml_path.parents:
        if parent.name == "res":
            return parent
    raise FileNotFoundError(f"cannot locate res root for {xml_path}")


def resource_path(xml_path: str) -> str:
    normalized = str(xml_path).replace("\\", "/")
    if normalized.startswith("res/"):
        return normalized.removeprefix("res/")
    marker = "/res/"
    if marker not in normalized:
        raise ValueError(f"XML path does not contain /res/: {xml_path}")
    return normalized.split(marker, 1)[1]


def issue_resource_path(issue: dict, res_dir: Path) -> str:
    path = Path(issue.get("file", ""))
    try:
        return path.resolve().relative_to(res_dir.resolve()).as_posix()
    except (OSError, ValueError):
        normalized = str(path).replace("\\", "/")
        return normalized.rsplit("/res/", 1)[-1] if "/res/" in normalized else normalized


def candidate_code_map() -> dict[tuple[str, str], set[str]]:
    mapping: dict[tuple[str, str], set[str]] = defaultdict(set)
    for code, (issue_type, subtype, _) in CODE_CLASSIFICATION.items():
        mapping[(issue_type, subtype)].add(code)
    mapping[
        ("accessibility_attribute_conflict", "standard_interactive_focusable_false")
    ].add("ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE")
    return mapping


CANDIDATE_CODES = candidate_code_map()


def verify_dataset_files() -> tuple[dict, list[dict]]:
    metadata = load_json(DATASET_METADATA)
    protocol = load_json(PROTOCOL_PATH)
    errors = []
    if metadata.get("status") != "frozen":
        errors.append("V2 dataset is not frozen")
    expected_dataset_hash = protocol["dataset"]["dataset_sha256"]
    if metadata.get("dataset_sha256") != expected_dataset_hash:
        errors.append("V2 dataset hash differs from the registered protocol")
    checksum_rows = {}
    for line in DATASET_CHECKSUMS.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        checksum_rows[name] = digest
    for path in (DEVELOPMENT_CSV, DATASET_METADATA):
        expected = checksum_rows.get(path.name)
        if not expected or sha256_file(path) != expected:
            errors.append(f"dataset checksum mismatch: {path.name}")
    if errors:
        raise SystemExit("V2 dataset validation failed:\n- " + "\n- ".join(errors))
    rows = load_csv(DEVELOPMENT_CSV)
    if any(row.get("dataset_split") != "development" for row in rows):
        raise SystemExit("V2 Development CSV contains a non-development row")
    return metadata, rows


def validate_source_row(row: dict) -> list[str]:
    errors = []
    repository = Path(row["repository_path"])
    xml_path = repository / row["xml_path"]
    if not repository.is_dir() or not (repository / ".git").exists():
        return [f"{row['candidate_id']}: repository missing"]
    if git_value(repository, "rev-parse", "HEAD") != row["commit_hash"]:
        errors.append(f"{row['candidate_id']}: source commit changed")
    if not xml_path.is_file():
        errors.append(f"{row['candidate_id']}: source XML missing")
    elif sha256_file(xml_path) != row["source_file_sha256"]:
        errors.append(f"{row['candidate_id']}: source XML hash changed")
    return errors


def grouped_repair_rows(rows: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["candidate_role"] == "xml_safe":
            grouped[(row["repository_url"], row["xml_path"])].append(row)
    return [
        sorted(values, key=lambda row: row["candidate_id"])
        for _, values in sorted(grouped.items())
    ]


def locate_candidate_targets(
    candidate_rows: list[dict],
    package_res: Path,
) -> list[dict]:
    expected_path = resource_path(candidate_rows[0]["xml_path"])
    layout = package_res / expected_path
    root = ET.parse(layout).getroot()
    apply_explicit_styles(root, load_style_resources([package_res]))
    targets = []
    for row in candidate_rows:
        matches = element_candidates(root, row)
        if len(matches) != 1:
            raise ValueError(
                f"{row['candidate_id']}: expected one frozen node, found {len(matches)}"
            )
        element = matches[0]
        codes = sorted(CANDIDATE_CODES.get((row["issue_type"], row["issue_subtype"]), set()))
        if not codes:
            raise ValueError(
                f"{row['candidate_id']}: no detector code mapping for "
                f"{row['issue_type']}/{row['issue_subtype']}"
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


def match_frozen_issues(
    issues: list[dict],
    task: dict,
    res_dir: Path,
    require_all: bool = False,
) -> list[dict]:
    matched = []
    seen_candidates = set()
    for target in task["target_candidates"]:
        candidates = [
            issue
            for issue in issues
            if issue_severity(issue) == "error"
            and issue.get("repairability", "xml_safe") == "xml_safe"
            and issue.get("code") in set(target["expected_codes"])
            and issue_resource_path(issue, res_dir) == target["resource_path"]
            and issue.get("selector") == target["selector"]
        ]
        if len(candidates) > 1:
            raise ValueError(
                f"{target['candidate_id']}: detector produced duplicate target issues"
            )
        if candidates:
            item = dict(candidates[0])
            item["v2_candidate_id"] = target["candidate_id"]
            matched.append(item)
            seen_candidates.add(target["candidate_id"])
    if require_all:
        missing = [
            target["candidate_id"]
            for target in task["target_candidates"]
            if target["candidate_id"] not in seen_candidates
        ]
        if missing:
            raise ValueError("frozen candidate(s) not reproduced: " + ", ".join(missing))
    return matched


def implementation_hashes() -> dict:
    paths = {
        "runner": Path(__file__).resolve(),
        "protocol": PROTOCOL_PATH,
        "development_dataset": DEVELOPMENT_CSV,
        "dataset_metadata": DATASET_METADATA,
        "knowledge": ROOT / "knowledge/rag/knowledge_documents.json",
        "retriever": ROOT / "tools/retrieval/v2_hybrid.py",
        "prompt_contract": ROOT / "tools/android_xml_rag_prompt_contract.py",
        "detector": ROOT / "tools/evaluation/android_xml_a11y_check.py",
        "operation_executor": ROOT / "tools/generate_android_xml.py",
    }
    return {
        name: {
            "path": recorded_path(path),
            "sha256": sha256_file(path),
        }
        for name, path in paths.items()
    }


def boundary_gate_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "candidate_id": row["candidate_id"],
            "app_name": row["app_name"],
            "package_name": row["package_name"],
            "repository_url": row["repository_url"],
            "xml_path": row["xml_path"],
            "issue_type": row["issue_type"],
            "issue_subtype": row["issue_subtype"],
            "candidate_role": row["candidate_role"],
            "decision": "blocked_before_model",
            "model_calls": 0,
            "correct_static_repair_refusal": "true",
            "notes": "Frozen boundary candidate is excluded from XML-safe repair execution.",
        }
        for row in rows
        if row["candidate_role"] == "boundary"
    ]


def task_csv_row(task: dict) -> dict:
    return {
        **task,
        "candidate_ids": ";".join(task["candidate_ids"]),
        "issue_types": ";".join(task["issue_types"]),
        "issue_subtypes": ";".join(task["issue_subtypes"]),
        "target_codes": ";".join(task["target_codes"]),
        "rag_top_k_values": ";".join(
            str(value) for value in task["rag_top_k_values"]
        ),
        "effective_top_k_values": json.dumps(
            task["effective_top_k_values"],
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def registered_top_k_values(protocol: dict) -> tuple[int, ...]:
    values = tuple(
        int(value)
        for value in protocol["development_tuning"]["prompt_top_k_candidates"]
    )
    if not values or len(values) != len(set(values)):
        raise ValueError("Registered Top-k values must be non-empty and unique")
    if tuple(sorted(values)) != values:
        raise ValueError("Registered Top-k values must be sorted")
    return values


def experiment_conditions(top_k_values=RAG_TOP_K_VALUES) -> tuple[str, ...]:
    return ("no_rag",) + tuple(f"rag_topk{value}" for value in top_k_values)


def condition_top_k(condition: str) -> int:
    if condition == "no_rag":
        return 0
    match = re.fullmatch(r"rag_topk([1-9][0-9]*)", condition)
    if not match:
        raise ValueError(f"Unknown Development condition: {condition}")
    return int(match.group(1))


def prepare(args) -> dict:
    metadata, rows = verify_dataset_files()
    source_errors = [
        error
        for row in rows
        for error in validate_source_row(row)
    ]
    if source_errors:
        raise SystemExit("V2 source validation failed:\n- " + "\n- ".join(source_errors))
    protocol = load_json(PROTOCOL_PATH)
    top_k_values = registered_top_k_values(protocol)
    if top_k_values != RAG_TOP_K_VALUES:
        raise SystemExit(
            "Protocol Top-k values do not match the registered runner matrix: "
            f"{top_k_values} != {RAG_TOP_K_VALUES}"
        )
    conditions = experiment_conditions(top_k_values)
    if args.force and args.output.exists():
        shutil.rmtree(args.output)
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output already exists; use --force to rebuild Development inputs")
    args.output.mkdir(parents=True, exist_ok=True)
    documents = load_documents()
    task_records = []
    grouped = grouped_repair_rows(rows)
    for index, candidate_rows in enumerate(grouped, 1):
        task_id = task_id_for(candidate_rows)
        print(f"[{index}/{len(grouped)}] prepare / {task_id}")
        first = candidate_rows[0]
        package = args.output / "frozen_inputs" / task_id
        collect(
            source_res_dir(first),
            package,
            force=True,
            selected_layouts={Path(first["xml_path"]).stem},
        )
        prune_entrypoint_variants(package, {
            "screen_path": first["xml_path"],
            "screen_name": Path(first["xml_path"]).stem,
        })
        package_res = package / "res"
        targets = locate_candidate_targets(candidate_rows, package_res)
        task = {
            "task_id": task_id,
            "app_name": first["app_name"],
            "package_name": first["package_name"],
            "repository_url": first["repository_url"],
            "repository_path": first["repository_path"],
            "source_commit": first["commit_hash"],
            "source_file_sha256": first["source_file_sha256"],
            "xml_path": first["xml_path"],
            "screen_name": Path(first["xml_path"]).stem,
            "candidate_ids": [row["candidate_id"] for row in candidate_rows],
            "issue_types": sorted({row["issue_type"] for row in candidate_rows}),
            "issue_subtypes": sorted({row["issue_subtype"] for row in candidate_rows}),
            "target_codes": sorted({
                code for target in targets for code in target["expected_codes"]
            }),
            "target_candidates": targets,
            "candidate_count": len(candidate_rows),
            "rag_top_k_values": list(top_k_values),
            "input_package": recorded_path(package),
            "input_resource_sha256": tree_digest(package_res),
        }
        issues = run_xml_checker(package_res, detector_profile=DETECTOR_PROFILE)
        selected = match_frozen_issues(issues, task, package_res, require_all=True)
        prompt_root = args.output / "frozen_prompts" / task_id
        prompt_root.mkdir(parents=True, exist_ok=True)
        pairs = {}
        no_rag_prompt = None
        for top_k in top_k_values:
            pair = build_prompt_pair(
                selected,
                package_res,
                documents,
                per_issue_limit=top_k,
                prompt_limit=top_k,
            )
            audit = audit_prompt_pair(pair, selected)
            if not audit["passed"]:
                raise SystemExit(
                    f"{task_id} / Top-k {top_k}: prompt isolation failed: "
                    + ", ".join(audit["failures"])
                )
            if no_rag_prompt is None:
                no_rag_prompt = pair["no_rag"]
            elif no_rag_prompt != pair["no_rag"]:
                raise SystemExit(
                    f"{task_id}: No-RAG prompt changed across Top-k conditions"
                )
            condition = f"rag_topk{top_k}"
            pairs[condition] = pair
            (prompt_root / f"{condition}_prompt.txt").write_text(
                pair["rag"],
                encoding="utf-8",
            )
            write_json(
                prompt_root / f"{condition}_retrieval_trace.json",
                pair["trace"],
            )
        (prompt_root / "no_rag_prompt.txt").write_text(
            no_rag_prompt or "",
            encoding="utf-8",
        )
        save_report(package, issues)
        task.update({
            "effective_top_k_values": {
                condition: pair["trace"]["effective_prompt_limit"]
                for condition, pair in pairs.items()
            },
            "prompt_sha256": {
                condition: sha256_file(
                    prompt_root / f"{condition}_prompt.txt"
                )
                for condition in conditions
            },
            "retrieval_trace_sha256": {
                condition: sha256_file(
                    prompt_root / f"{condition}_retrieval_trace.json"
                )
                for condition in conditions
                if condition != "no_rag"
            },
            "retrieved_document_ids": {
                condition: [
                    item["doc_id"]
                    for item in pair["trace"]["knowledge_documents"]
                ]
                for condition, pair in pairs.items()
            },
            "prompt_isolation_passed": True,
        })
        write_json(prompt_root / "task.json", task)
        task_records.append(task)

    boundary_rows = boundary_gate_rows(rows)
    write_csv(args.output / "development_tasks.csv", [
        task_csv_row(task) for task in task_records
    ], TASK_FIELDS)
    write_csv(args.output / "boundary_gate.csv", boundary_rows, BOUNDARY_FIELDS)
    manifest = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "status": "development_inputs_frozen",
        "created_at": now_iso(),
        "model_execution": False,
        "model_calls": 0,
        "dataset_version": metadata["dataset_version"],
        "dataset_sha256": metadata["dataset_sha256"],
        "dataset_split": "development",
        "test_set_loaded": False,
        "conditions": list(conditions),
        "conditions_differ_only_in_knowledge_block": True,
        "model_calls_per_condition_task": 1,
        "rag_top_k_values": list(top_k_values),
        "effective_top_k_values": list(top_k_values),
        "shared_no_rag": True,
        "development_app_count": len({
            row["repository_url"] for row in rows
        }),
        "repair_app_count": len({
            task["repository_url"] for task in task_records
        }),
        "boundary_app_count": len({
            row["repository_url"]
            for row in rows
            if row["candidate_role"] == "boundary"
        }),
        "task_count": len(task_records),
        "candidate_count": sum(task["candidate_count"] for task in task_records),
        "boundary_candidate_count": len(boundary_rows),
        "condition_run_count": len(task_records) * len(conditions),
        "implementation_hashes": implementation_hashes(),
        "boundary_gate_sha256": sha256_file(args.output / "boundary_gate.csv"),
        "tasks": task_records,
    }
    write_json(args.output / "frozen_manifest.json", manifest)
    result = {
        "status": manifest["status"],
        "development_apps": manifest["development_app_count"],
        "repair_apps": manifest["repair_app_count"],
        "boundary_apps": manifest["boundary_app_count"],
        "repair_tasks": len(task_records),
        "xml_safe_candidates": manifest["candidate_count"],
        "boundary_candidates": len(boundary_rows),
        "prepared_condition_runs": manifest["condition_run_count"],
        "model_calls": 0,
        "rag_top_k_values": manifest["rag_top_k_values"],
        "shared_no_rag": manifest["shared_no_rag"],
        "output": str(args.output.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def validate_freeze(output: Path) -> list[str]:
    manifest_path = output / "frozen_manifest.json"
    if not manifest_path.exists():
        return ["frozen_manifest.json is missing"]
    manifest = load_json(manifest_path)
    errors = []
    metadata, _ = verify_dataset_files()
    if manifest.get("dataset_sha256") != metadata.get("dataset_sha256"):
        errors.append("dataset hash changed")
    current = implementation_hashes()
    for name, expected in manifest.get("implementation_hashes", {}).items():
        if current.get(name, {}).get("sha256") != expected.get("sha256"):
            errors.append(f"implementation changed: {name}")
    for task in manifest.get("tasks", []):
        package = ROOT / task["input_package"]
        if not package.is_dir():
            errors.append(f"input package missing: {task['task_id']}")
        elif tree_digest(package / "res") != task["input_resource_sha256"]:
            errors.append(f"input package changed: {task['task_id']}")
        prompt_root = output / "frozen_prompts" / task["task_id"]
        for condition in manifest.get("conditions", []):
            path = prompt_root / f"{condition}_prompt.txt"
            if (
                not path.exists()
                or sha256_file(path) != task["prompt_sha256"][condition]
            ):
                errors.append(
                    f"frozen prompt changed: {task['task_id']} / {condition}"
                )
            if condition != "no_rag":
                trace_path = (
                    prompt_root / f"{condition}_retrieval_trace.json"
                )
                if (
                    not trace_path.exists()
                    or sha256_file(trace_path)
                    != task["retrieval_trace_sha256"][condition]
                ):
                    errors.append(
                        "frozen retrieval trace changed: "
                        f"{task['task_id']} / {condition}"
                    )
    boundary = output / "boundary_gate.csv"
    if not boundary.exists() or sha256_file(boundary) != manifest.get("boundary_gate_sha256"):
        errors.append("boundary gate changed")
    return errors


def verify(args) -> dict:
    errors = validate_freeze(args.output)
    result = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "output": str(args.output.resolve()),
        "model_calls": 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)
    return result


def target_descriptors(task: dict) -> tuple[list[str], list[str], list[str]]:
    return (
        [item["candidate_id"] for item in task["target_candidates"]],
        sorted({item["issue_type"] for item in task["target_candidates"]}),
        sorted({item["issue_subtype"] for item in task["target_candidates"]}),
    )


def run_one(task: dict, condition: str, args, documents: list[dict]) -> dict:
    input_package = ROOT / task["input_package"]
    output = args.output / "runs" / task["task_id"] / condition
    state_path = output / "reports/v2_rag_run.json"
    if args.resume and state_path.exists():
        state = load_json(state_path)
        if state.get("status") not in {"running", "infrastructure_failed"}:
            return state
    prepare_output(input_package, output, force=True)
    input_res = input_package / "res"
    output_res = output / "res"
    before_issues = run_xml_checker(output_res, detector_profile=DETECTOR_PROFILE)
    selected = match_frozen_issues(before_issues, task, output_res, require_all=True)
    requested_top_k = condition_top_k(condition)
    retrieval_top_k = requested_top_k or min(task["rag_top_k_values"])
    pair = build_prompt_pair(
        selected,
        output_res,
        documents,
        per_issue_limit=retrieval_top_k,
        prompt_limit=retrieval_top_k,
    )
    prompt = pair["no_rag"] if condition == "no_rag" else pair["rag"]
    actual_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if actual_prompt_hash != task["prompt_sha256"][condition]:
        raise SystemExit(
            f"{task['task_id']} / {condition}: prompt differs from freeze"
        )
    save_round_artifact(output, "repair_prompt.txt", prompt)
    trace = pair["trace"] if condition != "no_rag" else {
        **pair["trace"],
        "knowledge_documents": [],
        "knowledge_document_count": 0,
        "knowledge_injected_characters": 0,
    }
    write_json(output / "reports/retrieval_trace.json", trace)
    save_report(output, before_issues, "android_xml_a11y_report_before.json")
    candidate_ids, issue_types, issue_subtypes = target_descriptors(task)
    before_target = len(selected)
    state = {
        "schema_version": 1,
        "protocol_id": load_json(PROTOCOL_PATH)["protocol_id"],
        "task_id": task["task_id"],
        "app_name": task["app_name"],
        "screen_name": task["screen_name"],
        "candidate_ids": candidate_ids,
        "issue_types": issue_types,
        "issue_subtypes": issue_subtypes,
        "target_codes": task["target_codes"],
        "group": condition,
        "provider": args.provider,
        "model": args.model,
        "started_at": now_iso(),
        "status": "running",
        "model_calls": 1,
        "before_candidate_error_count": before_target,
        "before_total_error_count": error_count(before_issues),
        "requested_top_k": requested_top_k,
        "effective_top_k": (
            pair["trace"]["effective_prompt_limit"]
            if condition != "no_rag"
            else 0
        ),
        "knowledge_document_count": trace["knowledge_document_count"],
        "knowledge_document_ids": [
            item["doc_id"] for item in trace["knowledge_documents"]
        ],
        "changed_files": [],
        "safety_finding_count": 0,
    }
    after_issues = before_issues
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
        state["model_call"] = model_error_metadata(exc, args.provider, args.model)

    after_target = len(match_frozen_issues(after_issues, task, output_res))
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
        "after_candidate_error_count": after_target,
        "candidate_repair_rate": target_repair_rate(before_target, after_target),
        "complete_candidate_repair": after_target == 0,
        "after_total_error_count": error_count(after_issues),
        "warning_count": quality[1],
        "info_count": quality[2],
        "changed_file_count": len(state["changed_files"]),
        "safety_finding_count": len(safety),
        "output_path": recorded_path(output),
    })
    write_json(state_path, state)
    return state


def state_row(state: dict) -> dict:
    call = state.get("model_call", {})
    usage = call.get("usage", {})
    values = {
        **state,
        "candidate_ids": ";".join(state.get("candidate_ids", [])),
        "issue_types": ";".join(state.get("issue_types", [])),
        "issue_subtypes": ";".join(state.get("issue_subtypes", [])),
        "target_codes": ";".join(state.get("target_codes", [])),
        "knowledge_document_ids": ";".join(
            state.get("knowledge_document_ids", [])
        ),
        "changed_files": ";".join(state.get("changed_files", [])),
        "provider_attempts": call.get("provider_attempts"),
        "network_retries": call.get("network_retries"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "duration_ms": call.get("duration_ms"),
        "notes": state.get("notes", ""),
    }
    return {field: values.get(field, "") for field in SUMMARY_FIELDS}


def group_order(
    task_id: str,
    conditions=CONDITIONS,
) -> tuple[str, ...]:
    """Deterministically rotate and reverse conditions across XML tasks."""
    conditions = tuple(conditions)
    if not conditions:
        return ()
    digest = int(hashlib.sha256(task_id.encode()).hexdigest(), 16)
    offset = digest % len(conditions)
    ordered = conditions[offset:] + conditions[:offset]
    if (digest // len(conditions)) % 2:
        ordered = tuple(reversed(ordered))
    return ordered


def run(args) -> dict:
    errors = validate_freeze(args.output)
    if errors:
        raise SystemExit("Frozen Development validation failed:\n- " + "\n- ".join(errors))
    validate_model_configuration(args.provider, args.api_key)
    manifest = load_json(args.output / "frozen_manifest.json")
    tasks = manifest["tasks"]
    conditions = tuple(manifest["conditions"])
    if args.tasks:
        requested = set(args.tasks)
        tasks = [task for task in tasks if task["task_id"] in requested]
        missing = requested - {task["task_id"] for task in tasks}
        if missing:
            raise SystemExit("Unknown Development task(s): " + ", ".join(sorted(missing)))
    documents = load_documents()
    states = []
    total = len(tasks) * len(conditions)
    index = 0
    for task in tasks:
        for condition in group_order(task["task_id"], conditions):
            index += 1
            print(f"[{index}/{total}] {task['task_id']} / {condition}")
            states.append(run_one(task, condition, args, documents))
    summary = args.output / "development_results.csv"
    write_csv(summary, [state_row(state) for state in states], SUMMARY_FIELDS)
    run_manifest = {
        "schema_version": 1,
        "protocol_id": manifest["protocol_id"],
        "created_at": now_iso(),
        "dataset_version": manifest["dataset_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_split": "development",
        "test_set_loaded": False,
        "provider": args.provider,
        "model": args.model,
        "rag_top_k_values": manifest["rag_top_k_values"],
        "shared_no_rag": manifest["shared_no_rag"],
        "task_count": len(tasks),
        "condition_run_count": len(states),
        "completed_condition_runs": sum(
            state["status"] in {"completed", "partial", "no_improvement"}
            for state in states
        ),
        "infrastructure_failed_condition_runs": sum(
            state["status"] == "infrastructure_failed" for state in states
        ),
        "summary": recorded_path(summary),
    }
    write_json(args.output / "run_manifest.json", run_manifest)
    result = {
        "group_runs": len(states),
        "infrastructure_failed": (
            run_manifest["infrastructure_failed_condition_runs"]
        ),
        "summary": str(summary.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--output", type=Path)
        subparser.add_argument("--force", action="store_true")
        subparser.add_argument("--resume", action="store_true")
        subparser.add_argument(
            "--tasks",
            type=lambda value: [
                item.strip() for item in value.split(",") if item.strip()
            ],
        )
        subparser.add_argument(
            "--provider",
            choices=MODEL_PROVIDER_CHOICES,
            default="deepseek",
        )
        subparser.add_argument("--model", default="deepseek-v4-pro")
        subparser.add_argument("--api-key", default=None)
    args = parser.parse_args()
    args.output = (
        args.output.resolve()
        if args.output
        else (DEFAULT_OUTPUT_PARENT / "development_matrix").resolve()
    )
    if args.command == "prepare":
        prepare(args)
    elif args.command == "verify":
        verify(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
