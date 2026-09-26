#!/usr/bin/env python3
"""Create candidate or final integrity manifests for the Android XML V2 pilot."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "experiments/android_xml_v2_pilot/protocol_v2.json"
LABEL_EVALUATION_PATH = (
    ROOT
    / "experiments/android_xml_v2_design/retrieval_annotation/retrieval_evaluation.json"
)
FILES = [
    "tools/generate_android_xml_v2.py",
    "tools/run_android_xml_v2_pilot.py",
    "tools/evaluate_android_xml_retrieval_labels.py",
    "tools/retrieval/v2_hybrid.py",
    "tools/retrieval/app_context.py",
    "tools/generate_android_xml.py",
    "tools/evaluation/android_xml_a11y_check.py",
    "tools/run_android_xml_experiment.py",
    "knowledge/rag/knowledge_documents.json",
    "experiments/android_xml_v2_pilot/protocol_v2.json",
    "experiments/android_xml_v2_design/pilot_candidates/candidate_manifest.json",
    "experiments/android_xml_v2_design/retrieval_annotation/annotation_manifest.json",
    "experiments/android_xml_v2_design/retrieval_annotation/relevance_annotation.csv",
    "experiments/android_xml_v2_design/retrieval_annotation/relevance_annotation_blinded.csv",
    "experiments/android_xml_v2_design/retrieval_annotation/retrieval_evaluation.json",
    "experiments/android_xml_v2_pilot/preflight_summary.csv",
    "experiments/android_xml_v2_pilot/preflight_manifest.json",
]
TREES = [
    "experiments/android_xml_v2_design/pilot_candidates/inputs",
    "experiments/android_xml_v2_pilot/preflight",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path):
    path = Path(path)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def tree_record(root):
    root = Path(root)
    digest = hashlib.sha256()
    count = 0
    size = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        file_size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(file_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
        count += 1
        size += file_size
    return {
        "path": root.relative_to(ROOT).as_posix(),
        "file_count": count,
        "size_bytes": size,
        "tree_sha256": digest.hexdigest(),
    }


def run_tests():
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPYCACHEPREFIX": "/tmp/safer-xml-pycache"},
    )
    output = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests", output)
    if completed.returncode != 0:
        raise SystemExit("V2 freeze tests failed:\n" + output[-8000:])
    return {
        "command": "python3 -m unittest discover -s tests",
        "status": "passed",
        "test_count": int(match.group(1)) if match else None,
    }


def missing_inputs():
    return [value for value in FILES + TREES if not (ROOT / value).exists()]


def finalize_protocol(label_evaluation, provisional=False):
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol["status"] = "frozen_provisional" if provisional else "frozen_ready"
    protocol["frozen_at"] = datetime.now(timezone.utc).isoformat()
    protocol["execution"]["enabled"] = True
    protocol["execution"]["enable_condition"] = (
        "user_authorized_internal_pilot_with_pending_retrieval_labels"
        if provisional
        else "satisfied"
    )
    protocol["execution"]["allow_pending_retrieval_labels"] = provisional
    protocol["evaluation"]["retrieval_evaluation"] = (
        LABEL_EVALUATION_PATH.relative_to(ROOT).as_posix()
    )
    protocol["evaluation"]["retrieval_execution_gate_passed"] = label_evaluation[
        "execution_gate_passed"
    ]
    protocol["evaluation"]["retrieval_labels_required_before_model_execution"] = (
        not provisional
    )
    protocol["evaluation"]["retrieval_labels_required_before_formal_claims"] = True
    protocol["evaluation"]["provisional_results_must_not_be_used_as_formal_rag_evidence"] = provisional
    PROTOCOL_PATH.write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--final", action="store_true")
    modes.add_argument("--provisional", action="store_true")
    args = parser.parse_args()
    missing = missing_inputs()
    if missing:
        raise SystemExit("V2 freeze input missing: " + ", ".join(missing))
    label_evaluation = json.loads(
        LABEL_EVALUATION_PATH.read_text(encoding="utf-8")
    )
    if args.final:
        if label_evaluation.get("status") != "complete":
            raise SystemExit("Cannot finalize V2: blinded retrieval labels are incomplete")
        if not label_evaluation.get("execution_gate_passed"):
            raise SystemExit("Cannot finalize V2: retrieval relevance gate failed")
    verification = run_tests()
    if args.final or args.provisional:
        finalize_protocol(label_evaluation, provisional=args.provisional)
    status = (
        "frozen_ready"
        if args.final
        else "frozen_provisional"
        if args.provisional
        else "implementation_tested_execution_blocked"
    )
    manifest = {
        "schema_version": 1,
        "freeze_id": (
            "android_xml_v2_internal_pilot_final"
            if args.final
            else "android_xml_v2_internal_pilot_provisional"
            if args.provisional
            else "android_xml_v2_internal_pilot_candidate"
        ),
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_execution_enabled": bool(args.final or args.provisional),
        "provisional_pending_retrieval_labels": bool(args.provisional),
        "retrieval_label_status": label_evaluation.get("status"),
        "retrieval_execution_gate_passed": label_evaluation.get(
            "execution_gate_passed", False
        ),
        "verification": verification,
        "files": [file_record(ROOT / value) for value in FILES],
        "trees": [tree_record(ROOT / value) for value in TREES],
        "policy": {
            "modify_v1": False,
            "mix_v1_and_v2_outputs": False,
            "cross_app_context": False,
            "overwrite_after_final_freeze": False,
        },
    }
    output = ROOT / "experiments/android_xml_v2_pilot" / (
        "implementation_freeze.json"
        if args.final or args.provisional
        else "implementation_candidate.json"
    )
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "freeze_id": manifest["freeze_id"],
        "status": status,
        "tests": verification["test_count"],
        "files": len(manifest["files"]),
        "trees": len(manifest["trees"]),
        "output": output.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
