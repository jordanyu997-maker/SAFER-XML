#!/usr/bin/env python3
"""Run deterministic engineering checks for Android XML RAG retrieval."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_AUDIT = (
    ROOT
    / "experiments/android_xml_rag_contribution/prompt_isolation_audit"
    / "prompt_isolation_audit.json"
)
DEFAULT_OUTPUT = (
    ROOT / "experiments/android_xml_rag_contribution/rag_engineering_audit"
)

sys.path.insert(0, str(ROOT))

from tools.retrieval.search_documents import load_documents  # noqa: E402
from tools.retrieval.v2_hybrid import retrieve  # noqa: E402


TARGETS = {
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": {
        "evidence": "EditText android:id=@+id/edt_email android:hint=@string/email",
        "expected_doc_id": "android.fixcase.xml-email-inputtype-missing",
    },
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": {
        "evidence": "EditText android:hint=+1-555-12345 android:inputType=phone",
        "expected_doc_id": "android.fixcase.xml-format-example-only-hint",
    },
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": {
        "evidence": "ImageButton android:clickable=true android:focusable=false",
        "expected_doc_id": "android.fixcase.xml-standard-control-focusable-false",
    },
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": {
        "evidence": "EditText android:id=@+id/account_password android:hint=@string/password",
        "expected_doc_id": "android.fixcase.xml-password-inputtype-missing",
    },
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": {
        "evidence": "EditText android:id=@+id/contact_phone android:hint=@string/phone_number",
        "expected_doc_id": "android.fixcase.xml-phone-inputtype-missing",
    },
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": {
        "evidence": "EditText android:id=@+id/expense_amount android:hint=@string/amount",
        "expected_doc_id": "android.fixcase.xml-number-inputtype-missing",
    },
}


def run_audit(documents, prompt_audit):
    targeted_ids = {
        target["expected_doc_id"] for target in TARGETS.values()
    }
    queries = []
    for code, target in TARGETS.items():
        query = f"Android XML accessibility {code} {target['evidence']}"
        results = retrieve(
            query,
            documents,
            final_limit=3,
            direct_limit=0,
        )
        ids = [result["doc_id"] for result in results]
        unexpected_targeted_ids = sorted(
            (set(ids) & targeted_ids) - {target["expected_doc_id"]}
        )
        queries.append({
            "issue_code": code,
            "query": query,
            "expected_doc_id": target["expected_doc_id"],
            "retrieved_document_ids": ids,
            "top1_correct": bool(ids and ids[0] == target["expected_doc_id"]),
            "cross_issue_contamination": unexpected_targeted_ids,
        })

    tagged_documents = [
        document
        for document in documents
        if document.get("tags", {}).get("issue_codes")
    ]
    prompt_passed = bool(
        prompt_audit
        and prompt_audit.get("status") == "passed"
        and prompt_audit.get("conditions_differ_only_in_knowledge_block")
        and prompt_audit.get("detector_direct_mapping_disabled_for_all")
        and prompt_audit.get("app_context_retrieval_disabled_for_all")
    )
    top1_correct = sum(item["top1_correct"] for item in queries)
    contamination_count = sum(
        len(item["cross_issue_contamination"]) for item in queries
    )
    passed = (
        top1_correct == len(queries)
        and contamination_count == 0
        and prompt_passed
    )
    return {
        "schema_version": 1,
        "audit_id": "android_xml_rag_engineering_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "model_execution": False,
        "model_calls": 0,
        "knowledge_document_count": len(documents),
        "issue_tagged_document_count": len(tagged_documents),
        "target_query_count": len(queries),
        "top1_correct_count": top1_correct,
        "top1_accuracy": top1_correct / len(queries) if queries else None,
        "cross_issue_contamination_count": contamination_count,
        "prompt_isolation_passed": prompt_passed,
        "prompt_screen_count": (
            prompt_audit.get("screen_count", 0) if prompt_audit else 0
        ),
        "queries": queries,
    }


def write_markdown(path, result):
    lines = [
        "# Android XML RAG Engineering Audit",
        "",
        f"- Status: `{result['status']}`",
        f"- Knowledge documents: {result['knowledge_document_count']}",
        f"- Issue-tagged documents: {result['issue_tagged_document_count']}",
        f"- Target-query Top-1 accuracy: {result['top1_correct_count']} / "
        f"{result['target_query_count']}",
        "- Cross-issue contamination: "
        f"{result['cross_issue_contamination_count']}",
        f"- Prompt isolation: {'passed' if result['prompt_isolation_passed'] else 'failed'}",
        f"- Prompt screens checked: {result['prompt_screen_count']}",
        "- Model calls: 0",
        "",
        "| Issue code | Expected Top-1 document | Result |",
        "|---|---|---|",
    ]
    for query in result["queries"]:
        status = "pass" if query["top1_correct"] else "fail"
        lines.append(
            f"| `{query['issue_code']}` | `{query['expected_doc_id']}` | "
            f"{status} |"
        )
    lines.extend([
        "",
        "This is an offline engineering gate. It verifies retrieval and prompt isolation; model-outcome contribution must be measured in the equal-budget RAG versus No-RAG pilot.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-audit", type=Path, default=DEFAULT_PROMPT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    prompt_audit = (
        json.loads(args.prompt_audit.read_text(encoding="utf-8"))
        if args.prompt_audit.exists()
        else None
    )
    result = run_audit(load_documents(), prompt_audit)
    args.output.mkdir(parents=True, exist_ok=True)
    json_path = args.output / "rag_engineering_audit.json"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.output / "rag_engineering_audit.md", result)
    print(json.dumps({
        "status": result["status"],
        "top1": f"{result['top1_correct_count']}/{result['target_query_count']}",
        "cross_issue_contamination": result["cross_issue_contamination_count"],
        "prompt_isolation_passed": result["prompt_isolation_passed"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
