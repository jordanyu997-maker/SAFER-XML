#!/usr/bin/env python3
"""Build a detector-output-only relevance annotation set for V1 and V2 RAG."""
import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = (
    ROOT
    / "experiments/android_xml_multimodel/runs/formal/deepseek_v4_pro/rep_01"
)
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_design/retrieval_annotation"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.generate_android_xml import issue_query  # noqa: E402
from tools.retrieval.search_documents import load_documents, search  # noqa: E402
from tools.retrieval.v2_hybrid import infer_metadata, retrieve  # noqa: E402


FIELDS = [
    "query_id",
    "app_name",
    "issue_code",
    "severity",
    "repairability",
    "component",
    "selector",
    "query",
    "doc_id",
    "document_title",
    "document_summary",
    "source_url",
    "platforms",
    "frameworks",
    "v1_rank",
    "v2_rank",
    "detector_direct_mapping",
    "relevance_grade_0_1_2",
    "directly_actionable_yes_no",
    "assessor_id",
    "notes",
]
BLIND_FIELDS = [
    field
    for field in FIELDS
    if field not in {"v1_rank", "v2_rank", "detector_direct_mapping"}
]


def load_issues(run_root):
    rows = []
    for report in sorted(
        Path(run_root).glob("*/original/reports/android_xml_a11y_report.json")
    ):
        payload = json.loads(report.read_text(encoding="utf-8"))
        app_name = report.parts[-4]
        for issue in payload.get("issues", []):
            rows.append((app_name, issue))
    return rows


def stratified_sample(issue_rows, per_code):
    by_code = defaultdict(list)
    for app_name, issue in issue_rows:
        by_code[issue.get("code", "UNKNOWN")].append((app_name, issue))
    sampled = []
    for code, rows in sorted(by_code.items()):
        seen_apps = set()
        for app_name, issue in sorted(
            rows,
            key=lambda item: (
                item[0].lower(),
                item[1].get("selector", ""),
                item[1].get("id", ""),
            ),
        ):
            if app_name in seen_apps and len(seen_apps) < per_code:
                continue
            sampled.append((app_name, issue))
            seen_apps.add(app_name)
            if len(seen_apps) >= per_code:
                break
    return sampled


def source_url(document):
    source = document.get("source", {})
    return (
        source.get("understanding_url")
        or source.get("standard_url")
        or "local"
    )


