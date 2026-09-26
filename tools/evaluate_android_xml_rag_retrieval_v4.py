#!/usr/bin/env python3
"""Evaluate V4 Android XML retrieval offline without model calls."""
import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT
    / "experiments/android_xml_rag_contribution/equal_budget_limit8_confirmation_v3_1"
    / "frozen_manifest.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_rag_contribution/retrieval_v4_offline"
)
DEFAULT_GOLD = (
    ROOT
    / "experiments/android_xml_rag_contribution/retrieval_relevance_gold_v1.json"
)

sys.path.insert(0, str(ROOT))


from tools.android_xml_rag_prompt_contract import build_prompt_pair  # noqa: E402
from tools.generate_android_xml import issue_severity, run_xml_checker  # noqa: E402
from tools.retrieval.search_documents import load_documents  # noqa: E402


def task_issues(task, package):
    target_codes = set(task["target_codes"])
    return [
        issue
        for issue in run_xml_checker(package / "res", detector_profile="expanded_v3")
        if issue_severity(issue) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
        and issue.get("code") in target_codes
    ]


def load_relevance_gold(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = payload.get("labels", [])
    by_code = {label["issue_code"]: label for label in labels}
    if len(by_code) != len(labels):
        raise ValueError("Duplicate issue_code in retrieval relevance gold")
    return payload, by_code


def evaluate_task(task, documents, relevance_by_code):
    package = ROOT / task["input_package"]
    issues = task_issues(task, package)
    pair = build_prompt_pair(
        issues,
        package / "res",
        documents,
        per_issue_limit=8,
        prompt_limit=8,
    )
    trace = pair["trace"]
    results = trace["knowledge_documents"]
    retrieved_ids = [item["doc_id"] for item in results]
    target_codes = sorted({issue.get("code") for issue in issues})
    code_metrics = []
    for code in target_codes:
        if code not in relevance_by_code:
            raise ValueError(f"Missing independent relevance label for {code}")
        label = relevance_by_code[code]
        actionable_ids = label.get("actionable_document_ids", [])
        supporting_ids = label.get("supporting_document_ids", [])
        relevant_ids = list(dict.fromkeys([*actionable_ids, *supporting_ids]))
        code_results = [
            item for item in results if item.get("issue_code") == code
        ]
        code_retrieved_ids = [item["doc_id"] for item in code_results]
        ranks = [
            code_retrieved_ids.index(doc_id) + 1
            for doc_id in relevant_ids
            if doc_id in code_retrieved_ids
        ]
        best_rank = min(ranks) if ranks else None
        actionable_ranks = [
            code_retrieved_ids.index(doc_id) + 1
            for doc_id in actionable_ids
            if doc_id in code_retrieved_ids
        ]
        actionable_best_rank = min(actionable_ranks) if actionable_ranks else None
        prohibited = sorted(
            set(code_retrieved_ids) & set(label.get("prohibited_document_ids", []))
        )
        code_metrics.append({
            "issue_code": code,
            "relevant_document_ids": relevant_ids,
            "actionable_document_ids": actionable_ids,
            "retrieved_document_ids": code_retrieved_ids,
            "best_rank": best_rank,
            "hit_at_4": best_rank is not None and best_rank <= 4,
            "reciprocal_rank": 1.0 / best_rank if best_rank else 0.0,
            "actionable_best_rank": actionable_best_rank,
            "actionable_hit_at_4": (
                actionable_best_rank is not None and actionable_best_rank <= 4
            ),
            "knowledge_gap": bool(label.get("knowledge_gap")),
            "prohibited_retrieved_document_ids": prohibited,
        })
    expected_ids = {
        doc_id
        for metric in code_metrics
        for doc_id in metric["relevant_document_ids"]
    }
    return {
        "task_id": task["task_id"],
        "target_issue_count": len(issues),
        "target_codes": target_codes,
        "knowledge_document_count": trace["knowledge_document_count"],
        "knowledge_injected_characters": trace["knowledge_injected_characters"],
        "dense_backend": trace.get("dense_backend"),
        "direct_result_count": sum(
            item.get("reason") == "direct_issue_mapping" for item in results
        ),
        "vector_scored_result_count": sum(
            item.get("dense_score") is not None for item in results
        ),
        "android_document_count": sum(
            "android" in item.get("metadata", {}).get("platforms", [])
            for item in results
        ),
        "evaluation_document_count": sum(
            str(item.get("doc_id", "")).startswith("android.eval.")
            for item in results
        ),
        "unmapped_document_count": sum(
            item.get("doc_id") not in expected_ids for item in results
        ),
        "retrieved_document_ids": retrieved_ids,
        "code_metrics": code_metrics,
    }


def summarize(records):
    code_metrics = [
        metric for record in records for metric in record["code_metrics"]
    ]
    document_count = sum(record["knowledge_document_count"] for record in records)
    android_count = sum(record["android_document_count"] for record in records)
    unmapped_count = sum(record["unmapped_document_count"] for record in records)
    actionable_metrics = [
        metric for metric in code_metrics if metric.get("actionable_document_ids")
    ]
    prohibited_count = sum(
        len(metric.get("prohibited_retrieved_document_ids", []))
        for metric in code_metrics
    )
    knowledge_gap_count = sum(
        bool(metric.get("knowledge_gap")) for metric in code_metrics
    )
    summary = {
        "task_count": len(records),
        "task_code_pair_count": len(code_metrics),
        "routing_hit_at_4": (
            sum(metric["hit_at_4"] for metric in code_metrics) / len(code_metrics)
            if code_metrics else 0.0
        ),
        "mean_reciprocal_rank": (
            statistics.mean(metric["reciprocal_rank"] for metric in code_metrics)
            if code_metrics else 0.0
        ),
        "actionable_hit_at_4": (
            sum(metric.get("actionable_hit_at_4", False) for metric in actionable_metrics)
            / len(actionable_metrics)
            if actionable_metrics else 0.0
        ),
        "knowledge_gap_code_pair_count": knowledge_gap_count,
        "prohibited_document_count": prohibited_count,
        "mean_documents_per_task": document_count / len(records) if records else 0.0,
        "mean_injected_characters": (
            statistics.mean(
                record["knowledge_injected_characters"] for record in records
            ) if records else 0.0
        ),
        "max_injected_characters": max(
            (record["knowledge_injected_characters"] for record in records),
            default=0,
        ),
        "android_document_ratio": android_count / document_count if document_count else 0.0,
        "unmapped_document_ratio": unmapped_count / document_count if document_count else 0.0,
        "evaluation_document_count": sum(
            record["evaluation_document_count"] for record in records
        ),
        "direct_result_count": sum(record["direct_result_count"] for record in records),
        "vector_scored_result_count": sum(
            record["vector_scored_result_count"] for record in records
        ),
        "dense_backends": dict(Counter(record["dense_backend"] for record in records)),
    }
    thresholds = {
        "routing_hit_at_4_at_least_95_percent": summary["routing_hit_at_4"] >= 0.95,
        "mrr_at_least_0_75": summary["mean_reciprocal_rank"] >= 0.75,
        "actionable_hit_at_4_at_least_95_percent": (
            summary["actionable_hit_at_4"] >= 0.95
        ),
        "at_most_4_documents_per_task": summary["mean_documents_per_task"] <= 4.0,
        "mean_injected_characters_at_most_8000": summary["mean_injected_characters"] <= 8000,
        "android_document_ratio_100_percent": summary["android_document_ratio"] == 1.0,
        "no_evaluation_tool_documents": summary["evaluation_document_count"] == 0,
        "unmapped_document_ratio_at_most_25_percent": (
            summary["unmapped_document_ratio"] <= 0.25
        ),
        "vector_scoring_used": summary["vector_scored_result_count"] > 0,
        "no_prohibited_documents": summary["prohibited_document_count"] == 0,
        "no_knowledge_gap_for_evaluated_codes": (
            summary["knowledge_gap_code_pair_count"] == 0
        ),
    }
    summary["thresholds"] = thresholds
    summary["passed"] = all(thresholds.values())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    gold_payload, relevance_by_code = load_relevance_gold(args.gold)
    documents = load_documents()
    records = [
        evaluate_task(task, documents, relevance_by_code)
        for task in manifest["tasks"]
    ]
    summary = summarize(records)
    payload = {
        "schema_version": 1,
        "evaluation_id": "android_xml_rag_retrieval_v4_offline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_calls": 0,
        "source_manifest": str(args.manifest.resolve()),
        "relevance_gold": {
            "gold_id": gold_payload.get("gold_id"),
            "path": str(args.gold.resolve()),
            "sha256": hashlib.sha256(args.gold.read_bytes()).hexdigest(),
            "generated_from_retriever_routes": False,
        },
        "summary": summary,
        "tasks": records,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "retrieval_evaluation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Android XML RAG V4 Offline Retrieval Evaluation",
        "",
        "- Model calls: 0",
        f"- Tasks: {summary['task_count']}",
        f"- Independent relevance Hit@4: {summary['routing_hit_at_4']:.2%}",
        f"- MRR: {summary['mean_reciprocal_rank']:.4f}",
        f"- Actionable-document Hit@4: {summary['actionable_hit_at_4']:.2%}",
        f"- Knowledge-gap code pairs: {summary['knowledge_gap_code_pair_count']}",
        f"- Prohibited retrieved documents: {summary['prohibited_document_count']}",
        f"- Mean documents/task: {summary['mean_documents_per_task']:.2f}",
        f"- Mean injected characters: {summary['mean_injected_characters']:.0f}",
        f"- Android document ratio: {summary['android_document_ratio']:.2%}",
        f"- Evaluation-tool documents: {summary['evaluation_document_count']}",
        f"- Vector-scored results: {summary['vector_scored_result_count']}",
        f"- Gate passed: {'yes' if summary['passed'] else 'no'}",
        "",
        "| Gate | Passed |",
        "|---|---|",
    ]
    for name, passed in summary["thresholds"].items():
        lines.append(f"| `{name}` | {'yes' if passed else 'no'} |")
    lines.append("")
    (args.output / "retrieval_evaluation.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
