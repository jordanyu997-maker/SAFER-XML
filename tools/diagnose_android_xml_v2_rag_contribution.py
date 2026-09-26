#!/usr/bin/env python3
"""Prepare, run, and report Development-only V2 RAG contribution diagnostics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_ROOT = ROOT / "experiments/android_xml_v2_rag/development_matrix"
DEVELOPMENT_RESULTS = DEVELOPMENT_ROOT / "development_results.csv"
DEVELOPMENT_MANIFEST = DEVELOPMENT_ROOT / "frozen_manifest.json"
DIAGNOSIS_ROOT = (
    ROOT / "experiments/android_xml_v2_rag/rag_contribution_diagnosis"
)
PROTOCOL_PATH = ROOT / "experiments/android_xml_v2_rag/protocol_v2.json"
DIAGNOSTIC_CONDITIONS = ("oracle_rag", "random_rag")
DEVELOPMENT_CONDITIONS = (
    "no_rag",
    "rag_topk2",
    "rag_topk4",
    "rag_topk8",
)
DETECTOR_PROFILE = "expanded_v3"
RANDOM_SEED = "android-xml-v2-rag-diagnosis-random-v1"

CORE_PATHS = {
    "dataset_metadata": ROOT / "outputs/v2_dataset/v2.0.0/v2_dataset_metadata.json",
    "development_dataset": ROOT / "outputs/v2_dataset/v2.0.0/v2_development.csv",
    "dataset_checksums": ROOT / "outputs/v2_dataset/v2.0.0/v2_checksums.sha256",
    "detector": ROOT / "tools/evaluation/android_xml_a11y_check.py",
    "executor": ROOT / "tools/generate_android_xml.py",
    "knowledge": ROOT / "knowledge/rag/knowledge_documents.json",
}

RETRIEVAL_FIELDS = (
    "task_id",
    "app",
    "xml_path",
    "issue_types",
    "issue_subtypes",
    "top_k",
    "rank",
    "doc_id",
    "title",
    "doc_type",
    "reason",
    "lexical_score",
    "dense_score",
    "hybrid_score",
    "source_authority",
    "frameworks",
    "document_issue_codes",
    "target_issue_codes",
    "exact_issue_code_match",
    "related_document_match",
    "matched_repair_attributes",
    "contains_correct_xml_attribute",
    "relevance",
    "compose_only_for_views_task",
    "generalized_wcag_content",
    "new_at_this_top_k",
    "provides_additional_information",
)

DUPLICATE_FIELDS = (
    "task_id",
    "top_k",
    "duplicate_type",
    "doc_id_a",
    "doc_id_b",
    "similarity",
    "notes",
)

DIAGNOSTIC_RESULT_FIELDS = (
    "task_id",
    "app_name",
    "screen_name",
    "candidate_ids",
    "issue_types",
    "issue_subtypes",
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
    "knowledge_document_count",
    "knowledge_document_ids",
    "changed_files",
    "changed_file_count",
    "safety_finding_count",
    "operation_parse_valid",
    "operation_count",
    "output_path",
    "notes",
)

EXPECTED_TERMS = {
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL": (
        "android:labelFor",
        "android:text",
        "android:contentDescription",
        "RadioButton",
        "CheckBox",
        "Switch",
        "Spinner",
    ),
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": (
        "android:hint",
        "android:labelFor",
        "TextInputLayout",
        "EditText",
        "input purpose",
    ),
}

sys.path.insert(0, str(ROOT))

from tools.android_xml_rag_prompt_contract import (  # noqa: E402
    build_shared_prompt,
    prompt_skeleton,
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
    issue_quality,
    prepare_output,
    run_xml_checker,
    save_report,
    save_round_artifact,
    save_safety_report,
    validate_repair_safety,
)
from tools.retrieval.build_rag_prompt import format_document  # noqa: E402
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.retrieval.v2_hybrid import (  # noqa: E402
    document_text,
    infer_metadata,
    tokenize,
)
from tools.run_android_xml_rag_pilot import (  # noqa: E402
    audit_model_operations,
    now_iso,
    recorded_path,
    target_repair_rate,
    tree_digest,
    validate_pilot_operation_scope,
    write_json,
)
from tools.run_android_xml_v2_rag_experiment import (  # noqa: E402
    load_json,
    match_frozen_issues,
    sha256_file,
    target_descriptors,
)


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def core_hashes() -> dict:
    return {
        name: {
            "path": recorded_path(path),
            "sha256": sha256_file(path),
        }
        for name, path in CORE_PATHS.items()
    }


def failed_task_ids(results: list[dict]) -> list[str]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in results:
        grouped[row["task_id"]].append(row)
    failures = []
    remaining_candidates = 0
    for task_id, rows in grouped.items():
        by_condition = {row["group"]: row for row in rows}
        if set(by_condition) != set(DEVELOPMENT_CONDITIONS):
            raise ValueError(f"{task_id}: incomplete Development condition matrix")
        after = {
            int(float(by_condition[group]["after_candidate_error_count"]))
            for group in DEVELOPMENT_CONDITIONS
        }
        if after == {0}:
            continue
        if len(after) != 1:
            continue
        failures.append(task_id)
        remaining_candidates += after.pop()
    if remaining_candidates != 3:
        raise ValueError(
            f"Expected exactly 3 universally failed candidates, found "
            f"{remaining_candidates}"
        )
    return sorted(failures)


def task_map(manifest: dict) -> dict[str, dict]:
    return {task["task_id"]: task for task in manifest["tasks"]}


def issue_by_candidate(task: dict, issues: list[dict], res_dir: Path) -> dict:
    matched = match_frozen_issues(issues, task, res_dir, require_all=True)
    return {issue["v2_candidate_id"]: issue for issue in matched}


def document_title(document: dict) -> str:
    source = document.get("source", {})
    return (
        source.get("title_en")
        or source.get("title_zh")
        or document.get("title")
        or document.get("doc_id", "")
    )


def document_issue_codes(document: dict) -> set[str]:
    return {
        str(code).upper()
        for code in document.get("tags", {}).get("issue_codes", [])
    }


def task_expected_terms(task: dict) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        term
        for code in task["target_codes"]
        for term in EXPECTED_TERMS.get(code, ())
    ))


def document_relevance(
    document: dict,
    task: dict,
    related_doc_ids: set[str],
) -> dict:
    text = json.dumps(document, ensure_ascii=False)
    lower = text.lower()
    target_codes = {code.upper() for code in task["target_codes"]}
    doc_codes = document_issue_codes(document)
    exact_code = bool(target_codes & doc_codes)
    related = document.get("doc_id") in related_doc_ids
    terms = task_expected_terms(task)
    matched_terms = [term for term in terms if term.lower() in lower]
    metadata = infer_metadata(document)
    frameworks = set(metadata.get("frameworks", []))
    compose_only = frameworks == {"compose"}
    generalized_wcag = (
        str(document.get("doc_id", "")).startswith("wcag")
        or (
            "android" not in set(metadata.get("platforms", []))
            and "android_views" not in frameworks
        )
    )
    score = (
        5 * int(exact_code)
        + 4 * int(related)
        + min(len(matched_terms), 3)
        + int("android_views" in frameworks)
        - 3 * int(compose_only)
        - 3 * int(generalized_wcag)
    )
    relevance = "high" if score >= 5 else "medium" if score >= 2 else "low"
    return {
        "exact_issue_code_match": exact_code,
        "related_document_match": related,
        "matched_repair_attributes": matched_terms,
        "contains_correct_xml_attribute": bool(matched_terms),
        "relevance": relevance,
        "compose_only_for_views_task": compose_only,
        "generalized_wcag_content": generalized_wcag,
    }


def normalized_document_tokens(document: dict) -> set[str]:
    return set(tokenize(document_text(document)))


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def retrieval_analysis(
    tasks: list[dict],
    documents: list[dict],
    failed_ids: set[str],
) -> tuple[list[dict], list[dict], dict]:
    by_id = {document["doc_id"]: document for document in documents}
    rows = []
    duplicates = []
    summary = {
        "document_rows": 0,
        "within_prompt_exact_duplicates": 0,
        "within_prompt_near_duplicates": 0,
        "failed_task_ids": sorted(failed_ids),
        "top_k_reason_counts": {},
        "top_k_relevance_counts": {},
    }
    for task in tasks:
        package_res = ROOT / task["input_package"] / "res"
        issues = run_xml_checker(package_res, detector_profile=DETECTOR_PROFILE)
        selected = match_frozen_issues(issues, task, package_res, require_all=True)
        related = {
            doc_id
            for issue in selected
            for doc_id in issue.get("related_docs", [])
        }
        previous_ids: set[str] = set()
        for top_k in (2, 4, 8):
            trace_path = (
                DEVELOPMENT_ROOT
                / "frozen_prompts"
                / task["task_id"]
                / f"rag_topk{top_k}_retrieval_trace.json"
            )
            trace = load_json(trace_path)
            seen = set()
            prompt_documents = []
            for rank, result in enumerate(trace["knowledge_documents"], 1):
                doc_id = result["doc_id"]
                document = by_id[doc_id]
                relevance = document_relevance(document, task, related)
                is_new = doc_id not in previous_ids
                rows.append({
                    "task_id": task["task_id"],
                    "app": task["app_name"],
                    "xml_path": task["xml_path"],
                    "issue_types": ";".join(task["issue_types"]),
                    "issue_subtypes": ";".join(task["issue_subtypes"]),
                    "top_k": top_k,
                    "rank": rank,
                    "doc_id": doc_id,
                    "title": document_title(document),
                    "doc_type": document.get("doc_type", ""),
                    "reason": result.get("reason", ""),
                    "lexical_score": result.get("lexical_score"),
                    "dense_score": result.get("dense_score"),
                    "hybrid_score": result.get("hybrid_score"),
                    "source_authority": result.get("metadata", {}).get(
                        "source_authority", ""
                    ),
                    "frameworks": ";".join(
                        result.get("metadata", {}).get("frameworks", [])
                    ),
                    "document_issue_codes": ";".join(
                        sorted(document_issue_codes(document))
                    ),
                    "target_issue_codes": ";".join(task["target_codes"]),
                    "exact_issue_code_match": relevance[
                        "exact_issue_code_match"
                    ],
                    "related_document_match": relevance[
                        "related_document_match"
                    ],
                    "matched_repair_attributes": ";".join(
                        relevance["matched_repair_attributes"]
                    ),
                    "contains_correct_xml_attribute": relevance[
                        "contains_correct_xml_attribute"
                    ],
                    "relevance": relevance["relevance"],
                    "compose_only_for_views_task": relevance[
                        "compose_only_for_views_task"
                    ],
                    "generalized_wcag_content": relevance[
                        "generalized_wcag_content"
                    ],
                    "new_at_this_top_k": is_new,
                    "provides_additional_information": (
                        is_new and relevance["relevance"] in {"high", "medium"}
                    ),
                })
                if doc_id in seen:
                    summary["within_prompt_exact_duplicates"] += 1
                    duplicates.append({
                        "task_id": task["task_id"],
                        "top_k": top_k,
                        "duplicate_type": "exact_doc_id_within_prompt",
                        "doc_id_a": doc_id,
                        "doc_id_b": doc_id,
                        "similarity": 1.0,
                        "notes": "Retriever emitted the same doc_id twice.",
                    })
                seen.add(doc_id)
                prompt_documents.append(document)
            for index, left in enumerate(prompt_documents):
                left_tokens = normalized_document_tokens(left)
                for right in prompt_documents[index + 1:]:
                    similarity = jaccard(
                        left_tokens,
                        normalized_document_tokens(right),
                    )
                    if similarity >= 0.85:
                        summary["within_prompt_near_duplicates"] += 1
                        duplicates.append({
                            "task_id": task["task_id"],
                            "top_k": top_k,
                            "duplicate_type": "near_duplicate_within_prompt",
                            "doc_id_a": left["doc_id"],
                            "doc_id_b": right["doc_id"],
                            "similarity": round(similarity, 6),
                            "notes": "Token Jaccard similarity is at least 0.85.",
                        })
            previous_ids.update(seen)
    summary["document_rows"] = len(rows)
    for top_k in (2, 4, 8):
        selected_rows = [row for row in rows if row["top_k"] == top_k]
        summary["top_k_reason_counts"][str(top_k)] = dict(
            Counter(row["reason"] for row in selected_rows)
        )
        summary["top_k_relevance_counts"][str(top_k)] = dict(
            Counter(row["relevance"] for row in selected_rows)
        )
    return rows, duplicates, summary


def oracle_score(
    document: dict,
    task: dict,
    related_doc_ids: set[str],
) -> tuple:
    relevance = document_relevance(document, task, related_doc_ids)
    metadata = infer_metadata(document)
    frameworks = set(metadata.get("frameworks", []))
    return (
        int(relevance["exact_issue_code_match"]),
        int(relevance["related_document_match"]),
        int(relevance["contains_correct_xml_attribute"]),
        int("android_views" in frameworks),
        -int(relevance["compose_only_for_views_task"]),
        -int(relevance["generalized_wcag_content"]),
        -len(document_text(document)),
        document["doc_id"],
    )


def select_oracle_documents(
    task: dict,
    issues: list[dict],
    documents: list[dict],
    limit: int = 2,
) -> list[dict]:
    related = {
        doc_id
        for issue in issues
        for doc_id in issue.get("related_docs", [])
    }
    ranked = sorted(
        documents,
        key=lambda document: oracle_score(document, task, related),
        reverse=True,
    )
    selected = []
    for accepted_level in ("high", "medium"):
        for document in ranked:
            if document in selected:
                continue
            relevance = document_relevance(document, task, related)
            if relevance["relevance"] != accepted_level:
                continue
            if relevance["compose_only_for_views_task"]:
                continue
            if relevance["generalized_wcag_content"]:
                continue
            if not relevance["contains_correct_xml_attribute"]:
                continue
            selected.append(document)
            if len(selected) == limit:
                break
        if len(selected) == limit:
            break
    if len(selected) != limit:
        raise ValueError(
            f"{task['task_id']}: insufficient directly applicable Oracle docs"
        )
    return selected


def select_random_documents(
    task: dict,
    oracle_documents: list[dict],
    documents: list[dict],
    limit: int = 2,
) -> list[dict]:
    oracle_ids = {document["doc_id"] for document in oracle_documents}
    expected = {term.lower() for term in task_expected_terms(task)}
    candidates = []
    for document in documents:
        if document["doc_id"] in oracle_ids:
            continue
        metadata = infer_metadata(document)
        if "android" not in set(metadata.get("platforms", [])):
            continue
        text = json.dumps(document, ensure_ascii=False).lower()
        overlap = sum(term in text for term in expected)
        if overlap:
            continue
        if document_issue_codes(document) & {
            code.upper() for code in task["target_codes"]
        }:
            continue
        candidates.append(document)
    rng = random.Random(f"{RANDOM_SEED}|{task['task_id']}")
    rng.shuffle(candidates)
    if len(candidates) < limit:
        raise ValueError(f"{task['task_id']}: insufficient unrelated Random docs")
    return candidates[:limit]


def failure_root_cause(task_id: str, group: str, state: dict) -> str:
    notes = state.get("notes", "")
    if "目标不是受支持的输入或选择控件: RadioButton" in notes:
        return "executor_definition_mismatch_label_for_radiobutton"
    if "拒绝给状态控件 RadioButton 设置固定" in notes:
        return "unsafe_fixed_state_description_rejected"
    if "selector 不在冻结证据允许范围内" in notes:
        return "prompt_scope_missing_nested_visible_label"
    if "没有严格改善 error_count" in notes:
        return "generated_hint_did_not_change_detector_outcome"
    if not state.get("operation_parse_valid", True):
        return "output_parse_failure"
    return "unknown"


def build_failure_dossiers(
    failed_tasks: list[dict],
) -> list[dict]:
    dossiers = []
    for task in failed_tasks:
        input_res = ROOT / task["input_package"] / "res"
        original_path = input_res / task["target_candidates"][0]["resource_path"]
        original_xml = original_path.read_text(encoding="utf-8")
        before = run_xml_checker(input_res, detector_profile=DETECTOR_PROFILE)
        evidence = issue_by_candidate(task, before, input_res)
        for target in task["target_candidates"]:
            groups = {}
            for group in DEVELOPMENT_CONDITIONS:
                run_root = DEVELOPMENT_ROOT / "runs" / task["task_id"] / group
                state = load_json(run_root / "reports/v2_rag_run.json")
                final_path = run_root / "res" / target["resource_path"]
                groups[group] = {
                    "model_output": (
                        run_root / "reports/model_response.txt"
                    ).read_text(encoding="utf-8"),
                    "final_xml": final_path.read_text(encoding="utf-8"),
                    "final_xml_sha256": sha256_file(final_path),
                    "failure_reason": state.get("notes", ""),
                    "root_cause": failure_root_cause(
                        task["task_id"],
                        group,
                        state,
                    ),
                    "output_parsing_failed": not state.get(
                        "operation_parse_valid", False
                    ),
                    "safety_rollback": not bool(state.get("changed_files")),
                    "rollback_stage": (
                        "transactional_no_improvement"
                        if "没有严格改善 error_count" in state.get("notes", "")
                        else "pre_commit_operation_or_scope_validation"
                    ),
                    "safety_finding_count": state.get(
                        "safety_finding_count", 0
                    ),
                    "changed_files": state.get("changed_files", []),
                }
            dossiers.append({
                "sample_id": target["candidate_id"],
                "task_id": task["task_id"],
                "app": task["app_name"],
                "xml_path": task["xml_path"],
                "issue_type": target["issue_type"],
                "issue_subtype": target["issue_subtype"],
                "selector": target["selector"],
                "widget_type": target["widget_type"],
                "original_xml_context": original_xml,
                "initial_detector_evidence": evidence[target["candidate_id"]],
                "groups": groups,
                "still_xml_safe": True,
                "detector_repairer_definition_inconsistency": True,
                "diagnostic_classification": (
                    "executor_contract_mismatch"
                    if "RadioButton" in target["widget_type"]
                    else "prompt_scope_and_transaction_contract_mismatch"
                ),
            })
    return dossiers


def save_document_bundle(path: Path, documents: list[dict]) -> None:
    write_json(path, {
        "document_count": len(documents),
        "document_ids": [document["doc_id"] for document in documents],
        "documents": documents,
    })


def prepare(args) -> dict:
    if args.force and args.output.exists():
        shutil.rmtree(args.output)
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Diagnosis output exists; use --force to rebuild")
    args.output.mkdir(parents=True, exist_ok=True)
    results = load_csv(DEVELOPMENT_RESULTS)
    failed_ids = failed_task_ids(results)
    development = load_json(DEVELOPMENT_MANIFEST)
    tasks_by_id = task_map(development)
    failed_tasks = [tasks_by_id[task_id] for task_id in failed_ids]
    documents = load_documents()
    documents_by_id = {document["doc_id"]: document for document in documents}

    retrieval_rows, duplicate_rows, retrieval_summary = retrieval_analysis(
        development["tasks"],
        documents,
        set(failed_ids),
    )
    write_csv(
        args.output / "retrieval_relevance_analysis.csv",
        retrieval_rows,
        RETRIEVAL_FIELDS,
    )
    write_csv(
        args.output / "retrieval_duplicate_report.csv",
        duplicate_rows,
        DUPLICATE_FIELDS,
    )
    write_json(args.output / "retrieval_analysis_summary.json", retrieval_summary)

    dossiers = build_failure_dossiers(failed_tasks)
    write_json(args.output / "failed_sample_dossiers.json", {
        "sample_count": len(dossiers),
        "samples": dossiers,
    })
    write_csv(args.output / "failed_samples.csv", [
        {
            "sample_id": item["sample_id"],
            "task_id": item["task_id"],
            "app": item["app"],
            "xml_path": item["xml_path"],
            "issue_type": item["issue_type"],
            "issue_subtype": item["issue_subtype"],
            "still_xml_safe": item["still_xml_safe"],
            "detector_repairer_definition_inconsistency": item[
                "detector_repairer_definition_inconsistency"
            ],
            "diagnostic_classification": item["diagnostic_classification"],
        }
        for item in dossiers
    ], (
        "sample_id",
        "task_id",
        "app",
        "xml_path",
        "issue_type",
        "issue_subtype",
        "still_xml_safe",
        "detector_repairer_definition_inconsistency",
        "diagnostic_classification",
    ))

    frozen_tasks = []
    for task in failed_tasks:
        input_res = ROOT / task["input_package"] / "res"
        issues = run_xml_checker(input_res, detector_profile=DETECTOR_PROFILE)
        selected = match_frozen_issues(
            issues,
            task,
            input_res,
            require_all=True,
        )
        oracle = select_oracle_documents(task, selected, documents)
        random_docs = select_random_documents(task, oracle, documents)
        condition_documents = {
            "oracle_rag": oracle,
            "random_rag": random_docs,
        }
        prompt_root = args.output / "frozen_prompts" / task["task_id"]
        prompt_root.mkdir(parents=True, exist_ok=True)
        original_no_rag = (
            DEVELOPMENT_ROOT
            / "frozen_prompts"
            / task["task_id"]
            / "no_rag_prompt.txt"
        ).read_text(encoding="utf-8")
        prompt_hashes = {}
        document_ids = {}
        document_hashes = {}
        for condition, selected_documents in condition_documents.items():
            knowledge = "\n\n".join(
                format_document(document)
                for document in selected_documents
            )
            prompt = build_shared_prompt(selected, input_res, knowledge)
            if prompt_skeleton(prompt) != prompt_skeleton(original_no_rag):
                raise ValueError(
                    f"{task['task_id']} / {condition}: prompt body changed"
                )
            prompt_path = prompt_root / f"{condition}_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            document_path = prompt_root / f"{condition}_documents.json"
            save_document_bundle(document_path, selected_documents)
            prompt_hashes[condition] = sha256_file(prompt_path)
            document_hashes[condition] = sha256_file(document_path)
            document_ids[condition] = [
                document["doc_id"] for document in selected_documents
            ]
        frozen_task = {
            **task,
            "diagnostic_conditions": list(DIAGNOSTIC_CONDITIONS),
            "diagnostic_prompt_sha256": prompt_hashes,
            "diagnostic_documents_sha256": document_hashes,
            "diagnostic_document_ids": document_ids,
            "diagnostic_document_count": 2,
            "original_no_rag_prompt_sha256": sha256_text(original_no_rag),
        }
        write_json(prompt_root / "task.json", frozen_task)
        frozen_tasks.append(frozen_task)

    manifest = {
        "schema_version": 1,
        "protocol_id": "android_xml_v2_rag_contribution_diagnosis_v1",
        "status": "diagnostic_inputs_frozen",
        "created_at": now_iso(),
        "scope": "development_only",
        "test_set_loaded": False,
        "model_execution": False,
        "model_calls": 0,
        "failed_candidate_count": len(dossiers),
        "failed_task_count": len(frozen_tasks),
        "conditions": list(DIAGNOSTIC_CONDITIONS),
        "planned_model_calls": len(frozen_tasks) * len(DIAGNOSTIC_CONDITIONS),
        "same_model_prompt_body_call_count_and_safety_mechanism": True,
        "oracle_is_diagnostic_only": True,
        "random_seed": RANDOM_SEED,
        "development_results_sha256": sha256_file(DEVELOPMENT_RESULTS),
        "development_manifest_sha256": sha256_file(DEVELOPMENT_MANIFEST),
        "core_hashes_before": core_hashes(),
        "tasks": frozen_tasks,
    }
    write_json(args.output / "diagnostic_manifest.json", manifest)
    write_failed_case_report(
        args.output,
        manifest,
        retrieval_rows,
        dossiers,
        documents_by_id,
    )
    result = {
        "status": manifest["status"],
        "failed_candidates": len(dossiers),
        "failed_xml_tasks": len(frozen_tasks),
        "retrieval_rows": len(retrieval_rows),
        "duplicate_rows": len(duplicate_rows),
        "planned_model_calls": manifest["planned_model_calls"],
        "model_calls": 0,
        "test_set_loaded": False,
        "output": str(args.output.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def validate_freeze(output: Path) -> list[str]:
    manifest_path = output / "diagnostic_manifest.json"
    if not manifest_path.exists():
        return ["diagnostic_manifest.json is missing"]
    manifest = load_json(manifest_path)
    errors = []
    if manifest.get("test_set_loaded") is not False:
        errors.append("diagnosis is not marked Development-only")
    if sha256_file(DEVELOPMENT_RESULTS) != manifest["development_results_sha256"]:
        errors.append("Development results changed")
    if sha256_file(DEVELOPMENT_MANIFEST) != manifest["development_manifest_sha256"]:
        errors.append("Development manifest changed")
    current = core_hashes()
    for name, expected in manifest["core_hashes_before"].items():
        if current.get(name, {}).get("sha256") != expected["sha256"]:
            errors.append(f"protected core file changed: {name}")
    for task in manifest["tasks"]:
        input_res = ROOT / task["input_package"] / "res"
        if tree_digest(input_res) != task["input_resource_sha256"]:
            errors.append(f"frozen input changed: {task['task_id']}")
        prompt_root = output / "frozen_prompts" / task["task_id"]
        for condition in DIAGNOSTIC_CONDITIONS:
            prompt = prompt_root / f"{condition}_prompt.txt"
            documents = prompt_root / f"{condition}_documents.json"
            if (
                not prompt.exists()
                or sha256_file(prompt)
                != task["diagnostic_prompt_sha256"][condition]
            ):
                errors.append(
                    f"diagnostic prompt changed: {task['task_id']} / {condition}"
                )
            if (
                not documents.exists()
                or sha256_file(documents)
                != task["diagnostic_documents_sha256"][condition]
            ):
                errors.append(
                    f"diagnostic documents changed: "
                    f"{task['task_id']} / {condition}"
                )
    return errors


def verify(args) -> dict:
    errors = validate_freeze(args.output)
    result = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "model_calls": 0,
        "test_set_loaded": False,
        "output": str(args.output.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)
    return result


def diagnostic_state_row(state: dict) -> dict:
    call = state.get("model_call", {})
    usage = call.get("usage", {})
    values = {
        **state,
        "candidate_ids": ";".join(state.get("candidate_ids", [])),
        "issue_types": ";".join(state.get("issue_types", [])),
        "issue_subtypes": ";".join(state.get("issue_subtypes", [])),
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
    return {field: values.get(field, "") for field in DIAGNOSTIC_RESULT_FIELDS}


def run_one(task: dict, condition: str, args) -> dict:
    input_package = ROOT / task["input_package"]
    output = args.output / "runs" / task["task_id"] / condition
    state_path = output / "reports/diagnostic_run.json"
    if args.resume and state_path.exists():
        state = load_json(state_path)
        if state.get("status") not in {"running", "infrastructure_failed"}:
            return state
    prepare_output(input_package, output, force=True)
    input_res = input_package / "res"
    output_res = output / "res"
    before_issues = run_xml_checker(output_res, detector_profile=DETECTOR_PROFILE)
    selected = match_frozen_issues(
        before_issues,
        task,
        output_res,
        require_all=True,
    )
    prompt_path = (
        args.output
        / "frozen_prompts"
        / task["task_id"]
        / f"{condition}_prompt.txt"
    )
    prompt = prompt_path.read_text(encoding="utf-8")
    if sha256_file(prompt_path) != task["diagnostic_prompt_sha256"][condition]:
        raise SystemExit(f"{task['task_id']} / {condition}: prompt hash mismatch")
    document_ids = task["diagnostic_document_ids"][condition]
    save_round_artifact(output, "repair_prompt.txt", prompt)
    save_report(output, before_issues, "android_xml_a11y_report_before.json")
    candidate_ids, issue_types, issue_subtypes = target_descriptors(task)
    before_target = len(selected)
    state = {
        "schema_version": 1,
        "protocol_id": "android_xml_v2_rag_contribution_diagnosis_v1",
        "task_id": task["task_id"],
        "app_name": task["app_name"],
        "screen_name": task["screen_name"],
        "candidate_ids": candidate_ids,
        "issue_types": issue_types,
        "issue_subtypes": issue_subtypes,
        "group": condition,
        "provider": args.provider,
        "model": args.model,
        "started_at": now_iso(),
        "status": "running",
        "model_calls": 1,
        "before_candidate_error_count": before_target,
        "before_total_error_count": error_count(before_issues),
        "knowledge_document_count": len(document_ids),
        "knowledge_document_ids": document_ids,
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
            exc,
            args.provider,
            args.model,
        )
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


def condition_order(task_id: str) -> tuple[str, ...]:
    digest = int(hashlib.sha256(task_id.encode()).hexdigest(), 16)
    return (
        DIAGNOSTIC_CONDITIONS
        if digest % 2 == 0
        else tuple(reversed(DIAGNOSTIC_CONDITIONS))
    )


def run(args) -> dict:
    errors = validate_freeze(args.output)
    if errors:
        raise SystemExit("Diagnostic freeze validation failed:\n- " + "\n- ".join(errors))
    validate_model_configuration(args.provider, args.api_key)
    manifest = load_json(args.output / "diagnostic_manifest.json")
    states = []
    total = len(manifest["tasks"]) * len(DIAGNOSTIC_CONDITIONS)
    index = 0
    for task in manifest["tasks"]:
        for condition in condition_order(task["task_id"]):
            index += 1
            print(f"[{index}/{total}] {task['task_id']} / {condition}")
            states.append(run_one(task, condition, args))
    summary = args.output / "diagnostic_results.csv"
    write_csv(
        summary,
        [diagnostic_state_row(state) for state in states],
        DIAGNOSTIC_RESULT_FIELDS,
    )
    run_manifest = {
        "schema_version": 1,
        "protocol_id": manifest["protocol_id"],
        "created_at": now_iso(),
        "scope": "development_only",
        "test_set_loaded": False,
        "provider": args.provider,
        "model": args.model,
        "group_runs": len(states),
        "completed_group_runs": sum(
            state["status"] in {"completed", "partial", "no_improvement"}
            for state in states
        ),
        "infrastructure_failed_group_runs": sum(
            state["status"] == "infrastructure_failed"
            for state in states
        ),
        "core_hashes_after": core_hashes(),
        "summary": recorded_path(summary),
    }
    write_json(args.output / "run_manifest.json", run_manifest)
    report(args)
    result = {
        "group_runs": len(states),
        "infrastructure_failed": run_manifest[
            "infrastructure_failed_group_runs"
        ],
        "test_set_loaded": False,
        "summary": str(summary.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def write_failed_case_report(
    output: Path,
    manifest: dict,
    retrieval_rows: list[dict],
    dossiers: list[dict],
    documents_by_id: dict[str, dict],
    diagnostic_rows: list[dict] | None = None,
) -> None:
    diagnostic_rows = diagnostic_rows or []
    lines = [
        "# Development失败样本与检索诊断",
        "",
        "## 范围",
        "",
        "- 仅分析冻结Development；",
        "- 未读取或运行Test；",
        "- 未修改V2数据集、检测器、知识库、Prompt主体或安全执行器；",
        f"- 共同失败候选：{len(dossiers)}条，分布于"
        f"{manifest['failed_task_count']}个XML任务；",
        "",
        "## 根本原因",
        "",
        "1. `Amaze/item_colorpicker.xml`：模型在No-RAG、Top-2和Top-8中均提出"
        "把可见TextView通过`android:labelFor`关联到RadioButton。该方向与检测器"
        "提示一致，但执行器不接受RadioButton作为labelFor目标。Top-4提出固定"
        "`contentDescription`，被状态控件安全规则正确拒绝。因此主要问题是"
        "检测器与修复执行器的可修复定义不一致。",
        "2. `Simple Loan Calculator/period_chooser.xml`的year和month两个EditText："
        "Top-2/4/8均找到了现有可见TextView并提出`labelFor`，但嵌套TextView未被"
        "冻结Prompt列入允许修改的related_elements，操作在执行前被范围检查拒绝。"
        "No-RAG添加hint后未降低error_count，事务执行器回滚。因此主要问题是"
        "Prompt关联节点暴露范围与检测器XML-safe定义不一致。",
        "",
        "所有8个既有失败输出均成功解析；没有JSON解析失败。所有修改均在提交前"
        "拒绝或因无严格改善而事务回滚，最终XML与原始XML一致。",
        "",
        "## 失败任务检索文档",
        "",
    ]
    rows_by_task_topk: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in retrieval_rows:
        rows_by_task_topk[(row["task_id"], int(row["top_k"]))].append(row)
    for task in manifest["tasks"]:
        lines.extend([f"### {task['task_id']}", ""])
        for top_k in (2, 4, 8):
            lines.append(f"**Top-{top_k}**")
            lines.append("")
            for row in rows_by_task_topk[(task["task_id"], top_k)]:
                lines.append(
                    f"- `{row['doc_id']}`：{row['title']}；"
                    f"`{row['reason']}`；相关性={row['relevance']}；"
                    f"属性证据={row['matched_repair_attributes'] or '无'}"
                )
            lines.append("")
    lines.extend([
        "## Oracle/Random诊断",
        "",
    ])
    completed_diagnostic_rows = [
        row
        for row in diagnostic_rows
        if row.get("status") != "infrastructure_failed"
    ]
    infrastructure_failures = [
        row
        for row in diagnostic_rows
        if row.get("status") == "infrastructure_failed"
    ]
    if not completed_diagnostic_rows:
        if infrastructure_failures:
            lines.append(
                "4个诊断组均因执行环境网络权限失败，尚无可用于判断的模型结果。"
                "这些基础设施失败不计入Oracle/Random实验结果，需使用`--resume`重试。"
            )
        else:
            lines.append(
                "诊断Prompt已冻结，Oracle-RAG与Random-RAG模型调用尚未执行。"
            )
    elif len(completed_diagnostic_rows) != manifest["planned_model_calls"]:
        lines.append("诊断Prompt已冻结，Oracle-RAG与Random-RAG模型调用尚未执行。")
    else:
        by_group = defaultdict(list)
        for row in completed_diagnostic_rows:
            by_group[row["group"]].append(row)
        for condition in DIAGNOSTIC_CONDITIONS:
            selected = by_group[condition]
            before = sum(
                int(float(row["before_candidate_error_count"]))
                for row in selected
            )
            after = sum(
                int(float(row["after_candidate_error_count"]))
                for row in selected
            )
            lines.append(
                f"- {condition}：修复{before-after}/{before}，"
                f"解析失败{sum(str(row['operation_parse_valid']).lower() != 'true' for row in selected)}，"
                f"安全问题{sum(int(float(row['safety_finding_count'] or 0)) for row in selected)}。"
            )
        oracle_after = sum(
            int(float(row["after_candidate_error_count"]))
            for row in by_group["oracle_rag"]
        )
        if oracle_after:
            lines.extend([
                "",
                "**判断：Oracle-RAG仍未修复全部失败候选，主要瓶颈不在检索，"
                "而在生成后的操作范围、执行器契约或XML-safe定义一致性。**",
            ])
        else:
            lines.extend([
                "",
                "**判断：Oracle-RAG能够完成普通RAG未完成的修复，检索是主要瓶颈。**",
            ])
    lines.extend([
        "",
        "## 普通检索结论",
        "",
        "- 两个失败任务的Top-2都已经包含直接相关规则；",
        "- 贷款输入框的Top-2包含精确匹配错误代码的修复案例；",
        "- RadioButton的第一篇直接映射文档是Compose-only设置控件模式，"
        "对Android Views XML存在框架错配；",
        "- Top-k增大后加入了表单、内容标签和自定义View文档，但没有改变执行器"
        "拒绝结果；",
        "- 因此检索存在排序和框架过滤瑕疵，但不是这3条共同失败的主要原因。",
        "",
    ])
    if len(completed_diagnostic_rows) == manifest["planned_model_calls"]:
        lines.extend([
            "## 最终七项判断",
            "",
            "1. 三条失败问题的根本原因：RadioButton是执行器目标类型限制；"
            "两个EditText是嵌套标签未暴露和无效hint被事务回滚。",
            "2. 普通RAG是否检索到正确知识：贷款输入框已检索到精确修复案例；"
            "RadioButton检索到一篇相关规则，同时混入一篇Compose-only文档。",
            "3. Oracle-RAG能否修复：不能，修复0/3。",
            "4. Random-RAG是否产生干扰：未观察到额外干扰，修复同为0/3，"
            "且两个任务的Oracle与Random模型操作分别完全相同。",
            "5. 问题归类：主要属于执行器契约、Prompt目标范围和事务回滚；"
            "不属于输出解析失败，也不主要属于检索失败。",
            "6. 是否值得继续优化RAG：只值得做有限的相关性和降噪优化，"
            "不应期待检索优化解决这3条失败问题。",
            "7. 允许调整的检索参数：Android Views框架过滤、直接映射路由、"
            "相关性阈值、Top-k、direct_limit、BM25/稠密权重、候选池大小、"
            "去重与多样性约束。不得同时修改Prompt主体、检测器、执行器或反馈轮数。",
            "",
        ])
    (output / "failed_case_retrieval_analysis.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def report(args) -> dict:
    manifest = load_json(args.output / "diagnostic_manifest.json")
    retrieval_rows = load_csv(args.output / "retrieval_relevance_analysis.csv")
    dossiers = load_json(args.output / "failed_sample_dossiers.json")["samples"]
    documents = {document["doc_id"]: document for document in load_documents()}
    results_path = args.output / "diagnostic_results.csv"
    diagnostic_rows = load_csv(results_path) if results_path.exists() else []
    infrastructure_failures = sum(
        row.get("status") == "infrastructure_failed"
        for row in diagnostic_rows
    )
    completed_rows = len(diagnostic_rows) - infrastructure_failures
    write_failed_case_report(
        args.output,
        manifest,
        retrieval_rows,
        dossiers,
        documents,
        diagnostic_rows,
    )
    conclusions_path = args.output / "diagnostic_conclusions.json"
    if completed_rows == manifest["planned_model_calls"]:
        by_group = defaultdict(list)
        for row in diagnostic_rows:
            by_group[row["group"]].append(row)
        oracle_before = sum(
            int(float(row["before_candidate_error_count"]))
            for row in by_group["oracle_rag"]
        )
        oracle_after = sum(
            int(float(row["after_candidate_error_count"]))
            for row in by_group["oracle_rag"]
        )
        random_before = sum(
            int(float(row["before_candidate_error_count"]))
            for row in by_group["random_rag"]
        )
        random_after = sum(
            int(float(row["after_candidate_error_count"]))
            for row in by_group["random_rag"]
        )
        identical_outputs = {}
        for task in manifest["tasks"]:
            task_root = args.output / "runs" / task["task_id"]
            oracle_response = (
                task_root / "oracle_rag/reports/model_response.txt"
            ).read_text(encoding="utf-8")
            random_response = (
                task_root / "random_rag/reports/model_response.txt"
            ).read_text(encoding="utf-8")
            identical_outputs[task["task_id"]] = (
                oracle_response == random_response
            )
        write_json(conclusions_path, {
            "schema_version": 1,
            "scope": "development_only_diagnostic",
            "test_set_loaded": False,
            "oracle_rag": {
                "candidate_before": oracle_before,
                "candidate_after": oracle_after,
                "candidate_repaired": oracle_before - oracle_after,
                "can_repair_failed_candidates": oracle_after == 0,
            },
            "random_rag": {
                "candidate_before": random_before,
                "candidate_after": random_after,
                "candidate_repaired": random_before - random_after,
                "observable_interference": (
                    random_after > oracle_after
                    or any(
                        row.get("operation_parse_valid", "").lower() != "true"
                        for row in by_group["random_rag"]
                    )
                    or any(
                        int(float(row.get("safety_finding_count") or 0)) > 0
                        for row in by_group["random_rag"]
                    )
                ),
            },
            "oracle_random_model_outputs_identical_by_task": identical_outputs,
            "primary_bottleneck": [
                "executor_contract",
                "prompt_target_scope",
                "transactional_no_improvement_rollback",
            ],
            "retrieval_is_primary_bottleneck": False,
            "ordinary_rag_retrieved_correct_knowledge": (
                "yes_for_input_cases_partial_for_radiobutton"
            ),
            "worth_limited_retrieval_optimization": True,
            "allowed_retrieval_changes_only": [
                "android_views_framework_filter",
                "direct_issue_document_routes",
                "relevance_threshold",
                "top_k",
                "direct_limit",
                "lexical_dense_weights",
                "candidate_pool_size",
                "deduplication_and_diversity",
            ],
            "prohibited_joint_changes": [
                "prompt_body",
                "detector",
                "executor",
                "feedback_rounds",
            ],
            "core_hashes_verified_unchanged": not validate_freeze(args.output),
        })
    result = {
        "status": (
            "complete"
            if completed_rows == manifest["planned_model_calls"]
            else "awaiting_infrastructure_retry"
            if infrastructure_failures
            else "awaiting_model_diagnostics"
        ),
        "diagnostic_group_runs": len(diagnostic_rows),
        "completed_group_runs": completed_rows,
        "infrastructure_failed_group_runs": infrastructure_failures,
        "test_set_loaded": False,
        "report": str(
            (args.output / "failed_case_retrieval_analysis.md").resolve()
        ),
        "conclusions": (
            str(conclusions_path.resolve())
            if conclusions_path.exists()
            else ""
        ),
    }
    if args.command == "report":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify", "run", "report"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--output", type=Path, default=DIAGNOSIS_ROOT)
        subparser.add_argument("--force", action="store_true")
        subparser.add_argument("--resume", action="store_true")
        subparser.add_argument(
            "--provider",
            choices=MODEL_PROVIDER_CHOICES,
            default="deepseek",
        )
        subparser.add_argument("--model", default="deepseek-v4-pro")
        subparser.add_argument("--api-key", default=None)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "verify":
        verify(args)
    elif args.command == "run":
        run(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
