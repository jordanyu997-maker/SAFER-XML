#!/usr/bin/env python3
"""Validate blinded retrieval labels and compare frozen V1/V2 rankings."""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLIND = (
    ROOT
    / "experiments/android_xml_v2_design/retrieval_annotation/relevance_annotation_blinded.csv"
)
DEFAULT_PROVENANCE = (
    ROOT
    / "experiments/android_xml_v2_design/retrieval_annotation/relevance_annotation.csv"
)
DEFAULT_OUTPUT = (
    ROOT / "experiments/android_xml_v2_design/retrieval_annotation/retrieval_evaluation.json"
)


def load_rows(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_labels(rows):
    labels = {}
    invalid = []
    incomplete = []
    for row in rows:
        key = (row.get("query_id"), row.get("doc_id"))
        grade = row.get("relevance_grade_0_1_2", "").strip()
        actionable = row.get("directly_actionable_yes_no", "").strip().lower()
        assessor = row.get("assessor_id", "").strip()
        if not grade or not actionable or not assessor:
            incomplete.append(key)
            continue
        if grade not in {"0", "1", "2"} or actionable not in {"yes", "no"}:
            invalid.append(key)
            continue
        labels[key] = {
            "grade": int(grade),
            "actionable": actionable == "yes",
            "assessor_id": assessor,
        }
    return labels, incomplete, invalid


def ranked_metrics(query_rows, labels, rank_field):
    rankings = []
    for row in query_rows:
        rank = row.get(rank_field, "").strip()
        if rank:
            rankings.append((int(rank), labels[(row["query_id"], row["doc_id"])]["grade"]))
    rankings.sort()
    grades = [grade for _, grade in rankings]
    relevant_total = sum(
        labels[(row["query_id"], row["doc_id"])]["grade"] > 0
        for row in query_rows
    )
    metrics = {}
    for k in (1, 3, 5):
        top = grades[:k]
        relevant = sum(grade > 0 for grade in top)
        metrics[f"precision_at_{k}"] = relevant / k
        metrics[f"recall_at_{k}"] = relevant / relevant_total if relevant_total else None
        dcg = sum(
            (2 ** grade - 1) / math.log2(index + 2)
            for index, grade in enumerate(top)
        )
        ideal = sorted(
            (
                label["grade"]
                for key, label in labels.items()
                if key[0] == query_rows[0]["query_id"]
            ),
            reverse=True,
        )[:k]
        idcg = sum(
            (2 ** grade - 1) / math.log2(index + 2)
            for index, grade in enumerate(ideal)
        )
        metrics[f"ndcg_at_{k}"] = dcg / idcg if idcg else None
    first = next((index for index, grade in enumerate(grades, 1) if grade > 0), None)
    metrics["mrr"] = 1 / first if first else 0.0
    return metrics


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def aggregate(provenance, labels, rank_field):
    by_query = defaultdict(list)
    for row in provenance:
        by_query[row["query_id"]].append(row)
    query_metrics = [
        ranked_metrics(rows, labels, rank_field)
        for _, rows in sorted(by_query.items())
    ]
    return {
        metric: mean([row[metric] for row in query_metrics])
        for metric in query_metrics[0]
    }


def compare_retrievers(provenance, labels):
    v1 = aggregate(provenance, labels, "v1_rank")
    v2 = aggregate(provenance, labels, "v2_rank")
    gate = (
        v2["precision_at_3"] >= v1["precision_at_3"]
        and v2["ndcg_at_5"] >= v1["ndcg_at_5"]
    )
    return {
        "query_count": len({row["query_id"] for row in provenance}),
        "metrics": {
            "v1_keyword": v1,
            "v2_metadata_bm25": v2,
        },
        "execution_gate": {
            "precision_at_3_non_inferior": (
                v2["precision_at_3"] >= v1["precision_at_3"]
            ),
            "ndcg_at_5_non_inferior": v2["ndcg_at_5"] >= v1["ndcg_at_5"],
        },
        "execution_gate_passed": gate,
    }


def stratified_comparisons(provenance, labels):
    by_stratum = defaultdict(list)
    for row in provenance:
        stratum = row.get("stratum", "").strip()
        if stratum:
            by_stratum[stratum].append(row)
    return {
        stratum: compare_retrievers(rows, labels)
        for stratum, rows in sorted(by_stratum.items())
    }


def metric_text(value):
    return "n/a" if value is None else f"{value:.3f}"


def metric_table(v1, v2):
    return [
        "| Retriever | Precision@3 | Recall@3 | nDCG@5 | MRR |",
        "|---|---:|---:|---:|---:|",
        "| V1 keyword | "
        f"{metric_text(v1['precision_at_3'])} | "
        f"{metric_text(v1['recall_at_3'])} | "
        f"{metric_text(v1['ndcg_at_5'])} | "
        f"{metric_text(v1['mrr'])} |",
        "| V2 metadata + BM25 | "
        f"{metric_text(v2['precision_at_3'])} | "
        f"{metric_text(v2['recall_at_3'])} | "
        f"{metric_text(v2['ndcg_at_5'])} | "
        f"{metric_text(v2['mrr'])} |",
    ]


def write_markdown(path, result):
    if result["status"] != "complete":
        text = "\n".join([
            "# Retrieval Label Evaluation",
            "",
            f"Status: `{result['status']}`",
            "",
            f"- Completed pairs: {result['completed_pair_count']} / {result['pair_count']}",
            f"- Incomplete pairs: {result['incomplete_pair_count']}",
            f"- Invalid pairs: {result['invalid_pair_count']}",
            "- Model execution remains disabled.",
            "",
        ])
    else:
        v1 = result["metrics"]["v1_keyword"]
        v2 = result["metrics"]["v2_metadata_bm25"]
        lines = [
            "# Retrieval Label Evaluation",
            "",
            f"Gate: `{'passed' if result['execution_gate_passed'] else 'failed'}`",
            "",
            *metric_table(v1, v2),
            "",
        ]
        for stratum, comparison in result.get("metrics_by_stratum", {}).items():
            stratum_v1 = comparison["metrics"]["v1_keyword"]
            stratum_v2 = comparison["metrics"]["v2_metadata_bm25"]
            lines.extend([
                f"## Stratum: {stratum}",
                "",
                f"Queries: {comparison['query_count']}. Gate: "
                f"`{'passed' if comparison['execution_gate_passed'] else 'failed'}`.",
                "",
                *metric_table(stratum_v1, stratum_v2),
                "",
            ])
        lines.extend([
            "The gate requires V2 Precision@3 and nDCG@5 to be no lower than V1 overall and, when present, in every declared stratum. Prompt compactness is reported separately and is not used to manufacture a relevance gain.",
            "",
        ])
        text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blinded", type=Path, default=DEFAULT_BLIND)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    blind = load_rows(args.blinded)
    provenance = load_rows(args.provenance)
    labels, incomplete, invalid = parse_labels(blind)
    provenance_keys = {(row["query_id"], row["doc_id"]) for row in provenance}
    blind_keys = {(row["query_id"], row["doc_id"]) for row in blind}
    if provenance_keys != blind_keys:
        raise SystemExit("Blinded and provenance query-document pairs do not match")
    complete = not incomplete and not invalid and len(labels) == len(blind)
    result = {
        "schema_version": 1,
        "evaluation_id": "android_xml_v2_blinded_retrieval_relevance",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if complete else "incomplete",
        "pair_count": len(blind),
        "completed_pair_count": len(labels),
        "incomplete_pair_count": len(incomplete),
        "invalid_pair_count": len(invalid),
        "execution_gate_passed": False,
    }
    if complete:
        comparison = compare_retrievers(provenance, labels)
        by_stratum = stratified_comparisons(provenance, labels)
        gate = comparison["execution_gate_passed"] and all(
            item["execution_gate_passed"] for item in by_stratum.values()
        )
        result.update({
            "metrics": comparison["metrics"],
            "metrics_by_stratum": by_stratum,
            "execution_gate": comparison["execution_gate"] | {
                "all_declared_strata_non_inferior": all(
                    item["execution_gate_passed"] for item in by_stratum.values()
                ),
            },
            "execution_gate_passed": gate,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.output.with_suffix(".md"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_complete and not complete:
        raise SystemExit(2)
    if args.require_complete and not result["execution_gate_passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
