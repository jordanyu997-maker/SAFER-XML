#!/usr/bin/env python3
"""Audit the frozen V1 Android XML retrieval pipeline without model calls."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = (
    ROOT
    / "experiments/android_xml_multimodel/runs/formal/deepseek_v4_pro/rep_01"
)
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_design/rag_audit_v1"
KNOWLEDGE_PATH = ROOT / "knowledge/rag/knowledge_documents.json"

import sys

sys.path.insert(0, str(ROOT))

from tools.generate_android_xml import (  # noqa: E402
    issue_query,
    repairable_issues,
    retrieve_documents,
)
from tools.retrieval.search_documents import load_documents, search  # noqa: E402


KS = (1, 3, 5, 16)
ROW_FIELDS = [
    "app_name",
    "code",
    "component",
    "selector",
    "related_doc_ids",
    "query",
    "keyword_doc_ids",
    "keyword_scores",
    "pipeline_doc_ids",
    "keyword_mrr",
    "pipeline_mrr",
] + [
    f"{method}_{metric}_at_{k}"
    for method in ("keyword", "pipeline")
    for metric in ("precision", "recall")
    for k in KS
]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ranking_metrics(doc_ids, relevant_ids):
    relevant = set(relevant_ids)
    metrics = {}
    for k in KS:
        top = doc_ids[:k]
        matches = len(relevant.intersection(top))
        metrics[f"precision_at_{k}"] = matches / k
        metrics[f"recall_at_{k}"] = (
            matches / len(relevant) if relevant else None
        )
    first = next(
        (index for index, doc_id in enumerate(doc_ids, 1) if doc_id in relevant),
        None,
    )
    metrics["mrr"] = 1 / first if first else 0.0
    return metrics


def load_actionable_issues(run_root):
    reports = sorted(
        Path(run_root).glob("*/original/reports/android_xml_a11y_report.json")
    )
    by_app = {}
    for report in reports:
        payload = json.loads(report.read_text(encoding="utf-8"))
        by_app[report.parts[-4]] = repairable_issues(payload.get("issues", []))
    return reports, by_app


def issue_rows(by_app):
    rows = []
    for app_name, issues in sorted(by_app.items()):
        for issue in issues:
            query = issue_query(issue)
            keyword = search(query, limit=50)
            keyword_ids = [document.get("doc_id") for _, document in keyword]
            keyword_scores = [score for score, _ in keyword]
            pipeline = retrieve_documents([issue], limit=16)
            pipeline_ids = [document.get("doc_id") for document in pipeline]
            relevant = issue.get("related_docs", [])
            keyword_metrics = ranking_metrics(keyword_ids, relevant)
            pipeline_metrics = ranking_metrics(pipeline_ids, relevant)
            row = {
                "app_name": app_name,
                "code": issue.get("code"),
                "component": issue.get("component") or issue.get("element"),
                "selector": issue.get("selector"),
                "related_doc_ids": json.dumps(relevant, ensure_ascii=False),
                "query": query,
                "keyword_doc_ids": json.dumps(keyword_ids[:16], ensure_ascii=False),
                "keyword_scores": json.dumps(keyword_scores[:16]),
                "pipeline_doc_ids": json.dumps(pipeline_ids, ensure_ascii=False),
                "keyword_mrr": keyword_metrics["mrr"],
                "pipeline_mrr": pipeline_metrics["mrr"],
            }
            for method, metrics in (
                ("keyword", keyword_metrics),
                ("pipeline", pipeline_metrics),
            ):
                for k in KS:
                    row[f"{method}_precision_at_{k}"] = metrics[
                        f"precision_at_{k}"
                    ]
                    row[f"{method}_recall_at_{k}"] = metrics[
                        f"recall_at_{k}"
                    ]
            rows.append(row)
    return rows


def mean(rows, field):
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return sum(values) / len(values) if values else None


def app_retrieval_summary(by_app):
    document_frequency = Counter()
    type_frequency = Counter()
    retrieved_counts = Counter()
    for issues in by_app.values():
        if not issues:
            continue
        documents = retrieve_documents(issues, limit=16)
        retrieved_counts[len(documents)] += 1
        for document in documents:
            document_frequency[document.get("doc_id")] += 1
            type_frequency[document.get("doc_type")] += 1
    return document_frequency, type_frequency, retrieved_counts


def prompt_summary(run_root):
    prompt_count = 0
    total_chars = 0
    rag_chars = 0
    for path in Path(run_root).glob(
        "*/proposed/reports/repair_prompt_round_1_attempt_1.txt"
    ):
        text = path.read_text(encoding="utf-8")
        prompt_count += 1
        total_chars += len(text)
        try:
            start = text.index("Retrieved knowledge:")
            end = text.index("Detected Android XML accessibility issues:")
        except ValueError:
            continue
        rag_chars += end - start
    return {
        "prompt_count": prompt_count,
        "total_chars": total_chars,
        "rag_chars": rag_chars,
        "rag_char_share": rag_chars / total_chars if total_chars else None,
    }


def build_summary(reports, by_app, rows, run_root):
    documents = load_documents()
    document_frequency, type_frequency, retrieved_counts = app_retrieval_summary(
        by_app
    )
    active_apps = sum(bool(issues) for issues in by_app.values())
    issue_codes = Counter(row["code"] for row in rows)
    related_counts = Counter(
        len(json.loads(row["related_doc_ids"])) for row in rows
    )
    aggregate = {}
    for method in ("keyword", "pipeline"):
        aggregate[method] = {
            "mean_mrr": mean(rows, f"{method}_mrr"),
            **{
                f"mean_{metric}_at_{k}": mean(
                    rows, f"{method}_{metric}_at_{k}"
                )
                for metric in ("precision", "recall")
                for k in KS
            },
        }
    common_threshold = active_apps * 0.75
    return {
        "schema_version": 1,
        "analysis_id": "android_xml_rag_v1_offline_audit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label_status": (
            "silver references from detector related_docs; expert relevance "
            "judgments are still required"
        ),
        "knowledge_corpus": {
            "path": KNOWLEDGE_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(KNOWLEDGE_PATH),
            "document_count": len(documents),
            "document_type_counts": dict(Counter(
                document.get("doc_type") for document in documents
            )),
            "documents_with_platform_field": sum(
                bool(document.get("platform")) for document in documents
            ),
        },
        "dataset": {
            "app_count": len(reports),
            "apps_with_actionable_issues": active_apps,
            "actionable_issue_count": len(rows),
            "actionable_issue_codes": dict(issue_codes),
            "related_docs_per_issue": dict(related_counts),
        },
        "aggregate_metrics": aggregate,
        "app_level_retrieval": {
            "retrieved_document_counts": dict(retrieved_counts),
            "retrieved_document_type_counts": dict(type_frequency),
            "documents_in_at_least_75_percent_of_active_apps": sum(
                count >= common_threshold for count in document_frequency.values()
            ),
            "most_frequent_documents": [
                {"doc_id": doc_id, "app_count": count}
                for doc_id, count in document_frequency.most_common(20)
            ],
        },
        "prompt_footprint": prompt_summary(run_root),
    }


def write_outputs(output, rows, summary):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "issue_retrieval_rows.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    json_path = output / "rag_audit.json"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    dataset = summary["dataset"]
    keyword = summary["aggregate_metrics"]["keyword"]
    pipeline = summary["aggregate_metrics"]["pipeline"]
    footprint = summary["prompt_footprint"]
    lines = [
        "# Android XML V1 RAG Offline Audit",
        "",
        f"- Frozen Apps: {dataset['app_count']}",
        f"- Apps with actionable issues: {dataset['apps_with_actionable_issues']}",
        f"- Actionable issue instances: {dataset['actionable_issue_count']}",
        f"- Actionable issue codes: {len(dataset['actionable_issue_codes'])}",
        f"- Knowledge documents: {summary['knowledge_corpus']['document_count']}",
        f"- Documents with platform metadata: {summary['knowledge_corpus']['documents_with_platform_field']}",
        "",
        "## Silver-reference retrieval",
        "",
        "The detector's `related_docs` values are silver references, not expert relevance labels.",
        "",
        "| Retriever | MRR | Recall@3 | Recall@5 | Precision@16 |",
        "|---|---:|---:|---:|---:|",
        f"| Keyword ranking | {keyword['mean_mrr']:.3f} | {keyword['mean_recall_at_3']:.3f} | {keyword['mean_recall_at_5']:.3f} | {keyword['mean_precision_at_16']:.3f} |",
        f"| V1 pipeline | {pipeline['mean_mrr']:.3f} | {pipeline['mean_recall_at_3']:.3f} | {pipeline['mean_recall_at_5']:.3f} | {pipeline['mean_precision_at_16']:.3f} |",
        "",
        "## Diagnostic findings",
        "",
        f"- Every active App was padded to 16 documents: {summary['app_level_retrieval']['retrieved_document_counts']}.",
        f"- Documents present in at least 75% of active Apps: {summary['app_level_retrieval']['documents_in_at_least_75_percent_of_active_apps']}.",
        f"- RAG prompt character share: {footprint['rag_char_share']:.1%}.",
        "- Direct rule mappings guarantee silver-reference recall but do not establish that the remaining retrieved documents are relevant.",
        "- V2 must add expert relevance judgments before using Precision@K or nDCG as formal evidence.",
        "",
    ]
    md_path = output / "rag_audit.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path, json_path, md_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    reports, by_app = load_actionable_issues(args.run_root)
    if len(reports) != 40:
        raise SystemExit(f"Expected 40 frozen App reports, found {len(reports)}")
    rows = issue_rows(by_app)
    summary = build_summary(reports, by_app, rows, args.run_root)
    csv_path, json_path, md_path = write_outputs(args.output, rows, summary)
    print(json.dumps({
        "apps": len(reports),
        "actionable_issues": len(rows),
        "csv": csv_path.relative_to(ROOT).as_posix(),
        "json": json_path.relative_to(ROOT).as_posix(),
        "report": md_path.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
