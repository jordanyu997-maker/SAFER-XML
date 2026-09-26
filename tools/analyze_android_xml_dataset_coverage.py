#!/usr/bin/env python3
"""Audit and redesign Android XML subjects without using model outcomes."""
import argparse
import csv
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLONE_ROOT = Path("fdroid_apps/selected_xml_apps")
DEFAULT_METADATA = ROOT / "reports/fdroid_screening_v3/app_screening.json"
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_dataset_redesign/coverage_audit"
DEFAULT_PREVIOUS_PLAN = ROOT / "experiments/android_xml_multimodel/formal_experiment_plan.json"
MAX_SCREEN_POOL = 12

sys.path.insert(0, str(ROOT))

from tools.dataset.fdroid_app_screening import (  # noqa: E402
    collect_layouts,
    expand_layout_dependencies,
    relative_to_repo,
    scan_source_references,
    score_layout,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    DEFAULT_DETECTOR_PROFILE,
    DETECTOR_PROFILES,
    scan,
)


def issue_severity(issue):
    severity = issue.get("severity", issue.get("type", "error"))
    return severity if severity in {"error", "warning", "info"} else "error"


def is_xml_safe_error(issue):
    return (
        issue_severity(issue) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
    )


def resource_root(path):
    for parent in Path(path).resolve().parents:
        if parent.name == "res":
            return parent
    return None


def resource_context_paths(res_roots):
    paths = []
    for root in sorted(res_roots):
        for directory in sorted(root.glob("values*")):
            if directory.is_dir():
                paths.extend(sorted(directory.glob("*.xml")))
    return paths


def ranked_screen_candidates(repo, limit):
    layouts = collect_layouts(repo)
    references, entry_references, _, _ = scan_source_references(repo)
    best_by_name = {}
    for path in layouts:
        candidate = score_layout(path, references, entry_references)
        if not candidate:
            continue
        candidate.relative_path = relative_to_repo(path, repo)
        current = best_by_name.get(candidate.name)
        if current is None or candidate.score > current.score:
            best_by_name[candidate.name] = candidate
    return sorted(
        best_by_name.values(),
        key=lambda item: (-item.score, item.name, item.relative_path),
    )[:limit]


def issue_signature(issue):
    return (
        issue.get("code", "UNKNOWN"),
        str(Path(issue.get("file", "")).resolve()),
        issue.get("selector", ""),
        issue_severity(issue),
        issue.get("repairability", "xml_safe"),
    )


def scan_candidate_pool(
    repo,
    candidates,
    detector_profile=DEFAULT_DETECTOR_PROFILE,
):
    dependencies = {}
    all_layouts = set()
    res_roots = set()
    for candidate in candidates:
        path = (repo / candidate.relative_path).resolve()
        expanded = set(expand_layout_dependencies([path]))
        dependencies[candidate.relative_path] = expanded
        all_layouts.update(expanded)
        res_roots.update(
            root for root in (resource_root(item) for item in expanded) if root
        )
    issues = scan(
        sorted(all_layouts) + resource_context_paths(res_roots),
        detector_profile=detector_profile,
    )
    issues = [
        issue
        for issue in issues
        if Path(issue.get("file", "")).parent.name.startswith("layout")
    ]
    by_signature = {issue_signature(issue): issue for issue in issues}
    candidate_issues = {}
    for candidate in candidates:
        files = {str(path.resolve()) for path in dependencies[candidate.relative_path]}
        candidate_issues[candidate.relative_path] = {
            signature
            for signature, issue in by_signature.items()
            if str(Path(issue.get("file", "")).resolve()) in files
        }
    return by_signature, candidate_issues


def combination_score(combo, candidate_issues, issues_by_signature):
    signatures = set().union(
        *(candidate_issues[candidate.relative_path] for candidate in combo)
    )
    issues = [issues_by_signature[signature] for signature in signatures]
    xml_safe = [issue for issue in issues if is_xml_safe_error(issue)]
    xml_safe_codes = {issue.get("code") for issue in xml_safe}
    error_codes = {
        issue.get("code")
        for issue in issues
        if issue_severity(issue) == "error"
    }
    all_codes = {issue.get("code") for issue in issues}
    excessive_issue_count = max(len(xml_safe) - 20, 0)
    return (
        len(xml_safe_codes),
        -excessive_issue_count,
        len(error_codes),
        len(all_codes),
        min(len(xml_safe), 5),
        sum(candidate.score for candidate in combo),
        -len(combo),
    )


