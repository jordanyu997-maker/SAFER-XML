#!/usr/bin/env python3
"""Build a blinded retrieval annotation set for the RAG contribution pilot."""
import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ISSUES = (
    ROOT
    / "experiments/android_xml_rag_contribution/pilot_dataset/pilot_issues.csv"
)
DEFAULT_MANIFEST = (
    ROOT
    / "experiments/android_xml_rag_contribution/pilot_dataset/pilot_manifest.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_rag_contribution/pilot_dataset/retrieval_annotation"
)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.build_android_xml_retrieval_annotation import (  # noqa: E402
    BLIND_FIELDS,
    FIELDS,
    build_rows,
)
from tools.retrieval.search_documents import load_documents  # noqa: E402


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_true(value):
    return str(value).strip().casefold() in {"1", "true", "yes"}


def issue_from_row(row):
    return {
        "id": f"{row['code']}:{Path(row['issue_layout_path']).name}:{row['selector']}",
        "code": row["code"],
        "severity": row["severity"],
        "repairability": row["repairability"],
        "component": row["component"],
        "element": row["component"],
        "selector": row["selector"],
        "message": row["message"],
        "repair_query": "",
        "related_docs": [],
    }


def semantic_key(row):
    return (row["code"], row["component"], row["message"])


def unique_sensitive_rows(rows):
    selected = {}
    for row in sorted(
        rows,
        key=lambda item: (
            item["code"],
            item["app_name"].casefold(),
            item["screen_path"],
            item["selector"],
        ),
    ):
        if (
            row["rag_role"] == "rag_sensitive"
            and is_true(row["actionable"])
        ):
            selected.setdefault(semantic_key(row), row)
    return list(selected.values())


def matched_control_rows(rows, role_by_app, target):
    by_code = defaultdict(list)
    for row in rows:
        if (
            row["rag_role"] == "common_control"
            and is_true(row["actionable"])
            and role_by_app.get(row["app_name"]) == "common_negative_control"
        ):
            by_code[row["code"]].append(row)
    for code_rows in by_code.values():
        code_rows.sort(key=lambda item: (
            item["app_name"].casefold(),
            item["screen_path"],
            item["selector"],
        ))

    selected = []
    used_apps = set()
    codes = sorted(by_code)
    positions = defaultdict(int)
    while len(selected) < target:
        progress = False
        for code in codes:
            candidates = by_code[code]
            while positions[code] < len(candidates):
                row = candidates[positions[code]]
                positions[code] += 1
                if row["app_name"] in used_apps:
                    continue
                selected.append(row)
                used_apps.add(row["app_name"])
                progress = True
                break
            if len(selected) >= target:
                break
        if not progress:
            break
    if len(selected) != target:
        raise ValueError(f"Needed {target} matched controls, found {len(selected)}")
    return selected


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidate-limit", type=int, default=5)
    args = parser.parse_args()

    issue_rows = read_csv(args.issues)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    role_by_app = {
        app["app_name"]: app["pilot_role"] for app in manifest["apps"]
    }
    sensitive = unique_sensitive_rows(issue_rows)
    controls = matched_control_rows(issue_rows, role_by_app, len(sensitive))
    sampled_rows = sensitive + controls
    sampled = [
        (row["app_name"], issue_from_row(row)) for row in sampled_rows
    ]
    rows, queries = build_rows(
        sampled,
        load_documents(),
        args.candidate_limit,
    )
    stratum_by_query = {
        f"Q{index:03d}": (
            "rag_sensitive" if index <= len(sensitive) else "common_negative_control"
        )
        for index in range(1, len(sampled_rows) + 1)
    }
    for row in rows:
        row["stratum"] = stratum_by_query[row["query_id"]]
    for query in queries:
        query["stratum"] = stratum_by_query[query["query_id"]]

    fields = ["query_id", "stratum"] + FIELDS[1:]
    blind_fields = ["query_id", "stratum"] + BLIND_FIELDS[1:]
    args.output.mkdir(parents=True, exist_ok=True)
    provenance_path = args.output / "relevance_annotation.csv"
    write_csv(provenance_path, rows, fields)
    blinded_rows = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"android-xml-rag-pilot|{row['query_id']}|{row['doc_id']}".encode("utf-8")
        ).hexdigest(),
    )
    blind_path = args.output / "relevance_annotation_blinded.csv"
    write_csv(
        blind_path,
        [{field: row[field] for field in blind_fields} for row in blinded_rows],
        blind_fields,
    )

    annotation_manifest = {
        "schema_version": 1,
        "dataset_id": "android_xml_rag_contribution_pilot_retrieval_v1",
        "status": "unlabeled",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_boundary": "pilot detector findings only; no model outputs",
        "sampling": {
            "rag_sensitive_issue_instances": manifest["rag_sensitive_issue_count"],
            "rag_sensitive_unique_queries": len(sensitive),
            "matched_common_negative_control_queries": len(controls),
            "duplicate_repair_instances_collapsed_for_retrieval": (
                manifest["rag_sensitive_issue_count"] - len(sensitive)
            ),
            "candidate_limit_per_retriever": args.candidate_limit,
            "detector_direct_mapping_used": False,
            "model_outcomes_used": False,
        },
        "query_count": len(queries),
        "rag_sensitive_query_count": len(sensitive),
        "control_query_count": len(controls),
        "candidate_pair_count": len(rows),
        "annotation_file": blind_path.relative_to(ROOT).as_posix(),
        "provenance_file": provenance_path.relative_to(ROOT).as_posix(),
        "queries": queries,
    }
    (args.output / "annotation_manifest.json").write_text(
        json.dumps(annotation_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "ANNOTATION_GUIDE_ZH.md").write_text(
        "\n".join([
            "# RAG Pilot Retrieval Annotation",
            "",
            "Fill only `relevance_annotation_blinded.csv` before opening the provenance file.",
            "",
            "- `relevance_grade_0_1_2=0`: irrelevant, wrong platform, or unusable for the issue.",
            "- `relevance_grade_0_1_2=1`: related background, but not enough to guide an Android XML repair.",
            "- `relevance_grade_0_1_2=2`: directly relevant and specific enough to guide the repair decision.",
            "- `directly_actionable_yes_no=yes`: the document gives an applicable Android XML decision, constraint, or edit.",
            "- Use one anonymous `assessor_id` for every row.",
            "",
            "Judge the document against the query only. Do not inspect model outputs, repair rates, retriever ranks, or detector mappings.",
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({
        "queries": len(queries),
        "rag_sensitive_queries": len(sensitive),
        "control_queries": len(controls),
        "pairs": len(rows),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
