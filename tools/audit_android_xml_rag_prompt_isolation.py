#!/usr/bin/env python3
"""Audit the isolated RAG prompt contract on every selected pilot screen."""
import argparse
import csv
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
DEFAULT_SCREENS = (
    ROOT
    / "experiments/android_xml_rag_contribution/pilot_dataset/pilot_screens.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_rag_contribution/prompt_isolation_audit"
)

sys.path.insert(0, str(ROOT))

from tools.android_xml_rag_prompt_contract import (  # noqa: E402
    audit_prompt_pair,
    build_prompt_pair,
)
from tools.evaluation.android_xml_a11y_check import all_attrs  # noqa: E402
from tools.generate_android_xml import selector_target_element  # noqa: E402
from tools.retrieval.search_documents import load_documents  # noqa: E402


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_true(value):
    return str(value).strip().casefold() in {"1", "true", "yes"}


def find_res_root(path):
    for parent in (Path(path), *Path(path).parents):
        if parent.name == "res":
            return parent
    raise ValueError(f"No res directory for {path}")


def issue_from_row(row, source_path):
    file_path = (Path(source_path) / row["issue_layout_path"]).resolve()
    text = file_path.read_text(encoding="utf-8")
    element = selector_target_element(text, row["selector"])
    return {
        "id": f"{row['code']}:{file_path.name}:{row['selector']}",
        "code": row["code"],
        "severity": row["severity"],
        "repairability": row["repairability"],
        "component": row["component"],
        "element": element.tag,
        "selector": row["selector"],
        "file": str(file_path),
        "attributes": all_attrs(element),
        "message": row["message"],
        "repair_query": "",
        "fix_hint": "",
        "related_docs": [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
    parser.add_argument("--screens", type=Path, default=DEFAULT_SCREENS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    issue_rows = [row for row in read_csv(args.issues) if is_true(row["actionable"])]
    screen_rows = read_csv(args.screens)
    screens = {
        (row["app_name"], row["screen_path"]): row for row in screen_rows
    }
    grouped = defaultdict(list)
    for row in issue_rows:
        grouped[(row["app_name"], row["screen_path"])].append(row)

    documents = load_documents()
    records = []
    all_failures = []
    for key in sorted(grouped):
        screen = screens[key]
        issues = [
            issue_from_row(row, screen["source_path"])
            for row in grouped[key]
        ]
        res_roots = {find_res_root(issue["file"]) for issue in issues}
        if len(res_roots) != 1:
            raise ValueError(f"Screen spans multiple res roots: {key}")
        res_dir = res_roots.pop()
        pair = build_prompt_pair(issues, res_dir, documents)
        audit = audit_prompt_pair(pair, issues)
        leaks = []
        for field in ("message", "repair_query", "fix_hint"):
            for issue in issues:
                value = str(issue.get(field, "")).strip()
                if value and (
                    value in pair["no_rag"] or value in pair["rag"]
                ):
                    leaks.append(field)
        if leaks:
            audit["passed"] = False
            audit["failures"].append(
                "solution_bearing_fields_in_prompt:" + ",".join(sorted(set(leaks)))
            )
        all_failures.extend(
            f"{key[0]}:{key[1]}:{failure}" for failure in audit["failures"]
        )
        records.append({
            "app_name": key[0],
            "screen_path": key[1],
            "issue_count": len(issues),
            "issue_codes": sorted({issue["code"] for issue in issues}),
            "res_dir": str(res_dir),
            "passed": audit["passed"],
            "failures": audit["failures"],
            "no_rag_prompt_characters": len(pair["no_rag"]),
            "rag_prompt_characters": len(pair["rag"]),
            "retrieved_document_count": pair["trace"]["knowledge_document_count"],
            "retrieved_document_ids": [
                item["doc_id"] for item in pair["trace"]["knowledge_documents"]
            ],
            "direct_detector_mapping_enabled": pair["trace"][
                "direct_detector_mapping_enabled"
            ],
            "app_context_retrieval_enabled": pair["trace"][
                "app_context_retrieval_enabled"
            ],
        })

    result = {
        "schema_version": 1,
        "audit_id": "android_xml_rag_prompt_isolation_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not all_failures else "failed",
        "model_execution": False,
        "model_calls": 0,
        "screen_count": len(records),
        "passed_screen_count": sum(record["passed"] for record in records),
        "failed_screen_count": sum(not record["passed"] for record in records),
        "conditions_differ_only_in_knowledge_block": not all_failures,
        "detector_direct_mapping_disabled_for_all": all(
            not record["direct_detector_mapping_enabled"] for record in records
        ),
        "app_context_retrieval_disabled_for_all": all(
            not record["app_context_retrieval_enabled"] for record in records
        ),
        "failures": all_failures,
        "screens": records,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    json_path = args.output / "prompt_isolation_audit.json"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Android XML RAG Prompt Isolation Audit",
        "",
        f"- Status: `{result['status']}`",
        f"- Screens audited: {result['screen_count']}",
        f"- Passed: {result['passed_screen_count']}",
        f"- Failed: {result['failed_screen_count']}",
        "- Model calls: 0",
        "- Detector direct document mappings: disabled",
        "- App-source context retrieval: disabled",
        "",
        "The No-RAG and RAG conditions use the same detector evidence, XML files, operation schema, and safety constraints. Their only permitted difference is the content inside the retrieved-knowledge block.",
        "",
    ]
    if all_failures:
        lines.extend(["## Failures", ""] + [f"- {item}" for item in all_failures])
    (args.output / "prompt_isolation_audit.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "screens": result["screen_count"],
        "passed": result["passed_screen_count"],
        "failed": result["failed_screen_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    if all_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
