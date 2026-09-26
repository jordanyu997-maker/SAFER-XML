#!/usr/bin/env python3
"""Build a model-outcome-free pilot dataset for isolating RAG contribution."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTANCES = (
    ROOT
    / "experiments/android_xml_rag_contribution/targeted_sample_pool"
    / "targeted_issue_instances.csv"
)
DEFAULT_V1_PLAN = ROOT / "experiments/android_xml_multimodel/formal_experiment_plan.json"
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_rag_contribution/pilot_dataset"

RAG_SENSITIVE_CODES = {
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY",
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING",
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING",
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
}
COMMON_CONTROL_CODES = {
    "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
}


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def is_true(value):
    return str(value).strip().casefold() in {"1", "true", "yes"}


def normalized_identity(value):
    return "".join(char for char in str(value).casefold() if char.isalnum())


def v1_identities(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    identities = set()
    sources = set()
    for subject in payload.get("subjects", []):
        for field in ("app_id", "app_name"):
            if subject.get(field):
                identities.add(normalized_identity(subject[field]))
        if subject.get("source_path"):
            sources.add(str(Path(subject["source_path"]).resolve()))
    return identities, sources


def app_seen_in_v1(rows, identities, sources):
    first = rows[0]
    return (
        normalized_identity(first["app_name"]) in identities
        or normalized_identity(first["app_id"]) in identities
        or str(Path(first["source_path"]).resolve()) in sources
    )


def actionable(row):
    return (
        is_true(row.get("actionable"))
        and row.get("severity") == "error"
        and row.get("repairability") == "xml_safe"
    )


def group_rows(rows):
    by_app = defaultdict(list)
    by_screen = defaultdict(list)
    for row in rows:
        by_app[row["app_name"]].append(row)
        by_screen[(row["app_name"], row["screen_path"])].append(row)
    return by_app, by_screen


def app_summary(name, rows, identities, sources):
    active = [row for row in rows if actionable(row)]
    codes = Counter(row["code"] for row in active)
    screens = {row["screen_path"] for row in active}
    first = rows[0]
    return {
        "app_id": first["app_id"],
        "app_name": name,
        "category": first["category"],
        "repo_url": first["repo_url"],
        "source_path": first["source_path"],
        "seen_in_v1": app_seen_in_v1(rows, identities, sources),
        "actionable_count": len(active),
        "actionable_screen_count": len(screens),
        "actionable_codes": dict(sorted(codes.items())),
        "rag_sensitive_codes": sorted(set(codes) & RAG_SENSITIVE_CODES),
        "common_control_codes": sorted(set(codes) & COMMON_CONTROL_CODES),
    }


def select_apps(summaries, target_apps):
    anchors = [item for item in summaries if item["rag_sensitive_codes"]]
    anchors.sort(key=lambda item: (item["category"], item["app_name"].casefold()))
    if len(anchors) > target_apps:
        raise ValueError("RAG-sensitive anchor count exceeds the requested App count")

    selected = list(anchors)
    selected_names = {item["app_name"] for item in selected}
    category_counts = Counter(item["category"] for item in selected)
    controls = [
        item for item in summaries
        if item["app_name"] not in selected_names
        and item["common_control_codes"]
        and not item["seen_in_v1"]
    ]
    fallback = [
        item for item in summaries
        if item["app_name"] not in selected_names
        and item["common_control_codes"]
        and item["seen_in_v1"]
    ]

    while len(selected) < target_apps:
        pool = controls or fallback
        if not pool:
            raise ValueError(f"Only {len(selected)} eligible Apps are available")

        def ranking(item):
            excessive = max(item["actionable_count"] - 15, 0)
            return (
                category_counts[item["category"]] > 0,
                -len(item["common_control_codes"]),
                -min(item["actionable_screen_count"], 3),
                excessive,
                abs(item["actionable_count"] - 5),
                item["app_name"].casefold(),
            )

        chosen = min(pool, key=ranking)
        selected.append(chosen)
        selected_names.add(chosen["app_name"])
        category_counts[chosen["category"]] += 1
        if chosen in controls:
            controls.remove(chosen)
        if chosen in fallback:
            fallback.remove(chosen)
    return selected


def screen_summary(app_name, path, rows):
    active = [row for row in rows if actionable(row)]
    active_codes = Counter(row["code"] for row in active)
    all_codes = Counter(row["code"] for row in rows)
    first = rows[0]
    return {
        "app_name": app_name,
        "screen_name": first["screen_name"],
        "screen_path": path,
        "screen_score": int(first.get("screen_score") or 0),
        "actionable_issue_count": len(active),
        "rag_sensitive_issue_count": sum(
            count for code, count in active_codes.items()
            if code in RAG_SENSITIVE_CODES
        ),
        "common_control_issue_count": sum(
            count for code, count in active_codes.items()
            if code in COMMON_CONTROL_CODES
        ),
        "actionable_code_counts": dict(sorted(active_codes.items())),
        "all_finding_code_counts": dict(sorted(all_codes.items())),
    }


def screen_ranking(screen):
    code_count = len(screen["actionable_code_counts"])
    excessive = max(screen["actionable_issue_count"] - 8, 0)
    return (
        -int(screen["rag_sensitive_issue_count"] > 0),
        -code_count,
        excessive,
        -min(screen["actionable_issue_count"], 5),
        -screen["screen_score"],
        screen["screen_path"],
    )


def select_screens(app, by_screen, limit):
    candidates = [
        screen_summary(name, path, rows)
        for (name, path), rows in by_screen.items()
        if name == app["app_name"] and any(actionable(row) for row in rows)
    ]
    mandatory = [
        screen for screen in candidates if screen["rag_sensitive_issue_count"] > 0
    ]
    mandatory.sort(key=screen_ranking)
    selected = mandatory[:limit]
    selected_paths = {screen["screen_path"] for screen in selected}
    remaining = [
        screen for screen in candidates if screen["screen_path"] not in selected_paths
    ]
    remaining.sort(key=screen_ranking)
    selected.extend(remaining[:max(limit - len(selected), 0)])
    return selected


def json_cell(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, default=DEFAULT_INSTANCES)
    parser.add_argument("--v1-plan", type=Path, default=DEFAULT_V1_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-apps", type=int, default=10)
    parser.add_argument("--screens-per-app", type=int, default=3)
    parser.add_argument("--detector-profile", default="expanded_v2")
    args = parser.parse_args()

    rows = read_csv(args.instances)
    by_app, by_screen = group_rows(rows)
    identities, sources = v1_identities(args.v1_plan)
    summaries = [
        app_summary(name, app_rows, identities, sources)
        for name, app_rows in sorted(by_app.items())
        if any(actionable(row) for row in app_rows)
    ]
    selected_apps = select_apps(summaries, args.target_apps)
    selected_screens = []
    for app in selected_apps:
        role = "rag_sensitive_anchor" if app["rag_sensitive_codes"] else "common_negative_control"
        for screen in select_screens(app, by_screen, args.screens_per_app):
            selected_screens.append({
                **screen,
                "app_id": app["app_id"],
                "category": app["category"],
                "pilot_role": role,
                "seen_in_v1": app["seen_in_v1"],
                "source_path": app["source_path"],
            })

    selected_screen_keys = {
        (screen["app_name"], screen["screen_path"])
        for screen in selected_screens
    }
    selected_issue_rows = []
    for row in rows:
        key = (row["app_name"], row["screen_path"])
        if key not in selected_screen_keys:
            continue
        selected_issue_rows.append({
            "app_name": row["app_name"],
            "category": row["category"],
            "screen_name": row["screen_name"],
            "screen_path": row["screen_path"],
            "issue_layout_path": row["issue_layout_path"],
            "code": row["code"],
            "severity": row["severity"],
            "repairability": row["repairability"],
            "actionable": actionable(row),
            "rag_role": (
                "rag_sensitive"
                if row["code"] in RAG_SENSITIVE_CODES and actionable(row)
                else "common_control"
                if row["code"] in COMMON_CONTROL_CODES and actionable(row)
                else "record_only"
            ),
            "component": row["component"],
            "selector": row["selector"],
            "confidence": row["confidence"],
            "requires_review": row["requires_review"],
            "message": row["message"],
        })

    selected_rare = [
        row for row in selected_issue_rows
        if row["rag_role"] == "rag_sensitive"
    ]
    all_rare = [
        row for row in rows
        if actionable(row) and row["code"] in RAG_SENSITIVE_CODES
    ]
    if len(selected_rare) != len(all_rare):
        raise ValueError(
            f"Pilot retained {len(selected_rare)} of {len(all_rare)} RAG-sensitive findings"
        )

    args.output.mkdir(parents=True, exist_ok=True)
    screen_fields = [
        "app_id", "app_name", "category", "pilot_role", "seen_in_v1",
        "source_path", "screen_name", "screen_path", "screen_score",
        "actionable_issue_count", "rag_sensitive_issue_count",
        "common_control_issue_count", "actionable_code_counts",
        "all_finding_code_counts",
    ]
    screen_rows = []
    for screen in selected_screens:
        item = dict(screen)
        item["actionable_code_counts"] = json_cell(item["actionable_code_counts"])
        item["all_finding_code_counts"] = json_cell(item["all_finding_code_counts"])
        screen_rows.append(item)
    write_csv(args.output / "pilot_screens.csv", screen_rows, screen_fields)

    issue_fields = list(selected_issue_rows[0])
    write_csv(args.output / "pilot_issues.csv", selected_issue_rows, issue_fields)

    actionable_selected = [row for row in selected_issue_rows if row["actionable"]]
    code_counts = Counter(row["code"] for row in actionable_selected)
    manifest_apps = []
    for app in selected_apps:
        app_screens = [
            screen for screen in selected_screens
            if screen["app_name"] == app["app_name"]
        ]
        manifest_apps.append({
            **app,
            "pilot_role": (
                "rag_sensitive_anchor"
                if app["rag_sensitive_codes"]
                else "common_negative_control"
            ),
            "selected_screens": app_screens,
        })
    manifest = {
        "schema_version": 1,
        "dataset_id": f"android_xml_rag_contribution_pilot_{args.detector_profile}",
        "status": "candidate_requires_freeze_and_prompt_audit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_uses_model_outputs": False,
        "source_instances": str(args.instances.resolve()),
        "detector_profile": args.detector_profile,
        "selection_policy": {
            "include_all_observed_rag_sensitive_xml_safe_errors": True,
            "common_controls_prefer_unseen_v1_apps": True,
            "maximum_screens_per_app": args.screens_per_app,
            "model_outcomes_or_repair_metrics_used": False,
        },
        "app_count": len(selected_apps),
        "screen_count": len(selected_screens),
        "actionable_issue_count": len(actionable_selected),
        "rag_sensitive_issue_count": len(selected_rare),
        "common_control_issue_count": sum(
            row["rag_role"] == "common_control" for row in actionable_selected
        ),
        "actionable_code_counts": dict(sorted(code_counts.items())),
        "rag_sensitive_code_count": len({row["code"] for row in selected_rare}),
        "apps": manifest_apps,
    }
    (args.output / "pilot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Android XML RAG Contribution Pilot Dataset",
        "",
        f"- Apps: {manifest['app_count']}",
        f"- Screens: {manifest['screen_count']}",
        f"- Actionable findings: {manifest['actionable_issue_count']}",
        f"- RAG-sensitive findings: {manifest['rag_sensitive_issue_count']}",
        f"- Common negative-control findings: {manifest['common_control_issue_count']}",
        "- Model outputs used for selection: no",
        "",
        "| App | Category | Role | V1 seen | Screens | Actionable findings |",
        "|---|---|---|---:|---:|---:|",
    ]
    for app in manifest_apps:
        lines.append(
            f"| {app['app_name']} | {app['category']} | {app['pilot_role']} | "
            f"{'yes' if app['seen_in_v1'] else 'no'} | {len(app['selected_screens'])} | "
            f"{sum(screen['actionable_issue_count'] for screen in app['selected_screens'])} |"
        )
    lines.extend([
        "",
        "This is a candidate pilot dataset, not a completed experiment. All observed high-confidence RAG-sensitive findings are retained. Common cases serve as negative controls for ceiling effects. The next gate is source/freeze validation followed by a prompt-isolation audit; no model should be run before those checks pass.",
        "",
    ])
    (args.output / "README.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "apps": manifest["app_count"],
        "screens": manifest["screen_count"],
        "actionable_findings": manifest["actionable_issue_count"],
        "rag_sensitive_findings": manifest["rag_sensitive_issue_count"],
        "rag_sensitive_codes": manifest["rag_sensitive_code_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
