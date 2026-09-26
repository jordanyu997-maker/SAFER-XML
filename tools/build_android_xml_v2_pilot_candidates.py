#!/usr/bin/env python3
"""Prepare auditable, non-executable candidate inputs for the V2 pilot."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENING = (
    ROOT / "experiments/android_xml_v2_design/pilot_screening_current/selected_apps.json"
)
DEFAULT_FORMAL_PLAN = ROOT / "experiments/android_xml_multimodel/formal_experiment_plan.json"
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_design/pilot_candidates"
CANDIDATE_NAMES = (
    "Rootless Pixel Launcher",
    "app.simple.felicity",
    "Com-Phone",
    "sub rosa",
    "ch.threema.app.libre",
)

sys.path.insert(0, str(ROOT))

from tools.evaluation.android_xml_a11y_check import build_report, scan  # noqa: E402
from tools.evaluation.collect_android_xml_package import collect  # noqa: E402


def slug(value):
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return normalized or "app"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root):
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), len(files)


def git_value(source, *args):
    completed = subprocess.run(
        ["git", "-C", str(source), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def source_paths_from_v1(plan_path):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return {
        str(Path(subject["source_path"]).resolve())
        for subject in plan.get("subjects", [])
        if subject.get("source_path")
    }


def selected_res_dir(source, screens):
    roots = set()
    for screen in screens:
        relative = Path(screen["relative_path"])
        layout_index = next(
            (
                index
                for index, part in enumerate(relative.parts)
                if part.startswith("layout")
            ),
            None,
        )
        if layout_index is None:
            raise ValueError(f"Selected screen is not under a layout directory: {relative}")
        roots.add((source / Path(*relative.parts[:layout_index])).resolve())
    if len(roots) != 1:
        raise ValueError(f"Selected screens span multiple res directories: {sorted(roots)}")
    res_dir = roots.pop()
    if res_dir.name != "res" or not res_dir.is_dir():
        raise FileNotFoundError(f"Selected Android res directory does not exist: {res_dir}")
    return res_dir


def screen_counts(report, layout_names):
    counts = {name: Counter() for name in layout_names}
    for issue in report.get("issues", []):
        name = Path(issue.get("file", "")).stem
        if name in counts:
            counts[name][issue.get("severity", "error")] += 1
    return {
        name: {
            "error_count": values["error"],
            "warning_count": values["warning"],
            "info_count": values["info"],
        }
        for name, values in counts.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening", type=Path, default=DEFAULT_SCREENING)
    parser.add_argument("--formal-plan", type=Path, default=DEFAULT_FORMAL_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    screening = json.loads(args.screening.read_text(encoding="utf-8"))
    by_name = {app["name"]: app for app in screening.get("apps", [])}
    missing = [name for name in CANDIDATE_NAMES if name not in by_name]
    if missing:
        raise SystemExit(f"Missing screened candidates: {', '.join(missing)}")
    v1_sources = source_paths_from_v1(args.formal_plan)
    args.output.mkdir(parents=True, exist_ok=True)
    inputs_root = args.output / "inputs"
    reports_root = args.output / "reports"
    inputs_root.mkdir(exist_ok=True)
    reports_root.mkdir(exist_ok=True)
    candidates = []
    total_counts = Counter()
    for name in CANDIDATE_NAMES:
        app = by_name[name]
        source = Path(app["local_path"]).resolve()
        if str(source) in v1_sources:
            raise SystemExit(f"Candidate is present in V1: {name}")
        layout_names = [screen["name"] for screen in app["selected_screens"]]
        package = inputs_root / slug(name)
        res_dir = selected_res_dir(source, app["selected_screens"])
        collect(res_dir, package, force=True, selected_layouts=set(layout_names))
        report = build_report(scan([package / "res"]))
        report_path = reports_root / f"{slug(name)}.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        resource_hash, resource_file_count = tree_digest(package / "res")
        git_status = git_value(source, "status", "--porcelain")
        counts = {
            key: report[key]
            for key in (
                "error_count",
                "warning_count",
                "info_count",
                "total_issue_count",
            )
        }
        total_counts.update({key: value for key, value in counts.items()})
        candidates.append({
            "app_id": app.get("app_id"),
            "app_name": name,
            "category": app.get("category"),
            "repo_url": app.get("repo_url"),
            "source_path": str(source),
            "source_commit": git_value(source, "rev-parse", "HEAD"),
            "source_dirty": bool(git_status),
            "source_status_porcelain": git_status or "",
            "selected_res_path": str(res_dir),
            "confirmed_unseen_in_v1": True,
            "layouts": layout_names,
            "interface_count": len(layout_names),
            "screen_selection_basis": [
                {
                    "name": screen["name"],
                    "relative_path": screen["relative_path"],
                    "score": screen.get("score"),
                    "reasons": screen.get("reasons", []),
                }
                for screen in app["selected_screens"]
            ],
            "detector_counts": counts,
            "per_screen_counts": screen_counts(report, layout_names),
            "input_package": package.relative_to(ROOT).as_posix(),
            "input_resource_file_count": resource_file_count,
            "input_resource_sha256": resource_hash,
            "detector_report": report_path.relative_to(ROOT).as_posix(),
        })
    manifest = {
        "schema_version": 1,
        "candidate_set_id": "android_xml_v2_internal_pilot_candidates",
        "status": "candidate_not_frozen_requires_teacher_approval",
        "execution_enabled": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_policy": {
            "source": "existing F-Droid source repositories",
            "unseen_in_v1": True,
            "categories_must_be_distinct": True,
            "interfaces_selected_by_static_screen_role_before_model_generation": True,
            "minimum_current_xml_safe_errors_per_app": 1,
            "model_outputs_or_metrics_used_for_selection": False,
            "purpose": "internal debugging pilot, not formal hypothesis testing",
        },
        "app_count": len(candidates),
        "interface_count": sum(item["interface_count"] for item in candidates),
        "detector_totals": dict(total_counts),
        "candidates": candidates,
    }
    manifest_path = args.output / "candidate_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    readme_path = args.output / "README.md"
    lines = [
        "# Android XML V2 Pilot Candidates",
        "",
        "Status: candidate only. Model execution is disabled until the supervisor approves the V2 protocol.",
        "",
        "| App | Category | Interfaces | Errors | Warnings |",
        "|---|---|---:|---:|---:|",
    ]
    for item in candidates:
        counts = item["detector_counts"]
        lines.append(
            f"| {item['app_name']} | {item['category']} | {item['interface_count']} | "
            f"{counts['error_count']} | {counts['warning_count']} |"
        )
    lines.extend([
        "",
        "The set contains one stress-test App and four small cases. Report both micro-averaged and per-App macro-averaged outcomes so the stress-test App cannot dominate the conclusion.",
        "",
    ])
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "apps": manifest["app_count"],
        "interfaces": manifest["interface_count"],
        "errors": manifest["detector_totals"].get("error_count", 0),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "readme": readme_path.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
