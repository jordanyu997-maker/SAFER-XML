#!/usr/bin/env python3
"""Shallow-clone only Android XML evidence needed by source prescreening."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.common import normalize_repo_url, safe_name  # noqa: E402


def clean_subdir(value: str) -> str:
    raw = str(value or "").strip().strip("/")
    path = Path(raw)
    if raw and (path.is_absolute() or ".." in path.parts):
        raise ValueError(f"unsafe F-Droid subdir: {value}")
    return path.as_posix() if raw else ""


def sparse_patterns(subdir: str = "") -> list[str]:
    prefix = clean_subdir(subdir)
    base = f"/{prefix}" if prefix else ""
    patterns = ["/*", "!/*/"]
    resource_types = ("layout*", "values*", "xml*")
    for resource_type in resource_types:
        patterns.extend([
            f"{base}/**/res/{resource_type}/",
            f"{base}/**/res/{resource_type}/**",
        ])
    patterns.extend([
        f"{base}/**/AndroidManifest.xml",
        f"{base}/**/*.gradle",
        f"{base}/**/*.gradle.kts",
        f"{base}/**/gradle.properties",
        f"{base}/**/libs.versions.toml",
        "/settings.gradle",
        "/settings.gradle.kts",
    ])
    return patterns


def clone_commands(row: dict, destination: Path, depth: int = 1) -> list[list[str]]:
    repository_url = row["repository_url"]
    commands = [[
        "git", "clone", "--depth", str(depth), "--filter=blob:none", "--no-tags",
        "--single-branch", "--no-checkout", repository_url, str(destination),
    ]]
    commit = str(row.get("commit_hash") or "").strip()
    if commit:
        commands.append([
            "git", "-C", str(destination), "fetch", "--depth", str(depth),
            "origin", commit,
        ])
    commands.extend([
        ["git", "-C", str(destination), "sparse-checkout", "init", "--no-cone"],
        [
            "git", "-C", str(destination), "sparse-checkout", "set", "--no-cone",
            *sparse_patterns(row.get("subdir", "")),
        ],
        (
            ["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"]
            if commit
            else ["git", "-C", str(destination), "checkout", "--force"]
        ),
    ])
    return commands


def run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def clone_one(row: dict, clone_root: Path, depth: int, timeout: int) -> dict:
    destination = clone_root / safe_name(f"{row['app_name']}-{row['package_name']}")
    result = {
        "package_name": row["package_name"],
        "app_name": row["app_name"],
        "repository_url": row["repository_url"],
        "commit_hash": row.get("commit_hash", ""),
        "subdir": row.get("subdir", ""),
        "local_path": str(destination),
        "status": "pending",
        "error": "",
    }
    if (destination / ".git").exists():
        result["status"] = "existing"
        return result
    if destination.exists():
        result.update(status="failed", error="destination exists and is not a Git repository")
        return result
    try:
        for command in clone_commands(row, destination, depth):
            completed = run_command(command, timeout)
            if completed.returncode:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        result.update(status="failed", error=str(exc)[-1500:])
        return result
    result["status"] = "cloned_sparse"
    return result


def read_inventory(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def deduplicate_clone_rows(rows: list[dict]) -> list[dict]:
    """Keep one transfer for an identical repository revision and subdirectory."""
    unique = {}
    for row in rows:
        key = (
            normalize_repo_url(row.get("repository_url", "")),
            str(row.get("commit_hash") or "").strip(),
            clean_subdir(row.get("subdir", "")),
        )
        unique.setdefault(key, row)
    return list(unique.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--clone-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    rows = deduplicate_clone_rows([
        row for row in read_inventory(args.inventory)
        if not row.get("existing_repository_path")
    ])
    rows = rows[: max(args.limit, 0)] if args.limit else rows
    if not args.execute:
        report = {
            "mode": "dry_run",
            "selected_repositories": len(rows),
            "network_used": False,
            "paid_api_used": False,
            "destinations": [
                str(args.clone_root / safe_name(f"{row['app_name']}-{row['package_name']}"))
                for row in rows
            ],
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    args.clone_root.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=max(args.jobs, 1)) as executor:
        futures = {
            executor.submit(clone_one, row, args.clone_root, args.depth, args.timeout): row
            for row in rows
        }
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(f"[{index}/{len(rows)}] {result['app_name']}: {result['status']}", file=sys.stderr)
    results.sort(key=lambda item: (item["app_name"].casefold(), item["package_name"]))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps({
            "schema_version": 1,
            "source_type": "fdroid_build_metadata",
            "paid_api_used": False,
            "requested_count": len(rows),
            "successful_count": sum(item["status"] in {"cloned_sparse", "existing"} for item in results),
            "failed_count": sum(item["status"] == "failed" for item in results),
            "results": results,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "requested_count": len(rows),
        "successful_count": sum(item["status"] in {"cloned_sparse", "existing"} for item in results),
        "failed_count": sum(item["status"] == "failed" for item in results),
        "report": str(args.report.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
