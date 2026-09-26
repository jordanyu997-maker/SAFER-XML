#!/usr/bin/env python3
"""Clone a balanced batch from the fixed targeted F-Droid acquisition plan."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = (
    ROOT
    / "experiments/android_xml_dataset_redesign/fdroid_targeted_acquisition/targeted_app_acquisition_plan.json"
)
DEFAULT_CLONE_ROOT = Path("fdroid_apps/selected_xml_apps")
DEFAULT_REPORT = (
    ROOT
    / "experiments/android_xml_dataset_redesign/fdroid_targeted_acquisition/clone_results.json"
)

sys.path.insert(0, str(ROOT))

from tools.dataset.fdroid_app_screening import (  # noqa: E402
    FdroidApp,
    clone_repository,
    destination_for,
    existing_repo_map,
    normalize_repo_url,
)


def balanced_batch(apps, limit=0, allowed_codes=None):
    filtered = []
    for app in apps:
        if app.get("include_for_clone") is False:
            continue
        if app.get("source_verification") == "excluded_non_xml":
            continue
        codes = [
            code for code in app.get("selected_for_codes", [])
            if not allowed_codes or code in allowed_codes
        ]
        if codes:
            item = dict(app)
            item["selected_for_codes"] = codes
            filtered.append(item)
    if not limit or limit >= len(filtered):
        return filtered

    queues = {}
    for code in sorted({code for item in filtered for code in item["selected_for_codes"]}):
        queues[code] = sorted(
            (item for item in filtered if code in item["selected_for_codes"]),
            key=lambda item: (
                -item.get("target_scores", {}).get(code, 0),
                item["app_name"].casefold(),
            ),
        )
    positions = Counter()
    chosen = []
    chosen_ids = set()
    while len(chosen) < limit:
        progress = False
        for code in sorted(queues):
            queue = queues[code]
            while positions[code] < len(queue):
                item = queue[positions[code]]
                positions[code] += 1
                if item["app_id"] in chosen_ids:
                    continue
                chosen.append(item)
                chosen_ids.add(item["app_id"])
                progress = True
                break
            if len(chosen) >= limit:
                break
        if not progress:
            break
    return chosen


def as_fdroid_app(item):
    return FdroidApp(
        app_id=item["app_id"],
        name=item["app_name"],
        categories=item.get("categories") or ["Uncategorized"],
        license=item.get("license", "Unknown"),
        repo_url=item["repo_url"],
        source_code_url=item.get("source_code_url") or item["repo_url"],
        metadata_file=item.get("metadata_file", ""),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--clone-root", type=Path, default=DEFAULT_CLONE_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=24, help="0 clones all candidates")
    parser.add_argument("--codes", help="Comma-separated finding codes")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform network cloning. Without this flag, only print the batch.",
    )
    args = parser.parse_args()

    payload = json.loads(args.plan.read_text(encoding="utf-8"))
    allowed_codes = (
        {item.strip() for item in args.codes.split(",") if item.strip()}
        if args.codes else None
    )
    batch = balanced_batch(payload.get("apps", []), args.limit, allowed_codes)
    preview = {
        "selected_count": len(batch),
        "selected_by_type": dict(Counter(
            code for item in batch for code in item["selected_for_codes"]
        )),
        "apps": [item["app_name"] for item in batch],
    }
    if not args.execute:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        print("Add --execute to clone this fixed batch.")
        return

    args.clone_root.mkdir(parents=True, exist_ok=True)
    existing = existing_repo_map(args.clone_root)
    reserved = {
        path.name.casefold() for path in args.clone_root.iterdir() if path.is_dir()
    }
    jobs = []
    for item in batch:
        app = as_fdroid_app(item)
        current = existing.get(normalize_repo_url(app.repo_url))
        destination = current or destination_for(app, args.clone_root, reserved)
        jobs.append((item, app, destination, bool(current)))

    results = []
    with ThreadPoolExecutor(max_workers=max(args.jobs, 1)) as executor:
        futures = {}
        for item, app, destination, already_present in jobs:
            if already_present:
                results.append({
                    "app_id": app.app_id,
                    "app_name": app.name,
                    "repo_url": app.repo_url,
                    "local_path": str(destination),
                    "status": "existing",
                    "error": "",
                    "selected_for_codes": item["selected_for_codes"],
                })
                continue
            future = executor.submit(
                clone_repository,
                app,
                destination,
                args.timeout,
            )
            futures[future] = (item, app, destination)
        for future in as_completed(futures):
            item, app, destination = futures[future]
            try:
                status, error = future.result()
            except Exception as exc:  # pragma: no cover - process boundary
                status, error = "failed", str(exc)
            results.append({
                "app_id": app.app_id,
                "app_name": app.name,
                "repo_url": app.repo_url,
                "local_path": str(destination),
                "status": status,
                "error": error,
                "selected_for_codes": item["selected_for_codes"],
            })
            print(f"[{len(results)}/{len(jobs)}] {app.name}: {status}", file=sys.stderr)

    results.sort(key=lambda item: item["app_name"].casefold())
    report = {
        "schema_version": 1,
        "plan_id": payload.get("plan_id"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "selection_uses_model_outputs": False,
        "requested_count": len(batch),
        "successful_or_existing_count": sum(
            item["status"] in {"cloned", "existing"} for item in results
        ),
        "failed_count": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "requested_count": report["requested_count"],
        "successful_or_existing_count": report["successful_or_existing_count"],
        "failed_count": report["failed_count"],
        "report": str(args.report.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
