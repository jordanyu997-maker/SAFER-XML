#!/usr/bin/env python3
"""Create an integrity manifest for the completed Android XML V1 study."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v1_freeze/manifest.json"

FILES = [
    "tools/generate.py",
    "tools/generate_android_xml.py",
    "tools/evaluation/android_xml_a11y_check.py",
    "tools/retrieval/search_documents.py",
    "tools/retrieval/build_rag_prompt.py",
    "tools/run_android_xml_experiment.py",
    "tools/run_android_xml_multimodel.py",
    "tools/run_android_xml_ablation.py",
    "knowledge/rag/knowledge_documents.json",
    "knowledge/rag/knowledge_document_schema.json",
    "experiments/android_xml_multimodel/protocol_v1.json",
    "experiments/android_xml_multimodel/multimodel_app_results.csv",
    "experiments/android_xml_multimodel/run_manifest.json",
    "experiments/android_xml_multimodel/analysis/analysis_manifest.json",
    "experiments/android_xml_multimodel/analysis/primary_statistical_results.csv",
    "experiments/android_xml_multimodel/analysis/stability_summary.csv",
    "experiments/android_xml_ablation/protocol_v1.json",
    "experiments/android_xml_ablation/ablation_results.csv",
    "experiments/android_xml_ablation/run_manifest.json",
    "experiments/android_xml_ablation_claude/protocol_v1.json",
    "experiments/android_xml_ablation_claude/ablation_results.csv",
    "experiments/android_xml_ablation_claude/run_manifest.json",
]

TREES = [
    "experiments/android_xml_multimodel/runs",
    "experiments/android_xml_ablation/runs",
    "experiments/android_xml_ablation_claude/runs",
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
        if path.name == ".DS_Store":
            continue
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


def build_manifest():
    missing = [value for value in FILES + TREES if not (ROOT / value).exists()]
    if missing:
        raise SystemExit("V1 freeze input missing: " + ", ".join(missing))
    return {
        "schema_version": 1,
        "freeze_id": "android_xml_v1_2026_07_20",
        "status": "frozen_read_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "multimodel_formal_app_rows": 180,
            "multimodel_pilot_rows_excluded": 8,
            "deepseek_ablation_rows": 120,
            "claude_ablation_rows": 120,
            "independent_unit": "App",
        },
        "policy": {
            "overwrite_existing_results": False,
            "mix_v1_and_v2_outputs": False,
            "use_v1_outcomes_to_select_v2_subjects": False,
            "v2_requires_new_protocol_and_output_root": True,
        },
        "files": [file_record(ROOT / value) for value in FILES],
        "run_trees": [tree_record(ROOT / value) for value in TREES],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "freeze_id": manifest["freeze_id"],
        "files": len(manifest["files"]),
        "run_trees": len(manifest["run_trees"]),
        "output": args.output.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
