"""Shared schema and utility helpers for the source prescreen pipeline."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
V1_ROOTS = (
    ROOT / "experiments/android_xml_multimodel",
    ROOT / "experiments/android_xml_ablation",
    ROOT / "experiments/android_xml_ablation_claude",
    ROOT / "experiments/android_xml_v1_freeze",
)

CORE_ISSUE_TYPES = (
    "accessible_name_missing",
    "accessible_name_quality",
    "input_label_hint",
    "input_type_semantics",
    "label_association",
    "focus_accessibility_tree",
    "stateful_dynamic_value",
    "touch_target_size",
    "accessibility_attribute_conflict",
    "static_xml_boundary",
)

CANDIDATE_FIELDS = (
    "candidate_id",
    "package_name",
    "app_name",
    "repository_url",
    "repo_type",
    "commit_hash",
    "subdir",
    "xml_path",
    "line_number",
    "widget_type",
    "widget_id",
    "issue_type",
    "issue_subtype",
    "severity",
    "confidence",
    "difficulty",
    "xml_safe",
    "runtime_required",
    "evidence",
    "relevant_attributes",
    "resolved_resource_values",
    "parent_context",
    "screen_or_layout_name",
    "repository_status",
    "source_type",
    "dedup_group",
    "manual_review_status",
    "selection_status",
    "dataset_split",
    "notes",
)


def load_config(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = {"scan", "dataset_targets", "confidence", "resources", "execution"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"source prescreen config missing sections: {', '.join(missing)}")
    execution = data["execution"]
    if execution.get("allow_paid_api"):
        raise ValueError("source prescreen cannot enable paid APIs")
    if execution.get("allow_issue_injection"):
        raise ValueError("source prescreen cannot inject issues")
    if execution.get("overwrite_v1_outputs"):
        raise ValueError("source prescreen cannot overwrite V1 outputs")
    return data


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def ensure_output_is_v2(path: Path) -> None:
    resolved = path.resolve()
    for protected in V1_ROOTS:
        if resolved == protected.resolve() or protected.resolve() in resolved.parents:
            raise ValueError(f"refusing to write source prescreen output under V1: {resolved}")
    normalized = resolved.as_posix().lower()
    if "source_prescreen" not in normalized and "/v2" not in normalized:
        raise ValueError("source prescreen output path must contain source_prescreen or v2")


def normalize_repo_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    normalized = re.sub(r"\.git$", "", normalized, flags=re.I)
    normalized = re.sub(r"^git@([^:]+):", r"https://\1/", normalized)
    return normalized.casefold()


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    return value[:100] or "repository"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_cell(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def bool_cell(value) -> str:
    return "true" if bool(value) else "false"


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...] | list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