def build_rows(sampled, documents, candidate_limit):
    rows = []
    query_manifest = []
    for index, (app_name, issue) in enumerate(sampled, 1):
        query_id = f"Q{index:03d}"
        query = issue_query(issue)
        v1 = [document for _, document in search(query, candidate_limit)]
        v2 = [
            result["document"]
            for result in retrieve(
                query,
                documents,
                related_doc_ids=issue.get("related_docs", ()),
                final_limit=candidate_limit,
                direct_limit=2,
                candidate_limit=20,
            )
        ]
        v1_ranks = {document.get("doc_id"): rank for rank, document in enumerate(v1, 1)}
        v2_ranks = {document.get("doc_id"): rank for rank, document in enumerate(v2, 1)}
        by_id = {
            document.get("doc_id"): document
            for document in v1 + v2
            if document.get("doc_id")
        }
        candidate_ids = sorted(
            by_id,
            key=lambda doc_id: (
                min(v1_ranks.get(doc_id, 999), v2_ranks.get(doc_id, 999)),
                doc_id,
            ),
        )
        query_manifest.append({
            "query_id": query_id,
            "app_name": app_name,
            "issue_id": issue.get("id"),
            "issue_code": issue.get("code"),
            "severity": issue.get("severity", "error"),
            "repairability": issue.get("repairability"),
            "component": issue.get("component") or issue.get("element"),
            "selector": issue.get("selector"),
            "query": query,
            "candidate_count": len(candidate_ids),
        })
        for doc_id in candidate_ids:
            document = by_id[doc_id]
            metadata = infer_metadata(document)
            content = document.get("content", {})
            source = document.get("source", {})
            rows.append({
                "query_id": query_id,
                "app_name": app_name,
                "issue_code": issue.get("code"),
                "severity": issue.get("severity", "error"),
                "repairability": issue.get("repairability"),
                "component": issue.get("component") or issue.get("element"),
                "selector": issue.get("selector"),
                "query": query,
                "doc_id": doc_id,
                "document_title": source.get("title_en") or source.get("title_zh"),
                "document_summary": content.get("summary_en") or content.get("summary_zh"),
                "source_url": source_url(document),
                "platforms": ";".join(metadata["platforms"]),
                "frameworks": ";".join(metadata["frameworks"]),
                "v1_rank": v1_ranks.get(doc_id, ""),
                "v2_rank": v2_ranks.get(doc_id, ""),
                "detector_direct_mapping": (
                    "yes" if doc_id in issue.get("related_docs", []) else "no"
                ),
                "relevance_grade_0_1_2": "",
                "directly_actionable_yes_no": "",
                "assessor_id": "",
                "notes": "",
            })
    return rows, query_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-code", type=int, default=2)
    parser.add_argument("--candidate-limit", type=int, default=5)
    args = parser.parse_args()
    issue_rows = load_issues(args.run_root)
    sampled = stratified_sample(issue_rows, args.per_code)
    documents = load_documents()
    rows, queries = build_rows(sampled, documents, args.candidate_limit)
    args.output.mkdir(parents=True, exist_ok=True)
    csv_path = args.output / "relevance_annotation.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    blind_path = args.output / "relevance_annotation_blinded.csv"
    blind_rows = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"android-xml-v2-blind|{row['query_id']}|{row['doc_id']}".encode("utf-8")
        ).hexdigest(),
    )
    with blind_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BLIND_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: row[field] for field in BLIND_FIELDS}
            for row in blind_rows
        )
    manifest = {
        "schema_version": 1,
        "dataset_id": "android_xml_v2_retrieval_annotation_draft",
        "status": "unlabeled",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_boundary": "frozen V1 original detector reports only",
        "sampling": {
            "strategy": "up to two real issues per observed code from distinct Apps",
            "per_code": args.per_code,
            "candidate_limit_per_retriever": args.candidate_limit,
            "outcomes_used": False,
        },
        "issue_code_count": len({query["issue_code"] for query in queries}),
        "query_count": len(queries),
        "candidate_pair_count": len(rows),
        "annotation_file": blind_path.relative_to(ROOT).as_posix(),
        "provenance_file": csv_path.relative_to(ROOT).as_posix(),
        "queries": queries,
    }
    manifest_path = args.output / "annotation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    guide_path = args.output / "ANNOTATION_GUIDE.md"
    guide_path.write_text(
        "\n".join([
            "# Retrieval Relevance Annotation Guide",
            "",
            "Judge each query-document pair without looking at model repair outputs or experiment metrics.",
            "",
            "- `0`: irrelevant or wrong platform/framework.",
            "- `1`: related background, but not sufficient to guide this repair.",
            "- `2`: directly relevant and specific enough to guide the detected issue.",
            "- `directly_actionable_yes_no`: `yes` only when the document gives an applicable Android XML decision or repair constraint.",
            "- Use a stable anonymous `assessor_id`; explain borderline cases in `notes`.",
            "",
            "Annotate `relevance_annotation_blinded.csv`; it omits retriever ranks and detector mappings and uses rank-independent row ordering.",
            "Do not open `relevance_annotation.csv` until the blinded labels have been finalized; that file is retained only for later metric calculation.",
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({
        "issue_codes": manifest["issue_code_count"],
        "queries": len(queries),
        "pairs": len(rows),
        "blinded_csv": blind_path.relative_to(ROOT).as_posix(),
        "provenance_csv": csv_path.relative_to(ROOT).as_posix(),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "guide": guide_path.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
