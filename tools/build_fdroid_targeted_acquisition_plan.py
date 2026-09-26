#!/usr/bin/env python3
"""Build a leakage-free F-Droid acquisition plan for missing XML issue types."""
from __future__ import annotations

import argparse
import configparser
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA_ROOT = Path("fdroid_apps/_fdroiddata/metadata")
DEFAULT_EXISTING_ROOTS = (
    Path("fdroid_apps/selected_xml_apps"),
    Path("fdroid_apps"),
)
DEFAULT_GAP_REPORT = (
    ROOT
    / "experiments/android_xml_dataset_redesign/targeted_sample_pool_expanded_v2/targeted_app_candidates.json"
)
DEFAULT_OUTPUT = (
    ROOT / "experiments/android_xml_dataset_redesign/fdroid_targeted_acquisition"
)


TARGET_KEYWORDS = {
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": {
        "calculator": 5,
        "converter": 5,
        "ip address": 5,
        "network configuration": 5,
        "one-time password": 5,
        "otp": 4,
        "pin": 3,
        "port": 3,
        "timer": 3,
    },
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": {
        "remote control": 6,
        "controller": 5,
        "game": 3,
        "keyboard": 4,
        "media player": 3,
        "music player": 3,
    },
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": {
        "password manager": 8,
        "credentials": 6,
        "credential": 5,
        "sign in": 5,
        "signin": 5,
        "login": 5,
        "account authentication": 6,
        "vault": 4,
        "password": 4,
    },
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": {
        "email client": 8,
        "e-mail client": 8,
        "email account": 7,
        "mail account": 7,
        "registration": 4,
        "register": 3,
        "email": 4,
        "e-mail": 4,
        "mail": 2,
    },
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": {
        "phone number": 8,
        "contact manager": 7,
        "contacts": 5,
        "dialer": 6,
        "caller": 5,
        "telephone": 5,
        "sms": 3,
        "phone": 3,
    },
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": {
        "expense": 7,
        "budget": 7,
        "amount": 6,
        "price": 6,
        "quantity": 6,
        "weight": 5,
        "age": 4,
        "measurement": 4,
        "finance": 4,
        "calculator": 4,
        "tracker": 2,
    },
}

TARGET_CATEGORY_HINTS = {
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": {
        "Calculator", "Connectivity", "Password & 2FA", "Unit Convertor",
    },
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": {
        "Game", "Keyboard & IME", "Multimedia", "Remote Controller",
    },
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": {
        "Password & 2FA", "Security",
    },
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": {"Email"},
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": {"Contact", "Phone & SMS"},
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": {
        "Calculator", "Finance Manager", "Health Manager", "Market & Price",
        "Money", "Sports & Health", "Unit Convertor",
    },
}

TARGET_MIN_SCORES = {
    "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": 5,
    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": 5,
    "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": 8,
    "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": 7,
    "ANDROID_XML_PHONE_INPUTTYPE_MISSING": 8,
    "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": 6,
}


def normalize_repo_url(url):
    normalized = str(url or "").strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.casefold()


def searchable_text(data):
    categories = data.get("Categories") or []
    if isinstance(categories, str):
        categories = [categories]
    fields = [
        data.get("Name"),
        data.get("AutoName"),
        data.get("Summary"),
        data.get("Description"),
        " ".join(str(item) for item in categories),
    ]
    return re.sub(r"\s+", " ", " ".join(str(value or "") for value in fields)).casefold()


def phrase_present(text, phrase):
    tokens = re.findall(r"[a-z0-9]+", phrase.casefold())
    if not tokens:
        return False
    pattern = r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, tokens)) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text))


def target_scores(text, categories=()):
    scores = {}
    matches = {}
    category_set = set(categories)
    for code, weighted_keywords in TARGET_KEYWORDS.items():
        found = [
            keyword for keyword in weighted_keywords
            if phrase_present(text, keyword)
        ]
        if not found:
            continue
        base_score = sum(weighted_keywords[keyword] for keyword in found)
        category_match = bool(category_set & TARGET_CATEGORY_HINTS[code])
        if base_score < TARGET_MIN_SCORES[code] and not category_match:
            continue
        scores[code] = base_score + (3 if category_match else 0)
        matches[code] = found
    return scores, matches


