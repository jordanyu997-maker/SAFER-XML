#!/usr/bin/env python3
"""Build a model-free external V2 Test extension from unseen local sources."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.build_candidate_manifest import (  # noqa: E402
    sha256_file,
    snapshots_equal,
    v1_current_snapshot,
)
from scripts.source_prescreen.build_v2_frozen_dataset import (  # noqa: E402
    CONSISTENCY_FIELDS,
    V2_FIELDS,
    deduplicate_candidates,
    load_candidate_pool,
    normalized_xml_path,
    repository_key,
    stable_key,
    validate_pool,
)
from scripts.source_prescreen.common import (  # noqa: E402
    normalize_repo_url,
    read_csv,
    write_csv,
)
from tools.prepare_android_xml_v2_formal_study import (  # noqa: E402
    RESULT_LOCK_PATH,
    verify_result_lock,
)


VERSION = "v2.1-external-extension"
SEED = "android-xml-v2.1-external-extension-fixed-seed"
CURRENT_V2 = ROOT / "outputs/v2_dataset/v2.0.0"
CURRENT_MANIFEST = CURRENT_V2 / "v2_frozen_manifest.csv"
CURRENT_TEST = CURRENT_V2 / "v2_test.csv"
CURRENT_METADATA = CURRENT_V2 / "v2_dataset_metadata.json"
ELIGIBILITY_EXCLUSIONS = (
    ROOT
    / "experiments/android_xml_v2_rag/test_v2_1/"
    "test_eligibility_exclusions.csv"
)
DEFAULT_OUTPUT = ROOT / "outputs/v2_dataset/v2.1_external_extension"
TARGET_EXTERNAL_APPS = 13
DEFAULT_SHORTLIST_SIZE = 24
MAX_APP_CANDIDATES = 4
MAX_APP_XML = 3

APP_FIELDS = (
    "repository_key",
    "package_name",
    "app_name",
    "repository_url",
    "repository_path",
    "candidate_count",
    "xml_count",
    "issue_type_count",
    "issue_types",
    "difficulty_counts",
    "selection_status",
    "selection_reason",
)
LEAKAGE_FIELDS = (
    "check_name",
    "overlap_count",
    "status",
    "details",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def truth(value: object) -> bool:
    return str(value or "").strip().casefold() == "true"


def normalized_app_name(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def actual_model_result_csv(path: Path) -> bool:
    rows = read_csv(path)
    if not rows:
        return False
    fields = set(rows[0])
    return bool(fields & {"model", "requested_model", "provider"}) and bool(
        fields
        & {
            "group",
            "variant_key",
            "baseline_model_calls",
            "enhanced_model_calls",
            "model_calls",
        }
    )


def model_observed_app_names() -> tuple[set[str], list[str]]:
    """Read identities only, never model responses or outcome values."""
    names = set()
    files = []
    for path in sorted((ROOT / "experiments").rglob("*.csv")):
        if not actual_model_result_csv(path):
            continue
        files.append(path.relative_to(ROOT).as_posix())
        for row in read_csv(path):
            name = normalized_app_name(row.get("app_name", ""))
            if name:
                names.add(name)
    return names, files


def current_v2_identity() -> tuple[set[str], set[str], set[str]]:
    rows = read_csv(CURRENT_MANIFEST)
    return (
        {
            normalize_repo_url(row.get("repository_url", ""))
            for row in rows
            if row.get("repository_url")
        },
        {
            normalized_app_name(row.get("app_name", ""))
            for row in rows
            if row.get("app_name")
        },
        {row.get("dedup_group", "") for row in rows if row.get("dedup_group")},
    )


def repository_metadata_index(repository_index: dict) -> dict[str, dict]:
    return {
        key[1]: value
        for key, value in repository_index.items()
        if key[0] == "formal_scan_162"
        and not key[1].startswith("package:")
    }


def mark_excluded(row: dict, reason: str) -> dict:
    result = dict(row)
    result["selection_status"] = "excluded"
    result["exclusion_reason"] = reason
    return result


def eligible_unseen_pool() -> tuple[
    list[dict],
    list[dict],
    dict,
    dict,
]:
    pool, source_exclusions, repository_index = load_candidate_pool()
    current_urls, current_names, current_dedup = current_v2_identity()
    model_names, observed_files = model_observed_app_names()
    eligible = []
    exclusions = list(source_exclusions)
    for row in pool:
        reason = ""
        url = normalize_repo_url(row.get("repository_url", ""))
        name = normalized_app_name(row.get("app_name", ""))
        if row.get("source_dataset") != "formal_scan_162":
            reason = "not_from_formal_local_scan"
        elif row.get("candidate_role") != "xml_safe":
            reason = "boundary_not_used_to_reach_repair_app_target"
        elif url in current_urls or name in current_names:
            reason = "app_already_in_frozen_v2"
        elif name in model_names:
            reason = "app_already_observed_by_model_experiment"
        elif row.get("dedup_group") in current_dedup:
            reason = "layout_dedup_group_already_in_frozen_v2"
        if reason:
            exclusions.append(mark_excluded(row, reason))
        else:
            eligible.append(row)
    audit = {
        "model_observed_name_count": len(model_names),
        "identity_only_result_files": observed_files,
        "current_v2_repository_count": len(current_urls),
        "current_v2_app_name_count": len(current_names),
        "current_v2_dedup_group_count": len(current_dedup),
        "eligible_candidate_count": len(eligible),
        "eligible_app_count": len({
            repository_key(row) for row in eligible
        }),
        "selection_used_model_outcomes": False,
        "selection_used_model_response_content": False,
    }
    return eligible, exclusions, repository_index, audit


def shortlist_apps(
    rows: list[dict],
    size: int,
    seed: str = SEED,
) -> tuple[list[dict], list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[repository_key(row)].append(row)

    def rank(item):
        key, values = item
        xml_count = len({
            normalized_xml_path(row["xml_path"]) for row in values
        })
        types = {row["issue_type"] for row in values}
        non_easy = sum(
            row.get("difficulty") in {"medium", "hard"} for row in values
        )
        return (
            0 if xml_count >= 2 else 1,
            -len(types),
            -non_easy,
            -min(xml_count, MAX_APP_XML),
            hashlib.sha256(f"{seed}|{key}".encode()).hexdigest(),
        )

    ordered = sorted(grouped.items(), key=rank)
    selected_keys = {key for key, _ in ordered[:size]}
    selected = [
        row for row in rows if repository_key(row) in selected_keys
    ]
    excluded = [
        mark_excluded(row, "not_in_source_evidence_shortlist")
        for row in rows
        if repository_key(row) not in selected_keys
    ]
    return selected, excluded


def app_rows(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[repository_key(row)].append(row)
    return grouped


def select_external_apps(
    rows: list[dict],
    target: int,
    seed: str = SEED,
) -> tuple[list[str], list[str]]:
    grouped = app_rows(rows)
    eligible = {
        key: values
        for key, values in grouped.items()
        if len({
            normalized_xml_path(row["xml_path"]) for row in values
        }) >= 2
    }
    selected = []
    type_app_counts = Counter()
    while len(selected) < target and eligible:
        def rank(item):
            key, values = item
            types = {row["issue_type"] for row in values}
            undercovered = sum(type_app_counts[value] < 4 for value in types)
            non_easy = sum(
                row.get("difficulty") in {"medium", "hard"}
                for row in values
            )
            xml_count = len({
                normalized_xml_path(row["xml_path"]) for row in values
            })
            return (
                -undercovered,
                -len(types),
                -non_easy,
                -min(xml_count, MAX_APP_XML),
                stable_key(values[0], f"{seed}|app"),
            )

        key, values = min(eligible.items(), key=rank)
        selected.append(key)
        type_app_counts.update({row["issue_type"] for row in values})
        del eligible[key]
    rejected = sorted(set(grouped) - set(selected))
    return selected, rejected


def select_rows_for_app(
    rows: list[dict],
    seed: str = SEED,
) -> list[dict]:
    variants_by_xml = defaultdict(lambda: defaultdict(list))
    for row in rows:
        variants_by_xml[normalized_xml_path(row["xml_path"])][
            row["xml_path"]
        ].append(row)

    # One normalized screen maps to one physical variant. Prefer the
    # unqualified layout, then rank remaining variants deterministically.
    by_xml = {}
    for xml_key, variants in variants_by_xml.items():
        _, values = min(
            variants.items(),
            key=lambda item: (
                0 if "/res/layout/" in item[0].replace("\\", "/") else 1,
                -len({row["issue_type"] for row in item[1]}),
                -sum(
                    row.get("difficulty") in {"medium", "hard"}
                    for row in item[1]
                ),
                hashlib.sha256(
                    f"{seed}|variant|{item[0]}".encode()
                ).hexdigest(),
            ),
        )
        by_xml[xml_key] = values

    def xml_rank(item):
        key, values = item
        return (
            -len({row["issue_type"] for row in values}),
            -sum(
                row.get("difficulty") in {"medium", "hard"}
                for row in values
            ),
            hashlib.sha256(f"{seed}|xml|{key}".encode()).hexdigest(),
        )

    chosen_xml = [
        key for key, _ in sorted(by_xml.items(), key=xml_rank)[:MAX_APP_XML]
    ]
    selected = []
    seen_types = Counter()
    for xml_key in chosen_xml:
        choice = min(
            by_xml[xml_key],
            key=lambda row: (
                seen_types[row["issue_type"]],
                {"hard": 0, "medium": 1, "easy": 2}.get(
                    row.get("difficulty"),
                    3,
                ),
                stable_key(row, f"{seed}|first-per-xml"),
            ),
        )
        selected.append(choice)
        seen_types[choice["issue_type"]] += 1

    selected_ids = {row["candidate_id"] for row in selected}
    remaining = [
        row
        for xml_key in chosen_xml
        for row in by_xml[xml_key]
        if row["candidate_id"] not in selected_ids
    ]
    while len(selected) < MAX_APP_CANDIDATES and remaining:
        choice = min(
            remaining,
            key=lambda row: (
                seen_types[row["issue_type"]],
                {"hard": 0, "medium": 1, "easy": 2}.get(
                    row.get("difficulty"),
                    3,
                ),
                stable_key(row, f"{seed}|app-fill"),
            ),
        )
        selected.append(choice)
        selected_ids.add(choice["candidate_id"])
        seen_types[choice["issue_type"]] += 1
        remaining = [
            row for row in remaining
            if row["candidate_id"] != choice["candidate_id"]
        ]
    return selected


def leakage_report(
    selected: list[dict],
    observed_names: set[str],
) -> list[dict]:
    current_rows = read_csv(CURRENT_MANIFEST)
    definitions = {
        "repository": (
            {
                normalize_repo_url(row.get("repository_url", ""))
                for row in current_rows
            },
            {
                normalize_repo_url(row.get("repository_url", ""))
                for row in selected
            },
        ),
        "app_name": (
            {
                normalized_app_name(row.get("app_name", ""))
                for row in current_rows
            },
            {
                normalized_app_name(row.get("app_name", ""))
                for row in selected
            },
        ),
        "dedup_group": (
            {row.get("dedup_group", "") for row in current_rows},
            {row.get("dedup_group", "") for row in selected},
        ),
        "prior_model_observation": (
            observed_names,
            {
                normalized_app_name(row.get("app_name", ""))
                for row in selected
            },
        ),
    }
    result = []
    for name, (left, right) in definitions.items():
        overlap = sorted((left & right) - {""})
        result.append({
            "check_name": name,
            "overlap_count": len(overlap),
            "status": "passed" if not overlap else "failed",
            "details": json.dumps(overlap, ensure_ascii=False),
        })
    return result


def app_distribution(
    rows: list[dict],
    selected_keys: set[str],
) -> list[dict]:
    result = []
    for key, values in sorted(app_rows(rows).items()):
        types = sorted({row["issue_type"] for row in values})
        result.append({
            "repository_key": key,
            "package_name": values[0]["package_name"],
            "app_name": values[0]["app_name"],
            "repository_url": values[0]["repository_url"],
            "repository_path": values[0].get("repository_path", ""),
            "candidate_count": len(values),
            "xml_count": len({
                normalized_xml_path(row["xml_path"]) for row in values
            }),
            "issue_type_count": len(types),
            "issue_types": ";".join(types),
            "difficulty_counts": json.dumps(
                Counter(row["difficulty"] for row in values),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "selection_status": (
                "included" if key in selected_keys else "excluded"
            ),
            "selection_reason": (
                "deterministic_source_evidence_selection"
                if key in selected_keys
                else "not_selected_after_consistency_audit"
            ),
        })
    return result


def combined_manifest(external: list[dict]) -> list[dict]:
    excluded_ids = {
        row["candidate_id"] for row in read_csv(ELIGIBILITY_EXCLUSIONS)
    }
    current = [
        {
            **row,
            "source_partition": "existing_v2_test",
        }
        for row in read_csv(CURRENT_TEST)
        if row.get("candidate_role") == "xml_safe"
        and row["candidate_id"] not in excluded_ids
    ]
    added = [
        {
            **row,
            "source_partition": "external_extension",
        }
        for row in external
    ]
    return current + added


def write_checksums(output: Path) -> dict[str, str]:
    values = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            values[path.name] = sha256_file(path)
    content = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(values.items())
    )
    (output / "checksums.sha256").write_text(content, encoding="ascii")
    return values


def build(
    output: Path,
    target_apps: int,
    shortlist_size: int,
) -> dict:
    if output.exists() and any(output.iterdir()):
        raise SystemExit(
            f"external extension output already exists: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    before_v1 = v1_current_snapshot()
    current_v2_hash = sha256_file(CURRENT_MANIFEST)
    current_v2_metadata_hash = sha256_file(CURRENT_METADATA)
    result_lock_errors = verify_result_lock()
    if result_lock_errors:
        raise SystemExit(
            "prior V2 Test result lock failed:\n- "
            + "\n- ".join(result_lock_errors)
        )

    pool, exclusions, repository_index, identity_audit = (
        eligible_unseen_pool()
    )
    shortlisted, shortlist_exclusions = shortlist_apps(
        pool,
        shortlist_size,
    )
    exclusions.extend(shortlist_exclusions)
    validated, consistency_exclusions, consistency = validate_pool(
        shortlisted,
        repository_index,
    )
    exclusions.extend(consistency_exclusions)
    deduplicated, duplicate_exclusions = deduplicate_candidates(
        validated,
        SEED,
    )
    exclusions.extend(duplicate_exclusions)

    selected_apps, rejected_apps = select_external_apps(
        deduplicated,
        target_apps,
    )
    if len(selected_apps) < target_apps:
        raise SystemExit(
            f"only {len(selected_apps)} audited apps have at least two XMLs; "
            f"target={target_apps}"
        )
    grouped = app_rows(deduplicated)
    selected = []
    for key in selected_apps:
        selected.extend(select_rows_for_app(grouped[key], f"{SEED}|{key}"))
    selected_ids = {row["candidate_id"] for row in selected}
    for row in deduplicated:
        if row["candidate_id"] not in selected_ids:
            reason = (
                "app_not_selected_for_external_extension"
                if repository_key(row) in rejected_apps
                else "candidate_above_per_app_or_xml_cap"
            )
            exclusions.append(mark_excluded(row, reason))

    for row in selected:
        row.update({
            "selection_status": "included",
            "dataset_split": "external_test",
            "frozen_dataset_version": VERSION,
            "consistency_status": "passed",
            "exclusion_reason": "",
        })

    observed_names, observed_files = model_observed_app_names()
    leakage = leakage_report(selected, observed_names)
    after_v1 = v1_current_snapshot()
    v1_unchanged = snapshots_equal(before_v1, after_v1)
    selected_app_count = len({
        repository_key(row) for row in selected
    })
    selected_xml_count = len({
        (repository_key(row), normalized_xml_path(row["xml_path"]))
        for row in selected
    })
    all_consistent = all(
        row.get("consistency_status") == "passed" for row in selected
    )
    current_v2_unchanged = (
        sha256_file(CURRENT_MANIFEST) == current_v2_hash
        and sha256_file(CURRENT_METADATA) == current_v2_metadata_hash
    )
    hard_checks = {
        "target_external_app_count_met": selected_app_count == target_apps,
        "minimum_two_xml_per_external_app": all(
            len({
                normalized_xml_path(row["xml_path"])
                for row in selected
                if repository_key(row) == key
            }) >= 2
            for key in selected_apps
        ),
        "all_selected_source_consistency_passed": all_consistent,
        "no_current_v2_or_prior_model_leakage": all(
            row["status"] == "passed" for row in leakage
        ),
        "current_v2_hashes_unchanged": current_v2_unchanged,
        "v1_hashes_unchanged": v1_unchanged,
        "prior_rag_test_result_lock_unchanged": not verify_result_lock(),
    }
    status = (
        "frozen"
        if all(hard_checks.values())
        else "failed_not_frozen"
    )

    write_csv(
        output / "external_xml_safe_candidates.csv",
        selected,
        V2_FIELDS,
    )
    write_csv(
        output / "source_consistency_report.csv",
        consistency,
        CONSISTENCY_FIELDS,
    )
    write_csv(
        output / "selection_exclusions.csv",
        exclusions,
        V2_FIELDS,
    )
    apps = app_distribution(
        deduplicated,
        set(selected_apps),
    )
    write_csv(output / "app_distribution.csv", apps, APP_FIELDS)
    write_csv(
        output / "leakage_check.csv",
        leakage,
        LEAKAGE_FIELDS,
    )
    combined = combined_manifest(selected)
    combined_fields = list(V2_FIELDS) + ["source_partition"]
    write_csv(
        output / "combined_40_app_xml_safe_manifest.csv",
        combined,
        combined_fields,
    )

    type_counts = Counter(row["issue_type"] for row in selected)
    type_apps = {
        issue_type: len({
            repository_key(row)
            for row in selected
            if row["issue_type"] == issue_type
        })
        for issue_type in type_counts
    }
    combined_apps = {
        repository_key(row) for row in combined
    }
    metadata = {
        "schema_version": 1,
        "dataset_version": VERSION,
        "status": status,
        "created_at": now_iso(),
        "selection_policy": {
            "source_evidence_only": True,
            "model_api_calls": 0,
            "model_outcomes_used": False,
            "model_response_content_read": False,
            "prior_model_app_identity_used_only_for_exclusion": True,
            "fixed_seed": SEED,
        },
        "target_external_app_count": target_apps,
        "shortlist_app_count": len({
            repository_key(row) for row in shortlisted
        }),
        "external_app_count": selected_app_count,
        "external_xml_count": selected_xml_count,
        "external_candidate_count": len(selected),
        "external_issue_type_counts": dict(sorted(type_counts.items())),
        "external_issue_type_app_counts": dict(sorted(type_apps.items())),
        "existing_v2_repair_app_count": 27,
        "combined_repair_app_count": len(combined_apps),
        "combined_xml_safe_candidate_count": len(combined),
        "identity_audit": {
            **identity_audit,
            "identity_only_result_files": observed_files,
        },
        "hard_checks": hard_checks,
        "current_v2_manifest_sha256": current_v2_hash,
        "current_v2_metadata_sha256": current_v2_metadata_hash,
        "prior_result_lock_sha256": sha256_file(RESULT_LOCK_PATH),
        "v1_before": before_v1,
        "v1_after": after_v1,
    }
    write_json(output / "external_dataset_metadata.json", metadata)

    exclusion_counts = Counter(
        row.get("exclusion_reason", "unknown") for row in exclusions
    )
    report = [
        "# V2.1 外部 Test 扩展集报告",
        "",
        "## 结论",
        "",
        f"- 状态：`{status}`",
        f"- 新增可修复 App：{selected_app_count}",
        f"- 新增 XML：{selected_xml_count}",
        f"- 新增高置信 XML-safe 问题：{len(selected)}",
        f"- 合并后可修复 Test App：{len(combined_apps)}",
        f"- 合并后 XML-safe 问题：{len(combined)}",
        "- 付费模型调用：0",
        "- 模型结果用于选择：否",
        "",
        "## 新增问题类型",
        "",
        "| 类型 | 问题数 | App 来源 |",
        "|---|---:|---:|",
    ]
    for issue_type in sorted(type_counts):
        report.append(
            f"| {issue_type} | {type_counts[issue_type]} | "
            f"{type_apps[issue_type]} |"
        )
    report.extend((
        "",
        "## 硬性检查",
        "",
    ))
    for name, passed in hard_checks.items():
        report.append(f"- `{name}`：{'通过' if passed else '失败'}")
    report.extend((
        "",
        "## 排除记录",
        "",
    ))
    for reason, count in sorted(exclusion_counts.items()):
        report.append(f"- `{reason}`：{count}")
    (output / "EXTERNAL_EXTENSION_REPORT_ZH.md").write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )
    checksums = write_checksums(output)
    metadata["checksums"] = checksums
    write_json(output / "external_dataset_metadata.json", metadata)
    write_checksums(output)
    return metadata


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--target-apps", type=int, default=TARGET_EXTERNAL_APPS)
    result.add_argument(
        "--shortlist-size",
        type=int,
        default=DEFAULT_SHORTLIST_SIZE,
    )
    return result


def main() -> None:
    args = parser().parse_args()
    if args.target_apps < 1:
        raise SystemExit("--target-apps must be positive")
    if args.shortlist_size < args.target_apps:
        raise SystemExit("--shortlist-size must be at least --target-apps")
    result = build(
        args.output.resolve(),
        args.target_apps,
        args.shortlist_size,
    )
    print(json.dumps({
        "status": result["status"],
        "external_app_count": result["external_app_count"],
        "external_xml_count": result["external_xml_count"],
        "external_candidate_count": result["external_candidate_count"],
        "combined_repair_app_count": result[
            "combined_repair_app_count"
        ],
        "model_api_calls": 0,
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
