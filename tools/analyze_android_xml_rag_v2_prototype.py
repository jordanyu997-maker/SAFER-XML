#!/usr/bin/env python3
"""Compare frozen V1 retrieval with the dependency-light V2 prototype."""
import argparse
import csv
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = (
    ROOT
    / "experiments/android_xml_multimodel/runs/formal/deepseek_v4_pro/rep_01"
)
DEFAULT_OUTPUT = (
    ROOT / "experiments/android_xml_v2_design/rag_audit_v2_prototype"
)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.generate_android_xml import (  # noqa: E402
    issue_query,
    repairable_issues,
    retrieve_documents,
)
from tools.retrieval.build_rag_prompt import format_document  # noqa: E402
from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.retrieval.v2_hybrid import (  # noqa: E402
    eligible_for_android_xml,
    retrieve,
    retrieve_for_issues,
)


KS = (1, 3, 5)


def load_actionable_issues(run_root):
    reports = sorted(
        Path(run_root).glob("*/original/reports/android_xml_a11y_report.json")
    )
    by_app = {}
    for report in reports:
        payload = json.loads(report.read_text(encoding="utf-8"))
        by_app[report.parts[-4]] = repairable_issues(payload.get("issues", []))
    return reports, by_app


def ranking_metrics(doc_ids, relevant_ids):
    relevant = set(relevant_ids)
    metrics = {}
    for k in KS:
        top = doc_ids[:k]
        hits = [1 if doc_id in relevant else 0 for doc_id in top]
        matches = sum(hits)
        metrics[f"precision_at_{k}"] = matches / k
        metrics[f"recall_at_{k}"] = matches / len(relevant) if relevant else None
        dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
        ideal_hits = [1] * min(len(relevant), k)
        idcg = sum(
            hit / math.log2(index + 2)
            for index, hit in enumerate(ideal_hits)
        )
        metrics[f"ndcg_at_{k}"] = dcg / idcg if idcg else None
    first = next(
        (index for index, doc_id in enumerate(doc_ids, 1) if doc_id in relevant),
        None,
    )
    metrics["mrr"] = 1 / first if first else 0.0
    return metrics


def mean(rows, field):
    values = [row[field] for row in rows if row.get(field) is not None]
    return sum(values) / len(values) if values else None


def evaluate_issues(by_app, documents):
    rows = []
    for app_name, issues in sorted(by_app.items()):
        for issue in issues:
            query = issue_query(issue)
            started = time.perf_counter()
            v1_documents = retrieve_documents([issue], limit=16)
            v1_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            v2_results = retrieve(
                query,
                documents,
                related_doc_ids=issue.get("related_docs", ()),
                final_limit=3,
                direct_limit=2,
                candidate_limit=20,
            )
            v2_ms = (time.perf_counter() - started) * 1000
            v1_ids = [document.get("doc_id") for document in v1_documents]
            v2_ids = [result["doc_id"] for result in v2_results]
            relevant = issue.get("related_docs", [])
            row = {
                "app_name": app_name,
                "code": issue.get("code"),
                "component": issue.get("component") or issue.get("element"),
                "query": query,
                "silver_relevant_doc_ids": json.dumps(relevant, ensure_ascii=False),
                "v1_doc_ids": json.dumps(v1_ids, ensure_ascii=False),
                "v2_doc_ids": json.dumps(v2_ids, ensure_ascii=False),
                "v1_document_count": len(v1_documents),
                "v2_document_count": len(v2_results),
                "v1_injected_characters": sum(
                    len(format_document(document)) for document in v1_documents
                ),
                "v2_injected_characters": sum(
                    len(format_document(result["document"])) for result in v2_results
                ),
                "v1_latency_ms": v1_ms,
                "v2_latency_ms": v2_ms,
            }
            for method, ids in (("v1", v1_ids), ("v2", v2_ids)):
                for metric, value in ranking_metrics(ids, relevant).items():
                    row[f"{method}_{metric}"] = value
            rows.append(row)
    return rows


def app_prompt_summary(by_app, documents):
    rows = []
    v1_frequency = Counter()
    v2_frequency = Counter()
    for app_name, issues in sorted(by_app.items()):
        if not issues:
            continue
        started = time.perf_counter()
        v1 = retrieve_documents(issues, limit=16)
        v1_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        v2 = retrieve_for_issues(
            issues,
            documents,
            per_issue_limit=3,
            prompt_limit=6,
            direct_limit=2,
            candidate_limit=20,
            query_builder=issue_query,
        )
        v2_ms = (time.perf_counter() - started) * 1000
        v1_ids = [document.get("doc_id") for document in v1]
        v2_ids = [result["doc_id"] for result in v2]
        v1_frequency.update(v1_ids)
        v2_frequency.update(v2_ids)
        rows.append({
            "app_name": app_name,
            "issue_count": len(issues),
            "v1_document_count": len(v1),
            "v2_document_count": len(v2),
            "v1_injected_characters": sum(len(format_document(item)) for item in v1),
            "v2_injected_characters": sum(
                len(format_document(item["document"])) for item in v2
            ),
            "v1_latency_ms": v1_ms,
            "v2_latency_ms": v2_ms,
        })
    return rows, v1_frequency, v2_frequency


