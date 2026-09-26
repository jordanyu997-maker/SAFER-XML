#!/usr/bin/env python3
"""Build a detector-only confirmation dataset for the Android XML RAG study."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTANCES = (
    ROOT
    / "experiments/android_xml_rag_contribution/targeted_sample_pool_expanded_v3_1"
    / "targeted_issue_instances.csv"
)
DEFAULT_PRIOR_MANIFEST = (
    ROOT
    / "experiments/android_xml_rag_contribution/equal_budget_limit8_expanded_types_v3_1"
    / "frozen_manifest.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "experiments/android_xml_rag_contribution/confirmation_dataset_expanded_v3_1"
)

HARD_CODES = {
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
    "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY",
    "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING",
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING",
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
    "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME",
    "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME",
}


def is_true(value):
    return str(value).strip().casefold() in {"1", "true", "yes"}


def actionable(row):
    return (
        is_true(row.get("actionable"))
        and row.get("severity") == "error"
        and row.get("repairability") == "xml_safe"
    )


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prior_task_identity(paths):
    screens = set()
    apps = set()
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        tasks = payload.get("tasks", [])
        screens.update((item["app_name"], item["screen_path"]) for item in tasks)
        apps.update(item["app_name"] for item in tasks)
    return screens, apps


def layout_features(row):
    """Return lightweight, model-independent XML complexity signals."""
    path = Path(row["source_path"]) / row["screen_path"]
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {
            "element_count": 0,
            "max_depth": 0,
            "custom_component_count": 0,
            "resource_reference_count": 0,
            "style_reference_count": 0,
            "structural_complexity_score": 0,
        }

    elements = list(root.iter())
    max_depth = 0

    def visit(element, depth):
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        for child in element:
            visit(child, depth + 1)

    visit(root, 1)
    custom_components = sum("." in element.tag for element in elements)
    values = [str(value) for element in elements for value in element.attrib.values()]
    resource_references = sum(value.startswith("@") for value in values)
    style_references = sum(
        value.startswith("?attr/") or value.startswith("@style/")
        for value in values
    )
    complexity = (
        min(len(elements), 80)
        + min(max_depth, 12) * 3
        + min(custom_components, 10) * 4
        + min(resource_references, 40)
        + min(style_references, 10) * 2
    )
    return {
        "element_count": len(elements),
        "max_depth": max_depth,
        "custom_component_count": custom_components,
        "resource_reference_count": resource_references,
        "style_reference_count": style_references,
        "structural_complexity_score": complexity,
    }


def build_screen_candidates(rows, excluded_screens, prior_apps):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["app_name"], row["screen_path"])].append(row)

    candidates = []
    for key, screen_rows in grouped.items():
        if key in excluded_screens:
            continue
        active = [row for row in screen_rows if actionable(row)]
        if not active:
            continue
        first = screen_rows[0]
        active_counts = Counter(row["code"] for row in active)
        all_counts = Counter(row["code"] for row in screen_rows)
        candidates.append({
            "app_id": first["app_id"],
            "app_name": first["app_name"],
            "category": first["category"],
            "source_path": first["source_path"],
            "screen_name": first["screen_name"],
            "screen_path": first["screen_path"],
            "screen_score": int(first.get("screen_score") or 0),
            "unseen_app": first["app_name"] not in prior_apps,
            "actionable_issue_count": len(active),
            "hard_issue_count": sum(
                count for code, count in active_counts.items() if code in HARD_CODES
            ),
            "actionable_code_counts": dict(sorted(active_counts.items())),
            "all_finding_code_counts": dict(sorted(all_counts.items())),
            **layout_features(first),
        })
    return sorted(
        candidates,
        key=lambda item: (
            item["app_name"].casefold(),
            item["screen_path"],
        ),
    )


def select_confirmation_screens(
    candidates,
    target_screens=20,
    min_unseen_apps=12,
    max_findings_per_screen=12,
):
    if target_screens < 1:
        raise ValueError("target_screens must be positive")
    available_apps = {item["app_name"] for item in candidates}
    if len(available_apps) < target_screens:
        raise ValueError(
            f"Only {len(available_apps)} Apps remain for {target_screens} screens"
        )

    bounded = [
        item for item in candidates
        if item["actionable_issue_count"] <= max_findings_per_screen
    ]
    all_hard_codes = {
        code for item in candidates for code in item["actionable_code_counts"]
        if code in HARD_CODES
    }
    bounded_hard_codes = {
        code for item in bounded for code in item["actionable_code_counts"]
        if code in HARD_CODES
    }
    if (
        len({item["app_name"] for item in bounded}) >= target_screens
        and all_hard_codes <= bounded_hard_codes
    ):
        candidates = bounded

    code_screen_frequency = Counter()
    for item in candidates:
        code_screen_frequency.update(item["actionable_code_counts"].keys())

    selected = []
    selected_apps = set()
    category_counts = Counter()
    selected_code_counts = Counter()

    def score(item, prioritize_unseen=False):
        codes = set(item["actionable_code_counts"])
        hard_codes = codes & HARD_CODES
        uncovered_hard = hard_codes - set(selected_code_counts)
        uncovered_codes = codes - set(selected_code_counts)
        rarity = sum(1.0 / code_screen_frequency[code] for code in codes)
        excessive = max(item["actionable_issue_count"] - 12, 0)
        return (
            len(uncovered_hard),
            len(uncovered_codes),
            int(prioritize_unseen and item["unseen_app"]),
            rarity,
            int(item["unseen_app"]),
            int(category_counts[item["category"]] == 0),
            len(codes),
            item["structural_complexity_score"],
            min(item["hard_issue_count"], 6),
            min(item["actionable_issue_count"], 8),
            -excessive,
            item["screen_score"],
            item["app_name"].casefold(),
            item["screen_path"],
        )

    available_hard_codes = sorted(
        {code for item in candidates for code in item["actionable_code_counts"]}
        & HARD_CODES,
        key=lambda code: (code_screen_frequency[code], code),
    )
    for code in available_hard_codes:
        if code in selected_code_counts or len(selected) >= target_screens:
            continue
        eligible = [
            item for item in candidates
            if item["app_name"] not in selected_apps
            and code in item["actionable_code_counts"]
        ]
        if not eligible:
            continue
        chosen = max(eligible, key=score)
        selected.append(chosen)
        selected_apps.add(chosen["app_name"])
        category_counts[chosen["category"]] += 1
        selected_code_counts.update(chosen["actionable_code_counts"])

    while len(selected) < target_screens:
        eligible = [
            item for item in candidates if item["app_name"] not in selected_apps
        ]
        if not eligible:
            break
        unseen_selected = sum(item["unseen_app"] for item in selected)
        slots_left = target_screens - len(selected)
        prioritize_unseen = unseen_selected < min_unseen_apps and (
            min_unseen_apps - unseen_selected >= slots_left
        )
        chosen = max(
            eligible,
            key=lambda item: score(item, prioritize_unseen=prioritize_unseen),
        )
        selected.append(chosen)
        selected_apps.add(chosen["app_name"])
        category_counts[chosen["category"]] += 1
        selected_code_counts.update(chosen["actionable_code_counts"])

    if len(selected) != target_screens:
        raise ValueError(f"Selected only {len(selected)} of {target_screens} screens")
    return selected


def json_cell(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def write_dataset(
    output,
    rows,
    selected,
    excluded_screens,
    prior_apps,
    max_findings_per_screen,
):
    output.mkdir(parents=True, exist_ok=True)
    selected_keys = {
        (item["app_name"], item["screen_path"]) for item in selected
    }
    screen_fields = [
        "app_id", "app_name", "category", "pilot_role", "seen_in_prior_pilot",
        "source_path", "screen_name", "screen_path", "screen_score",
        "element_count", "max_depth", "custom_component_count",
        "resource_reference_count", "style_reference_count",
        "structural_complexity_score",
        "actionable_issue_count", "rag_sensitive_issue_count",
        "common_control_issue_count", "actionable_code_counts",
        "all_finding_code_counts",
    ]
    screen_rows = []
    for item in selected:
        counts = item["actionable_code_counts"]
        hard_count = sum(count for code, count in counts.items() if code in HARD_CODES)
        screen_rows.append({
            "app_id": item["app_id"],
            "app_name": item["app_name"],
            "category": item["category"],
            "pilot_role": (
                "hard_type_confirmation" if hard_count else "common_control_confirmation"
            ),
            "seen_in_prior_pilot": not item["unseen_app"],
            "source_path": item["source_path"],
            "screen_name": item["screen_name"],
            "screen_path": item["screen_path"],
            "screen_score": item["screen_score"],
            "element_count": item["element_count"],
            "max_depth": item["max_depth"],
            "custom_component_count": item["custom_component_count"],
            "resource_reference_count": item["resource_reference_count"],
            "style_reference_count": item["style_reference_count"],
            "structural_complexity_score": item["structural_complexity_score"],
            "actionable_issue_count": item["actionable_issue_count"],
            "rag_sensitive_issue_count": hard_count,
            "common_control_issue_count": item["actionable_issue_count"] - hard_count,
            "actionable_code_counts": json_cell(counts),
            "all_finding_code_counts": json_cell(item["all_finding_code_counts"]),
        })
    write_csv(output / "pilot_screens.csv", screen_rows, screen_fields)

    issue_rows = []
    for row in rows:
        if (row["app_name"], row["screen_path"]) not in selected_keys:
            continue
        item = dict(row)
        item["actionable"] = actionable(row)
        item["rag_role"] = (
            "hard_confirmation"
            if actionable(row) and row["code"] in HARD_CODES
            else "common_control"
            if actionable(row)
            else "record_only"
        )
        issue_rows.append(item)
    issue_fields = list(issue_rows[0])
    write_csv(output / "pilot_issues.csv", issue_rows, issue_fields)

    actionable_rows = [row for row in issue_rows if row["actionable"]]
    code_counts = Counter(row["code"] for row in actionable_rows)
    selected_apps = {item["app_name"] for item in selected}
    available_codes = {
        row["code"] for row in rows
        if actionable(row)
        and (row["app_name"], row["screen_path"]) not in excluded_screens
    }
    manifest = {
        "schema_version": 1,
        "dataset_id": "android_xml_rag_confirmation_expanded_v3_1",
        "status": "candidate_requires_freeze_and_prompt_audit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_uses_model_outputs": False,
        "selection_inputs": ["detector_findings", "prior_frozen_task_identity"],
        "prior_result_metrics_consumed": False,
        "detector_profile": "expanded_v3",
        "selection_policy": {
            "exclude_exact_prior_screens": True,
            "maximum_screens_per_app": 1,
            "prefer_hard_and_rare_issue_types": True,
            "prefer_structurally_complex_screens": True,
            "prefer_unseen_apps": True,
            "preferred_maximum_findings_per_screen": max_findings_per_screen,
            "model_outcomes_or_repair_metrics_used": False,
        },
        "excluded_prior_screen_count": len(excluded_screens),
        "app_count": len(selected_apps),
        "screen_count": len(selected),
        "unseen_app_count": sum(item["app_name"] not in prior_apps for item in selected),
        "reused_app_new_screen_count": sum(item["app_name"] in prior_apps for item in selected),
        "exact_prior_screen_overlap_count": len(selected_keys & excluded_screens),
        "actionable_issue_count": len(actionable_rows),
        "actionable_code_counts": dict(sorted(code_counts.items())),
        "available_but_unselected_codes": sorted(available_codes - set(code_counts)),
        "unavailable_hard_codes": sorted(HARD_CODES - available_codes),
        "screens": screen_rows,
    }
    (output / "pilot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Android XML RAG Confirmation Dataset",
        "",
        f"- Apps/screens: {manifest['app_count']}/{manifest['screen_count']}",
        f"- Apps absent from V3.1: {manifest['unseen_app_count']}",
        f"- Reused Apps with a new screen: {manifest['reused_app_new_screen_count']}",
        f"- Exact V3.1 screen overlap: {manifest['exact_prior_screen_overlap_count']}",
        f"- Actionable findings: {manifest['actionable_issue_count']}",
        "- Model outcomes used for selection: no",
        "",
        "| App | Category | New App | Screen | Findings | Codes |",
        "|---|---|---|---|---:|---|",
    ]
    for item in screen_rows:
        codes = ", ".join(json.loads(item["actionable_code_counts"]))
        lines.append(
            f"| {item['app_name']} | {item['category']} | "
            f"{'no' if item['seen_in_prior_pilot'] else 'yes'} | "
            f"`{item['screen_name']}` | {item['actionable_issue_count']} | {codes} |"
        )
    lines.extend([
        "",
        "Unavailable high-confidence hard types are reported in the manifest rather than synthesized or promoted from warnings.",
        "",
    ])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, default=DEFAULT_INSTANCES)
    parser.add_argument(
        "--prior-manifest",
        type=Path,
        action="append",
        dest="prior_manifests",
        help="Prior frozen manifest to exclude; repeat for multiple experiments.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-screens", type=int, default=20)
    parser.add_argument("--min-unseen-apps", type=int, default=12)
    parser.add_argument("--max-findings-per-screen", type=int, default=12)
    args = parser.parse_args()

    rows = read_csv(args.instances)
    prior_manifests = args.prior_manifests or [DEFAULT_PRIOR_MANIFEST]
    excluded_screens, prior_apps = prior_task_identity(prior_manifests)
    candidates = build_screen_candidates(rows, excluded_screens, prior_apps)
    selected = select_confirmation_screens(
        candidates,
        target_screens=args.target_screens,
        min_unseen_apps=args.min_unseen_apps,
        max_findings_per_screen=args.max_findings_per_screen,
    )
    manifest = write_dataset(
        args.output,
        rows,
        selected,
        excluded_screens,
        prior_apps,
        args.max_findings_per_screen,
    )
    print(json.dumps({
        "apps": manifest["app_count"],
        "screens": manifest["screen_count"],
        "unseen_apps": manifest["unseen_app_count"],
        "actionable_findings": manifest["actionable_issue_count"],
        "covered_codes": len(manifest["actionable_code_counts"]),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
