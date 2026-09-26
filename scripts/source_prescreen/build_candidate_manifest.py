#!/usr/bin/env python3
"""Build an auditable V2 source-prescreen candidate manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.analyze_candidate_distribution import write_analysis  # noqa: E402
from scripts.source_prescreen.common import (  # noqa: E402
    CANDIDATE_FIELDS,
    ensure_output_is_v2,
    load_config,
    normalize_repo_url,
    resolve_project_path,
    write_csv,
)
from scripts.source_prescreen.fetch_fdroid_metadata import (  # noqa: E402
    METADATA_FIELDS,
    attach_existing_paths,
    parse_metadata_root,
)
from scripts.source_prescreen.scan_android_xml import (  # noqa: E402
    REPOSITORY_FIELDS,
    XML_FIELDS,
    classify_repository,
    git_value,
    repository_origin,
    scan_repository,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def v1_current_snapshot() -> dict:
    manifest_path = ROOT / "experiments/android_xml_v1_freeze/manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for frozen in payload.get("files", []):
        path = ROOT / frozen["path"]
        current_hash = sha256_file(path) if path.exists() else "missing"
        records.append({
            "path": frozen["path"],
            "frozen_sha256": frozen["sha256"],
            "current_sha256": current_hash,
            "matches_frozen_manifest": current_hash == frozen["sha256"],
        })
    return {
        "freeze_id": payload.get("freeze_id"),
        "status": payload.get("status"),
        "records": records,
        "preexisting_mismatch_count": sum(not item["matches_frozen_manifest"] for item in records),
    }


def snapshots_equal(before: dict, after: dict) -> bool:
    return {
        item["path"]: item["current_sha256"] for item in before["records"]
    } == {
        item["path"]: item["current_sha256"] for item in after["records"]
    }


def inventory_existing_repositories(repository_root: Path, compose_limit: int) -> list[dict]:
    rows = []
    for repository in sorted(repository_root.glob("*")):
        if not repository.is_dir() or not (repository / ".git").exists():
            continue
        classification = classify_repository(repository, compose_file_limit=compose_limit)
        rows.append({
            "package_name": repository.name,
            "app_name": repository.name,
            "repository_url": repository_origin(repository),
            "repository_path": str(repository.resolve()),
            "commit_hash": git_value(repository, "rev-parse", "HEAD"),
            "subdir": "",
            "repository_status": "inventory_only",
            **classification,
            "res_root_count": 0,
            "high_candidate_count": 0,
            "review_candidate_count": 0,
            "boundary_candidate_count": 0,
            "scan_seconds": 0,
            "scan_error": "",
        })
    return rows


def choose_repositories(
    inventory: list[dict],
    repository_names: list[str],
    limit: int,
) -> list[dict]:
    if repository_names:
        wanted = {name.casefold() for name in repository_names}
        selected = [
            row for row in inventory
            if row["app_name"].casefold() in wanted
            or Path(row["repository_path"]).name.casefold() in wanted
        ]
        found = {
            value.casefold()
            for row in selected
            for value in (row["app_name"], Path(row["repository_path"]).name)
        }
        missing = sorted(name for name in repository_names if name.casefold() not in found)
        if missing:
            raise ValueError("dry-run repositories not found: " + ", ".join(missing))
        return selected
    eligible = [row for row in inventory if row["source_classification"] == "traditional_xml"]
    return eligible[:limit]


def metadata_maps(rows: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    by_origin = defaultdict(list)
    by_path = defaultdict(list)
    for row in rows:
        if row.get("repository_url"):
            by_origin[normalize_repo_url(row["repository_url"])].append(row)
        if row.get("existing_repository_path"):
            by_path[str(Path(row["existing_repository_path"]).resolve())].append(row)
    return by_origin, by_path


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def select_repository_metadata(candidates: list[dict], repository: Path) -> dict:
    if not candidates:
        return {}
    repository_key = _name_key(repository.name)

    def score(row):
        app_key = _name_key(row.get("app_name", ""))
        package_tail = _name_key(str(row.get("package_name", "")).rsplit(".", 1)[-1])
        subdir_key = _name_key(Path(row.get("subdir") or ".").name)
        value = 0
        value += 100 if app_key == repository_key else 0
        value += 90 if subdir_key and subdir_key == repository_key else 0
        value += 60 if package_tail == repository_key else 0
        value += 25 if repository_key and (repository_key in app_key or app_key in repository_key) else 0
        value += 20 if row.get("subdir") and (repository / row["subdir"]).exists() else 0
        value += 5 if row.get("commit_hash") else 0
        return value, row.get("version_code", ""), row.get("package_name", "")

    return dict(max(candidates, key=score))


def cap_per_app_type(candidates: list[dict], maximum: int) -> None:
    counts = Counter()
    for row in sorted(candidates, key=lambda item: (
        item["package_name"], item["issue_type"], item["xml_path"],
        int(item["line_number"]), item["candidate_id"],
    )):
        key = (row["repository_url"] or row["package_name"], row["issue_type"])
        counts[key] += 1
        if counts[key] > maximum:
            row["selection_status"] = "excluded"
            suffix = f"per-App per-type cap exceeded ({maximum})"
            row["notes"] = f"{row['notes']}; {suffix}".strip("; ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--repository-limit", type=int)
    parser.add_argument("--repository-names", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-large-scan", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    paths = config.get("paths", {})
    repository_root = resolve_project_path(paths["existing_repository_root"])
    metadata_root = resolve_project_path(paths["fdroid_metadata_root"])
    output_root = (
        args.output_root.resolve()
        if args.output_root
        else resolve_project_path(paths["output_root"]).resolve()
    )
    ensure_output_is_v2(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    log_path = output_root / "scan_log.jsonl"
    log_path.write_text("", encoding="utf-8")

    before = v1_current_snapshot()
    (output_root / "v1_integrity_before.json").write_text(
        json.dumps(before, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    compose_limit = int(config["scan"].get("compose_search_file_limit", 5000))
    inventory = inventory_existing_repositories(repository_root, compose_limit)
    metadata_rows = attach_existing_paths(parse_metadata_root(metadata_root), repository_root)
    write_csv(output_root / "fdroid_metadata_inventory.csv", metadata_rows, METADATA_FIELDS)
    by_origin, by_path = metadata_maps(metadata_rows)
    names = [item.strip() for item in args.repository_names.split(",") if item.strip()]
    default_limit = int(config["scan"]["dry_run_repository_limit"])
    limit = args.repository_limit if args.repository_limit is not None else default_limit
    selected = choose_repositories(inventory, names, limit)
    if args.dry_run and len(selected) > default_limit:
        raise ValueError(f"dry-run is limited to {default_limit} repositories")
    if not args.dry_run and len(selected) > default_limit and not args.confirm_large_scan:
        raise ValueError("large scan requires --confirm-large-scan")

    detector_profile = config["scan"].get("detector_profile", "expanded_v3")
    high_min = float(config["confidence"]["high_min_score"])
    medium_min = float(config["confidence"]["medium_min_score"])
    all_candidates = []
    xml_rows = []
    scanned_by_path = {}
    with log_path.open("a", encoding="utf-8") as log:
        for index, row in enumerate(selected, 1):
            repository = Path(row["repository_path"])
            origin = normalize_repo_url(row["repository_url"])
            metadata = select_repository_metadata(
                by_path.get(str(repository.resolve()))
                or by_origin.get(origin)
                or [],
                repository,
            )
            metadata.setdefault("package_name", row["package_name"])
            metadata.setdefault("app_name", row["app_name"])
            metadata.setdefault("repository_url", row["repository_url"])
            metadata["repository_status"] = "existing_local"
            try:
                summary, candidates, repository_xml = scan_repository(
                    repository,
                    metadata=metadata,
                    detector_profile=detector_profile,
                    high_min=high_min,
                    medium_min=medium_min,
                    compose_file_limit=compose_limit,
                )
                status = "completed" if not summary["scan_error"] else "completed_with_error"
            except Exception as exc:
                summary = dict(row)
                summary.update(repository_status="scan_failed", scan_error=str(exc))
                candidates = []
                repository_xml = []
                status = "failed"
            scanned_by_path[str(repository.resolve())] = summary
            all_candidates.extend(candidates)
            xml_rows.extend(repository_xml)
            log.write(json.dumps({
                "index": index,
                "repository": str(repository),
                "app_name": metadata["app_name"],
                "status": status,
                "high": summary.get("high_candidate_count", 0),
                "review": summary.get("review_candidate_count", 0),
                "boundary": summary.get("boundary_candidate_count", 0),
                "scan_seconds": summary.get("scan_seconds", 0),
                "paid_api_used": False,
                "model_outputs_used": False,
            }, ensure_ascii=False) + "\n")
            print(f"[{index}/{len(selected)}] {metadata['app_name']}: {status}")

    unique = {row["candidate_id"]: row for row in all_candidates}
    candidates = sorted(unique.values(), key=lambda row: (
        row["package_name"], row["xml_path"], int(row["line_number"]), row["candidate_id"]
    ))
    high = [row for row in candidates if row["confidence"] == "high" and row["severity"] == "error" and row["xml_safe"] == "true"]
    boundary = [row for row in candidates if row["difficulty"] == "boundary" or row["runtime_required"] == "true"]
    boundary_ids = {row["candidate_id"] for row in boundary}
    high_ids = {row["candidate_id"] for row in high}
    review = [row for row in candidates if row["candidate_id"] not in high_ids | boundary_ids]
    cap_per_app_type(high, int(config["scan"]["max_issues_per_app_type"]))
    cap_per_app_type(boundary, int(config["scan"]["max_issues_per_app_type"]))

    repository_rows = [
        scanned_by_path.get(row["repository_path"], row)
        for row in inventory
    ]
    write_csv(output_root / "high_confidence_candidates.csv", high, CANDIDATE_FIELDS)
    write_csv(output_root / "review_required_candidates.csv", review, CANDIDATE_FIELDS)
    write_csv(output_root / "boundary_candidates.csv", boundary, CANDIDATE_FIELDS)
    write_csv(output_root / "repository_summary.csv", repository_rows, REPOSITORY_FIELDS)
    write_csv(output_root / "xml_summary.csv", xml_rows, XML_FIELDS)
    analysis = write_analysis(output_root, high, review, boundary, repository_rows, xml_rows, config)

    after = v1_current_snapshot()
    unchanged = snapshots_equal(before, after)
    integrity = {
        "v1_files_unchanged_during_prescreen": unchanged,
        "preexisting_frozen_manifest_mismatch_count": before["preexisting_mismatch_count"],
        "before": before,
        "after": after,
    }
    (output_root / "v1_integrity_check.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not unchanged:
        raise RuntimeError("V1 protected files changed during source prescreen")

    manifest = {
        "schema_version": 1,
        "dataset_id": "android_xml_source_prescreen_v2",
        "status": "dry_run_candidate_not_frozen" if args.dry_run else "candidate_not_frozen",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_type": "natural_source_issue",
        "selection_uses_model_outputs": False,
        "paid_api_used": False,
        "issue_injection_used": False,
        "detector_profile": detector_profile,
        "repository_inventory_count": len(inventory),
        "scanned_repository_count": len(selected),
        "scanned_repositories": [Path(row["repository_path"]).name for row in selected],
        "candidate_counts": {
            "high_confidence_xml_safe": len(high),
            "high_confidence_xml_safe_eligible": analysis["eligible_high_xml_safe"],
            "review_required": len(review),
            "boundary": len(boundary),
            "boundary_eligible": analysis["eligible_boundary"],
        },
        "v1_integrity": {
            "unchanged_during_run": unchanged,
            "preexisting_frozen_manifest_mismatch_count": before["preexisting_mismatch_count"],
        },
        "large_scan_performed": not args.dry_run and len(selected) > default_limit,
        "dataset_split": "unassigned",
    }
    (output_root / "candidate_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "repositories_inventory": len(inventory),
        "repositories_scanned": len(selected),
        **manifest["candidate_counts"],
        "issue_types_meeting_quota": analysis["issue_types_meeting_quota"],
        "v1_unchanged_during_run": unchanged,
        "output": str(output_root),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