def aggregate(rows, prefix):
    return {
        "mean_mrr": mean(rows, f"{prefix}_mrr"),
        **{
            f"mean_{metric}_at_{k}": mean(rows, f"{prefix}_{metric}_at_{k}")
            for metric in ("precision", "recall", "ndcg")
            for k in KS
        },
        "mean_document_count": mean(rows, f"{prefix}_document_count"),
        "mean_injected_characters": mean(rows, f"{prefix}_injected_characters"),
        "mean_latency_ms": mean(rows, f"{prefix}_latency_ms"),
    }


def write_outputs(output, issue_rows, app_rows, summary):
    output.mkdir(parents=True, exist_ok=True)
    issue_path = output / "issue_retrieval_rows.csv"
    with issue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(issue_rows[0]))
        writer.writeheader()
        writer.writerows(issue_rows)
    app_path = output / "app_prompt_rows.csv"
    with app_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(app_rows[0]))
        writer.writeheader()
        writer.writerows(app_rows)
    json_path = output / "rag_audit.json"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    v1 = summary["silver_reference_metrics"]["v1"]
    v2 = summary["silver_reference_metrics"]["v2"]
    app = summary["app_prompt_footprint"]
    md_path = output / "rag_audit.md"
    md_path.write_text(
        "\n".join([
            "# Android XML V2 Retrieval Prototype Audit",
            "",
            "This is an offline engineering audit. Detector `related_docs` are silver references, not expert relevance judgments.",
            "",
            "| Method | MRR | Recall@3 | Precision@3 | nDCG@3 | Mean docs/issue |",
            "|---|---:|---:|---:|---:|---:|",
            f"| V1 | {v1['mean_mrr']:.3f} | {v1['mean_recall_at_3']:.3f} | {v1['mean_precision_at_3']:.3f} | {v1['mean_ndcg_at_3']:.3f} | {v1['mean_document_count']:.2f} |",
            f"| V2 metadata + BM25 | {v2['mean_mrr']:.3f} | {v2['mean_recall_at_3']:.3f} | {v2['mean_precision_at_3']:.3f} | {v2['mean_ndcg_at_3']:.3f} | {v2['mean_document_count']:.2f} |",
            "",
            "## Prompt footprint",
            "",
            f"- Active Apps: {app['active_app_count']}",
            f"- Mean V1 documents per App prompt: {app['v1_mean_document_count']:.2f}",
            f"- Mean V2 documents per App prompt: {app['v2_mean_document_count']:.2f}",
            f"- Mean V1 injected characters: {app['v1_mean_injected_characters']:.0f}",
            f"- Mean V2 injected characters: {app['v2_mean_injected_characters']:.0f}",
            f"- Character reduction: {app['injected_character_reduction']:.1%}",
            "",
            "## Boundary",
            "",
            "- Dense retrieval was not evaluated because no frozen embedding backend is installed.",
            "- Better silver-reference ranking only demonstrates compactness and mapping preservation.",
            "- Human relevance labels are required before claiming that V2 RAG is more relevant.",
            "",
        ]),
        encoding="utf-8",
    )
    return issue_path, app_path, json_path, md_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    reports, by_app = load_actionable_issues(args.run_root)
    if len(reports) != 40:
        raise SystemExit(f"Expected 40 frozen App reports, found {len(reports)}")
    documents = load_documents()
    issue_rows = evaluate_issues(by_app, documents)
    app_rows, v1_frequency, v2_frequency = app_prompt_summary(by_app, documents)
    v1_chars = mean(app_rows, "v1_injected_characters")
    v2_chars = mean(app_rows, "v2_injected_characters")
    active_apps = len(app_rows)
    summary = {
        "schema_version": 1,
        "analysis_id": "android_xml_rag_v2_dependency_light_prototype",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label_status": "detector related_docs silver references; expert labels pending",
        "dense_backend": {
            "enabled": False,
            "status": "not_installed_and_not_claimed",
        },
        "dataset": {
            "app_count": len(reports),
            "active_app_count": active_apps,
            "actionable_issue_count": len(issue_rows),
            "knowledge_document_count": len(documents),
            "android_xml_eligible_document_count": sum(
                eligible_for_android_xml(document) for document in documents
            ),
        },
        "silver_reference_metrics": {
            "v1": aggregate(issue_rows, "v1"),
            "v2": aggregate(issue_rows, "v2"),
        },
        "app_prompt_footprint": {
            "active_app_count": active_apps,
            "v1_mean_document_count": mean(app_rows, "v1_document_count"),
            "v2_mean_document_count": mean(app_rows, "v2_document_count"),
            "v1_mean_injected_characters": v1_chars,
            "v2_mean_injected_characters": v2_chars,
            "injected_character_reduction": (
                (v1_chars - v2_chars) / v1_chars if v1_chars else None
            ),
            "v1_documents_in_75_percent_of_active_apps": sum(
                count >= active_apps * 0.75 for count in v1_frequency.values()
            ),
            "v2_documents_in_75_percent_of_active_apps": sum(
                count >= active_apps * 0.75 for count in v2_frequency.values()
            ),
        },
        "interpretation_boundary": [
            "Silver references test mapping retention, not expert relevance.",
            "No dense or hybrid advantage is claimed without a frozen dense backend.",
            "No model repair outcomes were generated by this audit.",
        ],
    }
    paths = write_outputs(args.output, issue_rows, app_rows, summary)
    print(json.dumps({
        "apps": len(reports),
        "actionable_issues": len(issue_rows),
        "outputs": [path.relative_to(ROOT).as_posix() for path in paths],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