def select_screens(candidates, candidate_issues, issues_by_signature):
    if len(candidates) < 2:
        return list(candidates)
    combinations = itertools.chain(
        itertools.combinations(candidates, 2),
        itertools.combinations(candidates, 3),
    )
    return list(max(
        combinations,
        key=lambda combo: combination_score(
            combo, candidate_issues, issues_by_signature
        ),
    ))


def metadata_maps(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    by_path = {}
    by_name = {}
    for app in payload.get("apps", []):
        if app.get("local_path"):
            by_path[str(Path(app["local_path"]).resolve())] = app
        by_name[app.get("name", "").casefold()] = app
    return by_path, by_name


def count_issues(issues):
    severities = Counter(issue_severity(issue) for issue in issues)
    repairability = Counter(
        issue.get("repairability", "xml_safe") for issue in issues
    )
    codes = Counter(issue.get("code", "UNKNOWN") for issue in issues)
    xml_safe_codes = Counter(
        issue.get("code", "UNKNOWN")
        for issue in issues
        if is_xml_safe_error(issue)
    )
    return {
        "error_count": severities["error"],
        "warning_count": severities["warning"],
        "info_count": severities["info"],
        "total_issue_count": len(issues),
        "xml_safe_error_count": sum(xml_safe_codes.values()),
        "issue_code_counts": dict(sorted(codes.items())),
        "xml_safe_error_code_counts": dict(sorted(xml_safe_codes.items())),
        "repairability_counts": dict(sorted(repairability.items())),
    }


def audit_repository(
    repo,
    metadata,
    screen_pool_limit,
    detector_profile=DEFAULT_DETECTOR_PROFILE,
):
    candidates = ranked_screen_candidates(repo, screen_pool_limit)
    if not candidates:
        return {
            "app_id": metadata.get("app_id", repo.name),
            "app_name": metadata.get("name", repo.name),
            "category": metadata.get("category", "Unknown"),
            "categories": metadata.get("categories", ["Unknown"]),
            "repo_url": metadata.get("repo_url", ""),
            "source_path": str(repo.resolve()),
            "candidate_screen_count": 0,
            "selected_screens": [],
            "selected_issues": [],
            **count_issues([]),
        }
    issues_by_signature, candidate_issues = scan_candidate_pool(
        repo,
        candidates,
        detector_profile=detector_profile,
    )
    selected = select_screens(candidates, candidate_issues, issues_by_signature)
    selected_signatures = set().union(
        *(candidate_issues[candidate.relative_path] for candidate in selected)
    ) if selected else set()
    selected_issues = [
        issues_by_signature[signature] for signature in sorted(selected_signatures)
    ]
    screen_rows = []
    for candidate in candidates:
        issues = [
            issues_by_signature[signature]
            for signature in candidate_issues[candidate.relative_path]
        ]
        screen_rows.append({
            "name": candidate.name,
            "relative_path": candidate.relative_path,
            "structural_score": candidate.score,
            "structural_reasons": candidate.reasons,
            "selected": candidate in selected,
            **count_issues(issues),
        })
    return {
        "app_id": metadata.get("app_id", repo.name),
        "app_name": metadata.get("name", repo.name),
        "category": metadata.get("category", "Unknown"),
        "categories": metadata.get("categories", [metadata.get("category", "Unknown")]),
        "repo_url": metadata.get("repo_url", ""),
        "source_path": str(repo.resolve()),
        "candidate_screen_count": len(candidates),
        "selected_screens": screen_rows,
        "selected_issues": selected_issues,
        **count_issues(selected_issues),
    }


def select_apps(apps, target, max_per_category):
    eligible = [
        app
        for app in apps
        if len([screen for screen in app["selected_screens"] if screen["selected"]]) >= 2
        and app["xml_safe_error_count"] > 0
    ]
    code_app_frequency = Counter(
        code
        for app in eligible
        for code in app["xml_safe_error_code_counts"]
    )
    selected = []
    remaining = list(eligible)
    category_counts = Counter()
    effective_category_limit = max_per_category
    covered_xml_safe_codes = set()
    covered_all_codes = set()
    while remaining and len(selected) < target:
        candidates = [
            app
            for app in remaining
            if effective_category_limit <= 0
            or category_counts[app["category"]] < effective_category_limit
        ]
        if not candidates:
            if remaining and effective_category_limit > 0:
                effective_category_limit += 1
                continue
            break

        def marginal_score(app):
            xml_codes = set(app["xml_safe_error_code_counts"])
            all_codes = set(app["issue_code_counts"])
            rarity = sum(
                1 / code_app_frequency[code]
                for code in xml_codes
                if code_app_frequency[code]
            )
            return (
                len(xml_codes - covered_xml_safe_codes),
                rarity,
                category_counts[app["category"]] == 0,
                len(all_codes - covered_all_codes),
                min(app["xml_safe_error_count"], 10),
                -app["xml_safe_error_count"],
                app["app_name"].casefold(),
            )

        chosen = max(candidates, key=marginal_score)
        selected.append(chosen)
        remaining.remove(chosen)
        category_counts[chosen["category"]] += 1
        covered_xml_safe_codes.update(chosen["xml_safe_error_code_counts"])
        covered_all_codes.update(chosen["issue_code_counts"])
    return selected, eligible, max(category_counts.values(), default=0)


def json_cell(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalized_identity(value):
    return "".join(character for character in str(value).casefold() if character.isalnum())


def identity_keys(app):
    return {
        normalized_identity(app.get(field, ""))
        for field in ("app_id", "app_name")
        if app.get(field)
    }


def compare_previous_dataset(selected, previous_plan_path):
    previous = json.loads(
        Path(previous_plan_path).read_text(encoding="utf-8")
    ).get("subjects", [])
    matched_previous = set()
    added = []
    for app in selected:
        match = next(
            (
                index
                for index, old in enumerate(previous)
                if index not in matched_previous
                and identity_keys(app).intersection(identity_keys(old))
            ),
            None,
        )
        if match is None:
            added.append(app)
        else:
            matched_previous.add(match)
    removed = [
        app for index, app in enumerate(previous) if index not in matched_previous
    ]
    return {
        "previous_app_count": len(previous),
        "overlap_app_count": len(matched_previous),
        "added_app_count": len(added),
        "removed_app_count": len(removed),
        "added_apps": [
            {"app_name": app["app_name"], "category": app["category"]}
            for app in added
        ],
        "removed_apps": [
            {"app_name": app["app_name"], "category": app["category"]}
            for app in removed
        ],
    }


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    output,
    apps,
    selected,
    eligible,
    target,
    actual_max_per_category,
    previous_comparison,
    detector_profile=DEFAULT_DETECTOR_PROFILE,
):
    output.mkdir(parents=True, exist_ok=True)
    app_rows = []
    screen_rows = []
    finding_rows = []
    selected_names = {app["app_name"] for app in selected}
    for app in apps:
        selected_screen_names = [
            screen["name"] for screen in app["selected_screens"] if screen["selected"]
        ]
        app_rows.append({
            "app_id": app["app_id"],
            "app_name": app["app_name"],
            "category": app["category"],
            "source_path": app["source_path"],
            "candidate_screen_count": app["candidate_screen_count"],
            "selected_interface_count": len(selected_screen_names),
            "selected_interfaces": json_cell(selected_screen_names),
            "error_count": app["error_count"],
            "warning_count": app["warning_count"],
            "info_count": app["info_count"],
            "total_issue_count": app["total_issue_count"],
            "xml_safe_error_count": app["xml_safe_error_count"],
            "issue_code_counts": json_cell(app["issue_code_counts"]),
            "xml_safe_error_code_counts": json_cell(app["xml_safe_error_code_counts"]),
            "eligible_for_repair_benchmark": app in eligible,
            "selected_for_candidate_40": app["app_name"] in selected_names,
        })
        for screen in app["selected_screens"]:
            screen_rows.append({
                "app_name": app["app_name"],
                "category": app["category"],
                "screen_name": screen["name"],
                "relative_path": screen["relative_path"],
                "structural_score": screen["structural_score"],
                "selected_for_app": screen["selected"],
                "error_count": screen["error_count"],
                "warning_count": screen["warning_count"],
                "info_count": screen["info_count"],
                "xml_safe_error_count": screen["xml_safe_error_count"],
                "issue_code_counts": json_cell(screen["issue_code_counts"]),
                "xml_safe_error_code_counts": json_cell(screen["xml_safe_error_code_counts"]),
            })
        for issue in app["selected_issues"]:
            finding_rows.append({
                "app_name": app["app_name"],
                "category": app["category"],
                "selected_for_candidate_40": app["app_name"] in selected_names,
                "xml_file": Path(issue.get("file", "")).name,
                "code": issue.get("code", "UNKNOWN"),
                "severity": issue_severity(issue),
                "repairability": issue.get("repairability", "xml_safe"),
                "component": issue.get("component") or issue.get("element"),
                "selector": issue.get("selector"),
                "message": issue.get("message"),
            })
    write_csv(output / "app_coverage_matrix.csv", app_rows, list(app_rows[0]))
    write_csv(output / "screen_coverage_matrix.csv", screen_rows, list(screen_rows[0]))
    write_csv(output / "finding_instances.csv", finding_rows, list(finding_rows[0]))

    type_rows = []
    for (code, severity, repairability), group in itertools.groupby(
        sorted(
            finding_rows,
            key=lambda row: (row["code"], row["severity"], row["repairability"]),
        ),
        key=lambda row: (row["code"], row["severity"], row["repairability"]),
    ):
        rows = list(group)
        type_rows.append({
            "code": code,
            "severity": severity,
            "repairability": repairability,
            "finding_count_all_apps": len(rows),
            "app_count_all_apps": len({row["app_name"] for row in rows}),
            "finding_count_candidate_40": sum(
                str(row["selected_for_candidate_40"]).lower() == "true" for row in rows
            ),
            "app_count_candidate_40": len({
                row["app_name"]
                for row in rows
                if row["selected_for_candidate_40"]
            }),
        })
    write_csv(output / "issue_type_coverage.csv", type_rows, list(type_rows[0]))

    candidate_payload = {
        "schema_version": 1,
        "dataset_id": f"android_xml_stratified_candidate_40_{detector_profile}",
        "status": "candidate_requires_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_uses_model_outputs": False,
        "detector_profile": detector_profile,
        "target_app_count": target,
        "selected_app_count": len(selected),
        "eligible_app_count": len(eligible),
        "shortfall": max(target - len(selected), 0),
        "selection_policy": {
            "detector_profile": detector_profile,
            "interfaces_per_app": "2-3",
            "screen_pool_per_app": MAX_SCREEN_POOL,
            "requires_xml_safe_error": True,
            "max_apps_per_primary_category": 2,
            "actual_max_apps_in_one_category_after_shortfall_relaxation": (
                actual_max_per_category
            ),
            "priorities": [
                "new XML-safe issue-code coverage",
                "rare XML-safe issue-code coverage",
                "new App category",
                "new overall finding-code coverage",
                "prefer no more than 20 XML-safe errors per App",
            ],
        },
        "apps": [
            {
                key: value
                for key, value in app.items()
                if key not in {"selected_issues", "selected_screens"}
            } | {
                "selected_screens": [
                    {
                        key: value
                        for key, value in screen.items()
                        if key not in {
                            "issue_code_counts",
                            "xml_safe_error_code_counts",
                            "repairability_counts",
                        }
                    }
                    for screen in app["selected_screens"]
                    if screen["selected"]
                ]
            }
            for app in selected
        ],
    }
    candidate_path = output / "candidate_40.json"
    candidate_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    xml_safe_types = [
        row for row in type_rows
        if row["severity"] == "error" and row["repairability"] == "xml_safe"
    ]
    all_selected_codes = {
        code for app in selected for code in app["issue_code_counts"]
    }
    selected_xml_codes = {
        code for app in selected for code in app["xml_safe_error_code_counts"]
    }
    report = {
        "schema_version": 1,
        "analysis_id": "android_xml_dataset_coverage_audit",
        "detector_profile": detector_profile,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_count": len(apps),
        "apps_with_xml_safe_errors": len(eligible),
        "candidate_app_count": len(selected),
        "candidate_category_count": len({app["category"] for app in selected}),
        "observed_finding_code_count": len({row["code"] for row in type_rows}),
        "observed_xml_safe_error_code_count": len(xml_safe_types),
        "observed_xml_safe_error_codes": [row["code"] for row in xml_safe_types],
        "candidate_finding_code_count": len(all_selected_codes),
        "candidate_xml_safe_error_code_count": len(selected_xml_codes),
        "candidate_xml_safe_error_codes": sorted(selected_xml_codes),
        "candidate_has_at_least_four_xml_safe_error_codes": (
            len(selected_xml_codes) >= 4
        ),
        "dataset_reselection_alone_creates_diverse_auto_repair_types": (
            detector_profile == DEFAULT_DETECTOR_PROFILE
            and len(selected_xml_codes) >= 4
        ),
        "model_outputs_used": False,
        "previous_dataset_comparison": previous_comparison,
    }
    (output / "coverage_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Android XML Dataset Coverage Audit",
        "",
        f"- Detector profile: `{report['detector_profile']}`",
        f"- Repositories scanned: {report['repository_count']}",
        f"- Apps with at least one XML-safe error: {report['apps_with_xml_safe_errors']}",
        f"- Candidate Apps selected: {report['candidate_app_count']} / {target}",
        f"- Candidate categories: {report['candidate_category_count']}",
        f"- All observed finding codes: {report['observed_finding_code_count']}",
        f"- XML-safe error codes: {report['observed_xml_safe_error_code_count']}",
        f"- Apps retained from the previous 40-App set: {previous_comparison['overlap_app_count']}",
        f"- Apps newly introduced: {previous_comparison['added_app_count']}",
        "",
        "## XML-safe auto-repair scope",
        "",
    ]
    for row in xml_safe_types:
        lines.append(
            f"- `{row['code']}`: {row['finding_count_all_apps']} findings in "
            f"{row['app_count_all_apps']} Apps"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        (
            "The expanded detector profile and dataset reselection together "
            "produced at least four XML-safe error types. Real-App false-positive "
            "review is still required before freezing the benchmark."
            if report["candidate_has_at_least_four_xml_safe_error_codes"]
            and detector_profile != DEFAULT_DETECTOR_PROFILE
            else (
                "Dataset reselection produced at least four XML-safe error types. "
                "The next step can freeze and review the new 40-App benchmark."
                if report["candidate_has_at_least_four_xml_safe_error_codes"]
                else "Dataset reselection did not produce four XML-safe error types. "
                "This means the current detector/repairability policy, not only the old App sample, limits automatic-repair diversity."
            )
        ),
        "",
        "No model output, repair result, or previous experiment metric was used for this selection.",
        "",
    ])
    (output / "coverage_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone-root", type=Path, default=DEFAULT_CLONE_ROOT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--screen-pool", type=int, default=MAX_SCREEN_POOL)
    parser.add_argument("--target", type=int, default=40)
    parser.add_argument("--max-per-category", type=int, default=2)
    parser.add_argument("--previous-plan", type=Path, default=DEFAULT_PREVIOUS_PLAN)
    parser.add_argument(
        "--detector-profile",
        choices=DETECTOR_PROFILES,
        default=DEFAULT_DETECTOR_PROFILE,
    )
    args = parser.parse_args()
    by_path, by_name = metadata_maps(args.metadata)
    repos = sorted(
        path
        for path in args.clone_root.iterdir()
        if path.is_dir() and (path / ".git").exists()
    )
    apps = []
    for index, repo in enumerate(repos, 1):
        metadata = by_path.get(str(repo.resolve())) or by_name.get(repo.name.casefold()) or {}
        apps.append(audit_repository(
            repo,
            metadata,
            args.screen_pool,
            detector_profile=args.detector_profile,
        ))
        if index % 10 == 0 or index == len(repos):
            print(f"[{index}/{len(repos)}] dataset coverage scan")
    selected, eligible, actual_max_per_category = select_apps(
        apps, args.target, args.max_per_category
    )
    previous_comparison = compare_previous_dataset(
        selected, args.previous_plan
    )
    report = write_outputs(
        args.output,
        apps,
        selected,
        eligible,
        args.target,
        actual_max_per_category,
        previous_comparison,
        detector_profile=args.detector_profile,
    )
    print(json.dumps({
        "repositories": report["repository_count"],
        "eligible_apps": report["apps_with_xml_safe_errors"],
        "selected_apps": report["candidate_app_count"],
        "finding_codes": report["observed_finding_code_count"],
        "xml_safe_error_codes": report["observed_xml_safe_error_code_count"],
        "candidate_meets_four_type_target": report[
            "candidate_has_at_least_four_xml_safe_error_codes"
        ],
        "dataset_only_sufficient": report[
            "dataset_reselection_alone_creates_diverse_auto_repair_types"
        ],
        "output": args.output.resolve().relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
