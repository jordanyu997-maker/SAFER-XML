#!/usr/bin/env python3
"""Prepare or execute the isolated five-App Android XML V2 pilot."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "experiments/android_xml_v2_pilot/protocol_v2.json"
CANDIDATE_PATH = (
    ROOT / "experiments/android_xml_v2_design/pilot_candidates/candidate_manifest.json"
)
LABEL_EVALUATION_PATH = (
    ROOT
    / "experiments/android_xml_v2_design/retrieval_annotation/retrieval_evaluation.json"
)
IMPLEMENTATION_FREEZE_PATH = (
    ROOT / "experiments/android_xml_v2_pilot/implementation_freeze.json"
)
GROUPS = ("one_shot_baseline", "v2_no_rag", "v2_full")
SUMMARY_FIELDS = [
    "app_name",
    "category",
    "group",
    "status",
    "initial_error_count",
    "initial_eligible_error_count",
    "final_error_count",
    "final_eligible_error_count",
    "repair_rate",
    "semantic_round_count",
    "model_calls",
    "format_corrections_used",
    "rejected_attempts",
    "prompt_characters",
    "model_duration_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "warning_count",
    "info_count",
    "safety_finding_count",
    "knowledge_document_count",
    "knowledge_injected_characters",
    "app_context_count",
    "app_context_injected_characters",
    "output_path",
]

sys.path.insert(0, str(ROOT))

from tools.generate_android_xml_v2 import run_group  # noqa: E402


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(item for item in Path(root).rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def git_output(source, *args):
    completed = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def validate_candidates(candidates):
    errors = []
    for app in candidates.get("candidates", []):
        source = Path(app["source_path"])
        package = ROOT / app["input_package"]
        if not source.is_dir():
            errors.append(f"{app['app_name']}: source missing")
            continue
        if not package.is_dir():
            errors.append(f"{app['app_name']}: input package missing")
            continue
        if git_output(source, "rev-parse", "HEAD") != app.get("source_commit"):
            errors.append(f"{app['app_name']}: source commit changed")
        if git_output(source, "status", "--porcelain"):
            errors.append(f"{app['app_name']}: source worktree is dirty")
        if tree_digest(package / "res") != app.get("input_resource_sha256"):
            errors.append(f"{app['app_name']}: frozen resource hash changed")
    return errors


def execution_gate(protocol, label_evaluation, implementation_freeze_exists):
    reasons = []
    provisional = (
        protocol.get("status") == "frozen_provisional"
        and protocol.get("execution", {}).get("allow_pending_retrieval_labels")
    )
    if protocol.get("status") not in {"frozen_ready", "frozen_provisional"}:
        reasons.append("protocol is neither frozen_ready nor frozen_provisional")
    if not protocol.get("execution", {}).get("enabled"):
        reasons.append("protocol execution.enabled is false")
    if not provisional:
        if label_evaluation.get("status") != "complete":
            reasons.append("blinded retrieval labels are incomplete")
        if not label_evaluation.get("execution_gate_passed"):
            reasons.append("retrieval relevance gate has not passed")
    if not implementation_freeze_exists:
        reasons.append("implementation freeze manifest is missing")
    return reasons


def selected_candidates(candidates, names):
    rows = candidates.get("candidates", [])
    if not names:
        return rows
    requested = {name.strip() for name in names.split(",") if name.strip()}
    selected = [row for row in rows if row["app_name"] in requested]
    missing = requested - {row["app_name"] for row in selected}
    if missing:
        raise SystemExit("Unknown V2 pilot Apps: " + ", ".join(sorted(missing)))
    return selected


def state_row(app, group, state, output):
    quality = state.get("final_issue_quality") or [None, None, None, None]
    traces = []
    for path in sorted((output / "reports").glob("retrieval_trace_round_*.json")):
        traces.append(load_json(path))
    model_calls = [
        attempt.get("model_call", {})
        for round_state in state.get("semantic_rounds", [])
        for attempt in round_state.get("attempts", [])
        if attempt.get("model_call")
    ]

    def usage_sum(field):
        values = [
            call.get("usage", {}).get(field)
            for call in model_calls
            if call.get("usage", {}).get(field) is not None
        ]
        return sum(values) if values else None

    return {
        "app_name": app["app_name"],
        "category": app["category"],
        "group": group,
        "status": state.get("status"),
        "initial_error_count": state.get("initial_error_count"),
        "initial_eligible_error_count": state.get("initial_eligible_error_count"),
        "final_error_count": state.get("final_error_count"),
        "final_eligible_error_count": state.get("final_eligible_error_count"),
        "repair_rate": state.get("repair_rate"),
        "semantic_round_count": len(state.get("semantic_rounds", [])),
        "model_calls": state.get("model_calls", 0),
        "format_corrections_used": state.get("format_corrections_used", 0),
        "rejected_attempts": state.get("rejected_attempts", 0),
        "prompt_characters": (
            state.get("prompt_characters")
            if state.get("prompt_characters") is not None
            else sum(
                round_state.get("prompt_characters", 0)
                for round_state in state.get("semantic_rounds", [])
            )
        ),
        "model_duration_ms": sum(
            call.get("duration_ms", 0.0) for call in model_calls
        ),
        "input_tokens": usage_sum("input_tokens"),
        "output_tokens": usage_sum("output_tokens"),
        "total_tokens": usage_sum("total_tokens"),
        "warning_count": quality[1],
        "info_count": quality[2],
        "safety_finding_count": state.get("safety_finding_count", 0),
        "knowledge_document_count": sum(
            trace.get("knowledge_document_count", 0) for trace in traces
        ),
        "knowledge_injected_characters": sum(
            trace.get("knowledge_injected_characters", 0) for trace in traces
        ),
        "app_context_count": sum(
            trace.get("app_context_count", 0) for trace in traces
        ),
        "app_context_injected_characters": sum(
            trace.get("app_context_injected_characters", 0) for trace in traces
        ),
        "output_path": output.relative_to(ROOT).as_posix(),
    }


def write_summary(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    protocol = load_json(PROTOCOL_PATH)
    candidates = load_json(CANDIDATE_PATH)
    candidate_errors = validate_candidates(candidates)
    if candidate_errors:
        raise SystemExit("Candidate validation failed:\n- " + "\n- ".join(candidate_errors))
    label_evaluation = (
        load_json(LABEL_EVALUATION_PATH)
        if LABEL_EVALUATION_PATH.exists()
        else {"status": "missing", "execution_gate_passed": False}
    )
    is_prepare = args.command == "prepare"
    if not is_prepare:
        reasons = execution_gate(
            protocol,
            label_evaluation,
            IMPLEMENTATION_FREEZE_PATH.exists(),
        )
        if reasons:
            raise SystemExit("V2 model execution is blocked:\n- " + "\n- ".join(reasons))
    apps = selected_candidates(candidates, args.apps)
    output_root = ROOT / (
        "experiments/android_xml_v2_pilot/preflight"
        if is_prepare
        else "experiments/android_xml_v2_pilot/runs"
    )
    rows = []
    run_records = []
    total = len(apps) * len(GROUPS)
    index = 0
    for app in apps:
        for group in GROUPS:
            index += 1
            print(f"[{index}/{total}] {app['app_name']} / {group}")
            output = output_root / Path(app["input_package"]).name / group
            state = run_group(
                ROOT / app["input_package"],
                output,
                app["source_path"],
                group,
                args.provider,
                args.model,
                api_key=args.api_key,
                max_format_corrections=3,
                force=args.force or is_prepare,
                dry_run=is_prepare,
            )
            rows.append(state_row(app, group, state, output))
            run_records.append({
                "app_name": app["app_name"],
                "group": group,
                "status": state["status"],
                "model_calls": state["model_calls"],
                "output_path": output.relative_to(ROOT).as_posix(),
                "input_resource_sha256": app["input_resource_sha256"],
                "source_commit": app["source_commit"],
            })
    summary_path = output_root.parent / (
        "preflight_summary.csv" if is_prepare else "pilot_results.csv"
    )
    write_summary(summary_path, rows)
    manifest_path = output_root.parent / (
        "preflight_manifest.json" if is_prepare else "run_manifest.json"
    )
    manifest_path.write_text(
        json.dumps({
            "schema_version": 1,
            "protocol_id": protocol["protocol_id"],
            "mode": "prepare" if is_prepare else "run",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model_execution": not is_prepare,
            "provisional_pending_retrieval_labels": (
                protocol.get("status") == "frozen_provisional"
            ),
            "retrieval_label_status": label_evaluation.get("status"),
            "retrieval_execution_gate_passed": label_evaluation.get(
                "execution_gate_passed", False
            ),
            "app_count": len(apps),
            "group_run_count": len(rows),
            "runs": run_records,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "mode": "prepare" if is_prepare else "run",
        "app_count": len(apps),
        "group_run_count": len(rows),
        "summary": summary_path.relative_to(ROOT).as_posix(),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--apps", help="Comma-separated candidate App names")
        subparser.add_argument("--provider", default="deepseek")
        subparser.add_argument("--model", default="deepseek-v4-pro")
        subparser.add_argument("--api-key", default=None)
        subparser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