def load_gaps(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    gaps = {}
    for item in payload.get("target_types", []):
        code = item.get("code")
        if code in TARGET_KEYWORDS and not item.get("quota_met", False):
            gaps[code] = {
                "app_gap": int(item.get("app_gap", 0)),
                "finding_gap": int(item.get("finding_gap", 0)),
            }
    return gaps


def repository_origins(roots):
    origins = set()
    seen_paths = set()
    for root in roots:
        if not root.exists():
            continue
        git_dirs = [root / ".git"] if (root / ".git").exists() else root.glob("*/.git")
        for git_dir in git_dirs:
            repo = git_dir.parent.resolve()
            if repo in seen_paths:
                continue
            seen_paths.add(repo)
            config = configparser.RawConfigParser()
            try:
                config.read(git_dir / "config", encoding="utf-8")
                url = config.get('remote "origin"', "url", fallback="")
            except (configparser.Error, OSError):
                url = ""
            if url:
                origins.add(normalize_repo_url(url))
    return origins


def metadata_candidates(metadata_root, gaps, existing_origins):
    candidates = []
    for path in sorted(metadata_root.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if data.get("RepoType") != "git" or data.get("Disabled"):
            continue
        repo_url = str(data.get("Repo") or "").strip()
        if not repo_url.startswith(("https://", "http://")):
            continue
        if normalize_repo_url(repo_url) in existing_origins:
            continue
        categories = data.get("Categories") or ["Uncategorized"]
        if isinstance(categories, str):
            categories = [categories]
        categories = sorted({str(item) for item in categories})
        scores, matches = target_scores(searchable_text(data), categories)
        scores = {code: score for code, score in scores.items() if code in gaps}
        matches = {code: value for code, value in matches.items() if code in gaps}
        if not scores:
            continue
        candidates.append({
            "app_id": path.stem,
            "fdroid_app_ids": [path.stem],
            "app_name": str(data.get("Name") or data.get("AutoName") or path.stem),
            "categories": categories,
            "license": str(data.get("License") or "Unknown"),
            "repo_url": repo_url,
            "source_code_url": str(data.get("SourceCode") or repo_url),
            "metadata_file": str(path),
            "target_scores": scores,
            "keyword_evidence": matches,
            "active_version_known": bool(data.get("CurrentVersionCode")),
        })
    by_repository = {}
    for candidate in candidates:
        key = normalize_repo_url(candidate["repo_url"])
        current = by_repository.get(key)
        if current is None:
            by_repository[key] = candidate
            continue
        current["fdroid_app_ids"] = sorted(set(
            current["fdroid_app_ids"] + candidate["fdroid_app_ids"]
        ))
        current["categories"] = sorted(set(
            current["categories"] + candidate["categories"]
        ))
        current["active_version_known"] = (
            current["active_version_known"] or candidate["active_version_known"]
        )
        for code, score in candidate["target_scores"].items():
            current["target_scores"][code] = max(
                score,
                current["target_scores"].get(code, 0),
            )
            evidence = current["keyword_evidence"].setdefault(code, [])
            evidence.extend(candidate["keyword_evidence"].get(code, []))
            current["keyword_evidence"][code] = sorted(set(evidence))
    return list(by_repository.values())


def select_candidates(candidates, gaps, per_type=15, max_total=60, max_per_category=4):
    selected = {}
    selected_counts = Counter()
    category_counts = defaultdict(Counter)
    target_order = sorted(
        gaps,
        key=lambda code: (-gaps[code]["app_gap"], -gaps[code]["finding_gap"], code),
    )
    rankings = {
        code: sorted(
            (candidate for candidate in candidates if code in candidate["target_scores"]),
            key=lambda item: (
                -item["target_scores"][code],
                -int(item["active_version_known"]),
                item["app_name"].casefold(),
            ),
        )
        for code in target_order
    }
    positions = Counter()
    made_progress = True
    while len(selected) < max_total and made_progress:
        made_progress = False
        for code in target_order:
            if selected_counts[code] >= per_type:
                continue
            ranking = rankings[code]
            while positions[code] < len(ranking):
                candidate = ranking[positions[code]]
                positions[code] += 1
                primary_category = candidate["categories"][0]
                if category_counts[code][primary_category] >= max_per_category:
                    continue
                selected_counts[code] += 1
                category_counts[code][primary_category] += 1
                current = selected.setdefault(candidate["app_id"], dict(candidate))
                current.setdefault("selected_for_codes", [])
                if code not in current["selected_for_codes"]:
                    current["selected_for_codes"].append(code)
                made_progress = True
                break
            if len(selected) >= max_total:
                break
    return sorted(
        selected.values(),
        key=lambda item: (
            -len(item["selected_for_codes"]),
            -sum(item["target_scores"].values()),
            item["app_name"].casefold(),
        ),
    )


def write_outputs(output, candidates, selected, gaps, existing_count, per_type):
    output.mkdir(parents=True, exist_ok=True)
    per_code_selected = Counter(
        code for item in selected for code in item["selected_for_codes"]
    )
    payload = {
        "schema_version": 1,
        "plan_id": "fdroid_targeted_xml_acquisition_v2",
        "status": "candidate_repositories_not_yet_cloned_or_source_verified",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_uses_model_outputs": False,
        "selection_uses_detector_outcomes_from_new_apps": False,
        "existing_repository_count": existing_count,
        "gaps": gaps,
        "candidate_pool_count": len(candidates),
        "selected_repository_count": len(selected),
        "candidate_quota_per_type": per_type,
        "selected_count_by_type": dict(per_code_selected),
        "apps": selected,
    }
    (output / "targeted_app_acquisition_plan.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    csv_fields = [
        "app_id", "fdroid_app_ids", "app_name", "categories", "license", "repo_url",
        "selected_for_codes", "target_scores", "keyword_evidence",
        "active_version_known",
    ]
    with (output / "targeted_app_acquisition_plan.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for item in selected:
            writer.writerow({
                "app_id": item["app_id"],
                "fdroid_app_ids": "|".join(item["fdroid_app_ids"]),
                "app_name": item["app_name"],
                "categories": "|".join(item["categories"]),
                "license": item["license"],
                "repo_url": item["repo_url"],
                "selected_for_codes": "|".join(item["selected_for_codes"]),
                "target_scores": json.dumps(item["target_scores"], ensure_ascii=False),
                "keyword_evidence": json.dumps(item["keyword_evidence"], ensure_ascii=False),
                "active_version_known": item["active_version_known"],
            })

    lines = [
        "# F-Droid Targeted XML App Acquisition Plan",
        "",
        "- Selection uses model outputs: no",
        "- New repositories already counted as experiment samples: no",
        f"- Existing repositories excluded: {existing_count}",
        f"- Metadata candidates matching missing types: {len(candidates)}",
        f"- Repositories selected for cloning and source screening: {len(selected)}",
        "",
        "| Missing type | Current App gap | Current finding gap | Clone candidates |",
        "|---|---:|---:|---:|",
    ]
    for code, gap in gaps.items():
        lines.append(
            f"| `{code}` | {gap['app_gap']} | {gap['finding_gap']} | "
            f"{per_code_selected[code]} |"
        )
    lines.extend([
        "",
        "These are acquisition candidates only. A repository enters the dataset only after cloning, confirming XML-backed screens, running `expanded_v2`, and manually reviewing newly promoted findings.",
        "",
        "## First balanced batch",
        "",
        "Preview: `python3 tools/acquire_fdroid_targeted_apps.py --limit 24`",
        "",
        "Clone: `python3 tools/acquire_fdroid_targeted_apps.py --limit 24 --execute`",
        "",
        "After cloning, rebuild the type-stratified pool with `python3 tools/build_android_xml_targeted_sample_pool.py`.",
        "",
    ])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-root", type=Path, default=DEFAULT_METADATA_ROOT)
    parser.add_argument("--gap-report", type=Path, default=DEFAULT_GAP_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--existing-root",
        type=Path,
        action="append",
        dest="existing_roots",
        help="Root containing already cloned repositories; repeat as needed.",
    )
    parser.add_argument("--candidates-per-type", type=int, default=15)
    parser.add_argument("--max-total", type=int, default=60)
    parser.add_argument("--max-per-category", type=int, default=4)
    args = parser.parse_args()

    existing_roots = args.existing_roots or list(DEFAULT_EXISTING_ROOTS)
    origins = repository_origins(existing_roots)
    gaps = load_gaps(args.gap_report)
    candidates = metadata_candidates(args.metadata_root, gaps, origins)
    selected = select_candidates(
        candidates,
        gaps,
        per_type=args.candidates_per_type,
        max_total=args.max_total,
        max_per_category=args.max_per_category,
    )
    payload = write_outputs(
        args.output,
        candidates,
        selected,
        gaps,
        len(origins),
        args.candidates_per_type,
    )
    print(json.dumps({
        "candidate_pool_count": payload["candidate_pool_count"],
        "selected_repository_count": payload["selected_repository_count"],
        "selected_count_by_type": payload["selected_count_by_type"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
