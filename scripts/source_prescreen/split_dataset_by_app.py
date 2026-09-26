#!/usr/bin/env python3
"""Create a leakage-resistant development/test split at repository level."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.common import (  # noqa: E402
    CANDIDATE_FIELDS,
    load_config,
    normalize_repo_url,
    read_csv,
    write_csv,
)


class UnionFind:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first, second):
        left, right = self.find(first), self.find(second)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def repository_key(row: dict) -> str:
    return normalize_repo_url(row.get("repository_url", "")) or row["package_name"].casefold()


def split_by_repository(rows: list[dict], development_ratio: float, seed: str = "source-prescreen-v2") -> dict[str, str]:
    repositories = sorted({repository_key(row) for row in rows})
    if not repositories:
        return {}
    union = UnionFind(repositories)
    by_dedup = defaultdict(set)
    for row in rows:
        if row.get("dedup_group"):
            by_dedup[row["dedup_group"]].add(repository_key(row))
    for repo_keys in by_dedup.values():
        values = sorted(repo_keys)
        for value in values[1:]:
            union.union(values[0], value)
    components = defaultdict(set)
    for repo in repositories:
        components[union.find(repo)].add(repo)
    target = max(1, round(len(repositories) * development_ratio)) if len(repositories) > 1 else 0
    ordered = sorted(
        components.values(),
        key=lambda group: hashlib.sha256((seed + "|" + "|".join(sorted(group))).encode()).hexdigest(),
    )
    development = set()
    for component in ordered:
        if len(development) >= target:
            break
        if len(development) + len(component) <= target or not development:
            development.update(component)
    if development == set(repositories) and len(ordered) > 1:
        development.difference_update(ordered[-1])
    return {
        repo: "development" if repo in development else "test"
        for repo in repositories
    }


def assert_no_split_leakage(rows: list[dict]) -> None:
    repo_splits = defaultdict(set)
    dedup_splits = defaultdict(set)
    for row in rows:
        repo_splits[repository_key(row)].add(row["dataset_split"])
        if row.get("dedup_group"):
            dedup_splits[row["dedup_group"]].add(row["dataset_split"])
    bad_repos = [key for key, values in repo_splits.items() if len(values) > 1]
    bad_groups = [key for key, values in dedup_splits.items() if len(values) > 1]
    if bad_repos or bad_groups:
        raise ValueError(f"split leakage: repositories={bad_repos}, dedup_groups={bad_groups}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed", default="source-prescreen-v2")
    args = parser.parse_args()
    config = load_config(args.config)
    rows = []
    for name in ("high_confidence_candidates.csv", "boundary_candidates.csv"):
        rows.extend(
            row for row in read_csv(args.output_root / name)
            if row.get("selection_status") == "included"
        )
    assignments = split_by_repository(
        rows,
        float(config["dataset_targets"]["development_ratio"]),
        args.seed,
    )
    for row in rows:
        row["dataset_split"] = assignments[repository_key(row)]
    assert_no_split_leakage(rows)
    write_csv(args.output_root / "split_candidates.csv", rows, CANDIDATE_FIELDS)
    assignment_rows = [
        {"repository_key": key, "dataset_split": value}
        for key, value in sorted(assignments.items())
    ]
    write_csv(
        args.output_root / "dataset_split_assignments.csv",
        assignment_rows,
        ["repository_key", "dataset_split"],
    )
    print(json.dumps({
        "repositories": len(assignments),
        "development": sum(value == "development" for value in assignments.values()),
        "test": sum(value == "test" for value in assignments.values()),
        "candidate_rows": len(rows),
        "leakage_check": "passed",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
