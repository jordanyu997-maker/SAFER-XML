#!/usr/bin/env python3
"""Parse F-Droid build metadata into a source-oriented repository inventory."""
from __future__ import annotations

import argparse
import configparser
import json
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.common import (  # noqa: E402
    normalize_repo_url,
    write_csv,
)


METADATA_FIELDS = (
    "package_name",
    "app_name",
    "repository_url",
    "repo_type",
    "source_code_url",
    "commit_hash",
    "subdir",
    "version_name",
    "version_code",
    "categories",
    "license",
    "metadata_path",
    "existing_repository_path",
    "metadata_status",
)


def active_build(data: dict) -> dict:
    builds = [item for item in (data.get("Builds") or []) if isinstance(item, dict)]
    enabled = [item for item in builds if not item.get("disable")]
    pool = enabled or builds
    if not pool:
        return {}

    def build_key(item):
        try:
            version_code = int(item.get("versionCode", -1))
        except (TypeError, ValueError):
            version_code = -1
        return version_code, str(item.get("versionName") or "")

    return max(pool, key=build_key)


def parse_metadata_file(path: Path) -> dict | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    repo_type = str(data.get("RepoType") or "").strip()
    repository_url = str(data.get("Repo") or "").strip()
    if repo_type != "git" or not repository_url.startswith(("https://", "http://")):
        return None
    build = active_build(data)
    categories = data.get("Categories") or []
    if isinstance(categories, str):
        categories = [categories]
    package_name = path.stem
    return {
        "package_name": str(build.get("applicationId") or package_name),
        "app_name": str(data.get("Name") or data.get("AutoName") or package_name),
        "repository_url": repository_url,
        "repo_type": repo_type,
        "source_code_url": str(data.get("SourceCode") or repository_url),
        "commit_hash": str(build.get("commit") or ""),
        "subdir": str(build.get("subdir") or ""),
        "version_name": str(data.get("CurrentVersion") or build.get("versionName") or ""),
        "version_code": str(data.get("CurrentVersionCode") or build.get("versionCode") or ""),
        "categories": "|".join(str(item) for item in categories),
        "license": str(data.get("License") or "Unknown"),
        "metadata_path": str(path.resolve()),
        "existing_repository_path": "",
        "metadata_status": "active" if not data.get("Disabled") else "disabled",
    }


def parse_metadata_root(metadata_root: Path) -> list[dict]:
    rows = []
    for path in sorted(metadata_root.glob("*.yml")):
        row = parse_metadata_file(path)
        if row and row["metadata_status"] == "active":
            rows.append(row)
    return rows


def repository_origins(existing_root: Path | None) -> dict[str, str]:
    if not existing_root or not existing_root.exists():
        return {}
    result = {}
    for git_dir in existing_root.glob("*/.git"):
        config = configparser.RawConfigParser()
        try:
            config.read(git_dir / "config", encoding="utf-8")
            origin = config.get('remote "origin"', "url", fallback="")
        except (configparser.Error, OSError):
            origin = ""
        if origin:
            result[normalize_repo_url(origin)] = str(git_dir.parent.resolve())
    return result


def attach_existing_paths(rows: list[dict], existing_root: Path | None) -> list[dict]:
    origins = repository_origins(existing_root)
    for row in rows:
        row["existing_repository_path"] = origins.get(
            normalize_repo_url(row["repository_url"]), ""
        )
    return rows


def update_metadata_repository(metadata_root: Path) -> None:
    repo = metadata_root.parent
    if not (repo / ".git").exists():
        raise ValueError(f"metadata root is not inside a Git checkout: {metadata_root}")
    completed = subprocess.run(
        ["git", "-C", str(repo), "pull", "--ff-only", "--depth", "1"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "F-Droid metadata update failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--existing-root", type=Path)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    if args.update:
        update_metadata_repository(args.metadata_root)
    rows = attach_existing_paths(
        parse_metadata_root(args.metadata_root),
        args.existing_root,
    )
    write_csv(args.output, rows, METADATA_FIELDS)
    print(json.dumps({
        "metadata_records": len(rows),
        "existing_repositories_matched": sum(bool(row["existing_repository_path"]) for row in rows),
        "output": str(args.output.resolve()),
        "network_used": bool(args.update),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
