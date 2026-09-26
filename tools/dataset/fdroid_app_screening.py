#!/usr/bin/env python3
"""Select category-diverse F-Droid apps suitable for Android XML experiments.

The pipeline uses F-Droid's fdroiddata metadata to find public Git repositories,
clones candidates with shallow/filter options, scans their Android resources,
and keeps apps with at least two likely XML-backed interfaces.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("缺少 PyYAML。请先运行: python3 -m pip install PyYAML") from exc


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA_REPO = "https://gitlab.com/fdroid/fdroiddata.git"
CHECKER = ROOT / "tools" / "evaluation" / "android_xml_a11y_check.py"

ENTRY_PREFIX_SCORES = {
    "activity_": 100,
    "screen_": 95,
    "fragment_": 90,
    "bottom_sheet_": 85,
    "dialog_": 80,
    "page_": 75,
}

SUPPORT_PREFIXES = (
    "item_",
    "row_",
    "list_item_",
    "cell_",
    "view_",
    "include_",
    "component_",
    "widget_",
    "toolbar_",
    "header_",
    "footer_",
    "preference_",
    "listitem_",
    "fab_",
)

SUPPORT_SUFFIXES = (
    "_item",
    "_row",
    "_cell",
    "_view",
    "_button",
    "_toolbar",
    "_header",
    "_footer",
    "_toast",
    "_mockup",
    "_divider",
)

GENERIC_SUPPORT_TERMS = {
    "item",
    "row",
    "cell",
    "toolbar",
    "header",
    "footer",
    "divider",
    "button",
    "chip",
    "card",
}

SUPPORT_TOKENS = {
    "item",
    "row",
    "cell",
    "button",
    "toolbar",
    "actionbar",
    "header",
    "footer",
    "toast",
    "mockup",
    "divider",
    "menu",
    "splash",
    "empty",
    "placeholder",
    "loading",
}

NON_EXPERIMENT_TOKENS = {
    "background",
    "bg",
    "empty",
    "loading",
    "placeholder",
    "splash",
}

LAYOUT_REFERENCE_RE = re.compile(r"\bR\.layout\.([A-Za-z0-9_]+)")
INCLUDE_LAYOUT_RE = re.compile(
    r"<include\b[^>]*\blayout=[\"']@layout/([^\"']+)[\"']"
)
SET_CONTENT_VIEW_RE = re.compile(
    r"\b(?:setContentView|setContent)\s*\([^)]*R\.layout\.([A-Za-z0-9_]+)",
    re.DOTALL,
)
INFLATE_RE = re.compile(
    r"\binflate\s*\([^)]*R\.layout\.([A-Za-z0-9_]+)",
    re.DOTALL,
)
COMPOSABLE_RE = re.compile(r"@Composable\b")
ANDROID_APP_PLUGIN_RE = re.compile(
    r"(?:com\.android\.application|id\s*\(?[\"']com\.android\.application[\"'])"
)


@dataclass
class FdroidApp:
    app_id: str
    name: str
    categories: list[str]
    license: str
    repo_url: str
    source_code_url: str
    metadata_file: str


@dataclass
class ScreenCandidate:
    name: str
    relative_path: str
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class AppScan:
    app_id: str
    name: str
    category: str
    categories: list[str]
    license: str
    repo_url: str
    local_path: str
    clone_status: str
    eligible: bool
    exclusion_reasons: list[str]
    android_app_modules: list[str]
    layout_xml_count: int
    screen_candidate_count: int
    selected_screens: list[ScreenCandidate]
    supporting_layout_count: int
    composable_function_count: int
    kotlin_java_file_count: int
    detector_issue_count: int | None
    detector_fixable_issue_count: int | None
    detector_review_issue_count: int | None
    detector_issue_codes: dict[str, int]


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned[:80] or "app"


def normalize_repo_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def ensure_metadata_repo(metadata_dir: Path, repo_url: str, update: bool) -> None:
    if (metadata_dir / ".git").exists():
        if update:
            result = run_command(
                ["git", "-C", str(metadata_dir), "pull", "--ff-only", "--depth", "1"],
                timeout=900,
            )
            if result.returncode != 0:
                raise RuntimeError(f"更新 fdroiddata 失败: {result.stderr.strip()}")
        return

    metadata_dir.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--no-tags",
            repo_url,
            str(metadata_dir),
        ],
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f"克隆 fdroiddata 失败: {result.stderr.strip()}")


def parse_fdroid_metadata(metadata_dir: Path) -> list[FdroidApp]:
    metadata_root = metadata_dir / "metadata"
    if not metadata_root.exists():
        raise FileNotFoundError(f"找不到 F-Droid metadata 目录: {metadata_root}")

    apps = []
    for path in sorted(metadata_root.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue

        if data.get("RepoType") != "git":
            continue
        repo_url = str(data.get("Repo") or "").strip()
        if not repo_url.startswith(("https://", "http://")):
            continue

        categories = data.get("Categories") or []
        if isinstance(categories, str):
            categories = [categories]
        categories = sorted({str(item).strip() for item in categories if str(item).strip()})
        if not categories:
            categories = ["Uncategorized"]

        app_id = path.stem
        name = str(data.get("AutoName") or data.get("Name") or app_id).strip()
        apps.append(FdroidApp(
            app_id=app_id,
            name=name,
            categories=categories,
            license=str(data.get("License") or "Unknown"),
            repo_url=repo_url,
            source_code_url=str(data.get("SourceCode") or repo_url),
            metadata_file=str(path),
        ))
    return apps


def detect_app_modules(repo: Path) -> list[Path]:
    modules = set()
    for gradle_file in list(repo.rglob("build.gradle")) + list(repo.rglob("build.gradle.kts")):
        if any(part in {".git", "build", ".gradle"} for part in gradle_file.parts):
            continue
        try:
            text = gradle_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if ANDROID_APP_PLUGIN_RE.search(text):
            modules.add(gradle_file.parent)

    # Modern projects often apply the Android application plugin through a
    # version-catalog alias that is difficult to identify from one Gradle file.
    # A main manifest declaring at least one activity is a stable fallback.
    for manifest in repo.rglob("src/main/AndroidManifest.xml"):
        if any(part in {".git", "build", ".gradle"} for part in manifest.parts):
            continue
        try:
            text = manifest.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "<application" in text and re.search(r"<activity(?:-alias)?\b", text):
            modules.add(manifest.parents[2])
    return sorted(modules)


def is_test_source(path: Path) -> bool:
    lower_parts = [part.lower() for part in path.parts]
    for index, part in enumerate(lower_parts[:-1]):
        if part == "src" and lower_parts[index + 1] in {
            "test",
            "androidtest",
            "testfixtures",
        }:
            return True
    return any(
        part in {"test", "tests", "testing", "testing-android"}
        for part in lower_parts
    )


def collect_layouts(repo: Path) -> list[Path]:
    layouts = []
    for path in repo.rglob("*.xml"):
        if any(part in {".git", "build", ".gradle"} for part in path.parts):
            continue
        if is_test_source(path.relative_to(repo)):
            continue
        if path.parent.name.startswith("layout") and "res" in path.parts:
            layouts.append(path)
    return sorted(layouts)


def scan_source_references(repo: Path) -> tuple[Counter, Counter, int, int]:
    references = Counter()
    entry_references = Counter()
    composable_count = 0
    source_count = 0

    for suffix in ("*.kt", "*.java"):
        for path in repo.rglob(suffix):
            if any(part in {".git", "build", ".gradle"} for part in path.parts):
                continue
            if is_test_source(path.relative_to(repo)):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            source_count += 1
            references.update(LAYOUT_REFERENCE_RE.findall(text))
            entry_references.update(SET_CONTENT_VIEW_RE.findall(text))
            class_context = (
                "Fragment" in text
                or "Dialog" in text
                or "BottomSheet" in text
                or path.stem.endswith(("Fragment", "Dialog"))
            )
            if class_context and "Adapter" not in path.stem and "ViewHolder" not in text:
                entry_references.update(INFLATE_RE.findall(text))
            if path.suffix == ".kt":
                composable_count += len(COMPOSABLE_RE.findall(text))
    return references, entry_references, composable_count, source_count


def relative_to_repo(path: Path, repo: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return str(path)


def score_layout(
    path: Path,
    references: Counter,
    entry_references: Counter,
) -> ScreenCandidate | None:
    name = path.stem
    name_tokens = set(name.split("_"))
    if name_tokens & NON_EXPERIMENT_TOKENS:
        return None
    if name == "app_icon" or {"widget", "resize"}.issubset(name_tokens):
        return None

    score = 0
    reasons = []

    if name in entry_references:
        score += 130 + min(entry_references[name], 5)
        reasons.append("used by setContentView/inflate")
    elif name in references:
        score += 35 + min(references[name], 5)
        reasons.append("referenced from Kotlin/Java")

    for prefix, weight in ENTRY_PREFIX_SCORES.items():
        if name.startswith(prefix):
            score += weight
            reasons.append(f"{prefix[:-1]} layout")
            break

    if name in {"activity_main", "main_activity", "main"}:
        score += 50
        reasons.append("main interface")
    if "settings" in name or "preference" in name:
        score += 35
        reasons.append("settings interface")
    if any(term in name for term in ("search", "detail", "editor", "form", "login", "file", "commander")):
        score += 25
        reasons.append("task-oriented interface")

    if name.startswith(SUPPORT_PREFIXES):
        score -= 180
        reasons.append("support-layout prefix")
    if name.endswith(SUPPORT_SUFFIXES) or "header_footer" in name:
        score -= 180
        reasons.append("support-layout suffix")
    if name_tokens & SUPPORT_TOKENS:
        score -= 180
        reasons.append("support-layout token")
    if (
        "preference" in name
        and not name.startswith(("activity_", "fragment_", "dialog_", "screen_"))
    ):
        score -= 180
        reasons.append("preference support layout")
    if name in GENERIC_SUPPORT_TERMS:
        score -= 100
        reasons.append("generic support layout")

    if score < 50:
        return None
    return ScreenCandidate(
        name=name,
        relative_path="",
        score=score,
        reasons=reasons,
    )


def choose_screens(repo: Path, layouts: list[Path], limit: int = 3) -> list[ScreenCandidate]:
    references, entry_references, _, _ = scan_source_references(repo)
    best_by_name: dict[str, ScreenCandidate] = {}
    for path in layouts:
        candidate = score_layout(path, references, entry_references)
        if not candidate:
            continue
        candidate.relative_path = relative_to_repo(path, repo)
        current = best_by_name.get(candidate.name)
        if current is None or candidate.score > current.score:
            best_by_name[candidate.name] = candidate

    ranked = sorted(
        best_by_name.values(),
        key=lambda item: (-item.score, item.name, item.relative_path),
    )
    return ranked[:limit]


def resource_root(path: Path) -> Path | None:
    for parent in path.parents:
        if parent.name == "res":
            return parent
    return None


def expand_layout_dependencies(screen_paths: Iterable[Path]) -> list[Path]:
    selected = {path.resolve() for path in screen_paths if path.exists()}
    pending = list(selected)
    while pending:
        path = pending.pop()
        res_root = resource_root(path)
        if res_root is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for layout_name in INCLUDE_LAYOUT_RE.findall(text):
            for dependency in res_root.glob(f"layout*/{layout_name}.xml"):
                dependency = dependency.resolve()
                if dependency not in selected:
                    selected.add(dependency)
                    pending.append(dependency)
    return sorted(selected)


def run_detector_issues(screen_paths: Iterable[Path]) -> list[dict] | None:
    paths = expand_layout_dependencies(screen_paths)
    if not paths or not CHECKER.exists():
        return None
    result = run_command(
        [sys.executable, str(CHECKER), *(str(path) for path in paths), "--json"],
        timeout=180,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    return None


def run_detector(screen_paths: Iterable[Path]) -> tuple[int | None, int | None, int | None, dict[str, int]]:
    issues = run_detector_issues(screen_paths)
    if issues is None:
        return None, None, None, {}

    errors = [
        issue
        for issue in issues
        if issue.get("severity", issue.get("type", "error")) == "error"
    ]
    codes = Counter(issue.get("code", "UNKNOWN") for issue in errors)
    fixable = sum(
        issue.get("repairability", "xml_safe") == "xml_safe"
        for issue in errors
    )
    review = len(errors) - fixable
    return len(errors), fixable, review, dict(sorted(codes.items()))


def select_experiment_screens(
    repo: Path,
    candidates: list[ScreenCandidate],
    limit: int,
    run_a11y_detector: bool,
) -> list[ScreenCandidate]:
    if not run_a11y_detector or len(candidates) <= limit:
        return candidates[:limit]

    pool = candidates[:max(limit * 4, limit)]
    pool_paths = [repo / candidate.relative_path for candidate in pool]
    issues = run_detector_issues(pool_paths)
    if issues is None:
        return candidates[:limit]

    issue_files = [
        (
            Path(issue.get("file", "")).resolve(),
            (
                issue.get("severity", issue.get("type", "error")),
                issue.get("repairability", "xml_safe"),
            ),
        )
        for issue in issues
        if issue.get("file")
    ]
    repairable_counts = {}
    for candidate, path in zip(pool, pool_paths):
        dependencies = set(expand_layout_dependencies([path]))
        repairable_counts[candidate.relative_path] = sum(
            severity == "error"
            and repairability == "xml_safe"
            and issue_file in dependencies
            for issue_file, (severity, repairability) in issue_files
        )

    selected = [
        candidate
        for candidate in pool
        if repairable_counts.get(candidate.relative_path, 0) > 0
    ][:limit]
    for candidate in candidates:
        if len(selected) >= limit:
            break
        if candidate not in selected:
            selected.append(candidate)

    for candidate in selected:
        count = repairable_counts.get(candidate.relative_path, 0)
        if count:
            candidate.reasons.append(
                f"{count} xml_safe detector finding{'s' if count != 1 else ''}"
            )
    return selected


def scan_repository(
    repo: Path,
    app: FdroidApp | None = None,
    category: str | None = None,
    min_screens: int = 2,
    selected_screen_limit: int = 3,
    run_a11y_detector: bool = True,
    min_fixable_issues: int = 0,
    max_fixable_issues: int = 0,
    clone_status: str = "existing",
) -> AppScan:
    app_id = app.app_id if app else repo.name
    name = app.name if app else repo.name
    categories = app.categories if app else ["Unknown"]
    primary_category = category or categories[0]
    license_name = app.license if app else "Unknown"
    repo_url = app.repo_url if app else get_origin_url(repo)

    modules = detect_app_modules(repo)
    layouts = collect_layouts(repo)
    references, entry_references, composables, source_count = scan_source_references(repo)

    candidates = []
    best_by_name: dict[str, ScreenCandidate] = {}
    for path in layouts:
        candidate = score_layout(path, references, entry_references)
        if not candidate:
            continue
        candidate.relative_path = relative_to_repo(path, repo)
        current = best_by_name.get(candidate.name)
        if current is None or candidate.score > current.score:
            best_by_name[candidate.name] = candidate
    candidates = sorted(
        best_by_name.values(),
        key=lambda item: (-item.score, item.name, item.relative_path),
    )
    selected = select_experiment_screens(
        repo,
        candidates,
        selected_screen_limit,
        run_a11y_detector,
    )

    exclusion_reasons = []
    if not modules:
        exclusion_reasons.append("no Android application module")
    if len(candidates) < min_screens:
        exclusion_reasons.append(
            f"only {len(candidates)} likely XML interfaces; requires at least {min_screens}"
        )
    if not layouts:
        exclusion_reasons.append("no Android layout XML files")

    selected_paths = [repo / candidate.relative_path for candidate in selected]
    if run_a11y_detector:
        issue_count, fixable_count, review_count, issue_codes = run_detector(selected_paths)
    else:
        issue_count, fixable_count, review_count, issue_codes = None, None, None, {}
    if (
        min_fixable_issues > 0
        and fixable_count is not None
        and fixable_count < min_fixable_issues
    ):
        exclusion_reasons.append(
            f"only {fixable_count} fixable accessibility issues; "
            f"requires at least {min_fixable_issues}"
        )
    if (
        max_fixable_issues > 0
        and fixable_count is not None
        and fixable_count > max_fixable_issues
    ):
        exclusion_reasons.append(
            f"{fixable_count} fixable accessibility issues exceed "
            f"the experiment limit {max_fixable_issues}"
        )

    return AppScan(
        app_id=app_id,
        name=name,
        category=primary_category,
        categories=categories,
        license=license_name,
        repo_url=repo_url,
        local_path=str(repo.resolve()),
        clone_status=clone_status,
        eligible=not exclusion_reasons,
        exclusion_reasons=exclusion_reasons,
        android_app_modules=[relative_to_repo(path, repo) for path in modules],
        layout_xml_count=len(layouts),
        screen_candidate_count=len(candidates),
        selected_screens=selected,
        supporting_layout_count=max(len(layouts) - len(selected), 0),
        composable_function_count=composables,
        kotlin_java_file_count=source_count,
        detector_issue_count=issue_count,
        detector_fixable_issue_count=fixable_count,
        detector_review_issue_count=review_count,
        detector_issue_codes=issue_codes,
    )


def get_origin_url(repo: Path) -> str:
    result = run_command(["git", "-C", str(repo), "remote", "get-url", "origin"], timeout=20)
    return result.stdout.strip() if result.returncode == 0 else ""


def existing_repo_map(clone_root: Path) -> dict[str, Path]:
    mapping = {}
    if not clone_root.exists():
        return mapping
    for child in clone_root.iterdir():
        if not child.is_dir() or not (child / ".git").exists():
            continue
        origin = get_origin_url(child)
        if origin:
            mapping[normalize_repo_url(origin)] = child
    return mapping


def destination_for(app: FdroidApp, clone_root: Path, reserved: set[str]) -> Path:
    base = safe_name(app.name)
    candidate = base
    if candidate.lower() in reserved:
        candidate = safe_name(f"{base}-{app.app_id}")
    reserved.add(candidate.lower())
    return clone_root / candidate


def clone_repository(
    app: FdroidApp,
    destination: Path,
    timeout: int,
) -> tuple[str, str]:
    if (destination / ".git").exists():
        return "existing", ""
    if destination.exists():
        return "failed", f"destination exists and is not a git repository: {destination}"

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run_command(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--no-tags",
                "--single-branch",
                app.repo_url,
                str(destination),
            ],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(destination, ignore_errors=True)
        return "failed", f"clone timed out after {timeout} seconds"
    if result.returncode != 0:
        shutil.rmtree(destination, ignore_errors=True)
        return "failed", result.stderr.strip()[-1000:]
    return "cloned", ""


def balanced_candidates(
    apps: list[FdroidApp],
    allowed_categories: set[str] | None = None,
) -> list[tuple[FdroidApp, str]]:
    grouped: dict[str, deque[FdroidApp]] = defaultdict(deque)
    seen = set()
    for app in apps:
        categories = [
            category
            for category in app.categories
            if allowed_categories is None or category in allowed_categories
        ]
        if not categories:
            continue
        category = min(categories, key=lambda item: (len(grouped[item]), item))
        key = normalize_repo_url(app.repo_url)
        if key in seen:
            continue
        seen.add(key)
        grouped[category].append(app)

    ordered = []
    categories = sorted(grouped)
    while categories:
        next_categories = []
        for category in categories:
            queue = grouped[category]
            if queue:
                ordered.append((queue.popleft(), category))
            if queue:
                next_categories.append(category)
        categories = next_categories
    return ordered


def scan_existing_root(
    clone_root: Path,
    output_dir: Path,
    min_screens: int,
    selected_screen_limit: int,
    min_fixable_issues: int,
    max_fixable_issues: int,
    metadata_report: Path | None = None,
    target: int = 40,
    max_per_category: int = 1,
) -> list[AppScan]:
    metadata_by_repo = {}
    metadata_by_name = {}
    if metadata_report and metadata_report.exists():
        payload = json.loads(metadata_report.read_text(encoding="utf-8"))
        for item in payload.get("apps", []):
            app = FdroidApp(
                app_id=item.get("app_id") or item.get("name"),
                name=item.get("name") or item.get("app_id"),
                categories=item.get("categories") or [item.get("category", "Unknown")],
                license=item.get("license", "Unknown"),
                repo_url=item.get("repo_url", ""),
                source_code_url=item.get("repo_url", ""),
                metadata_file=str(metadata_report),
            )
            if app.repo_url:
                metadata_by_repo[normalize_repo_url(app.repo_url)] = (
                    app,
                    item.get("category"),
                )
            metadata_by_name[app.name.lower()] = (app, item.get("category"))

    scans = []
    for repo in sorted(clone_root.iterdir()) if clone_root.exists() else []:
        if not repo.is_dir() or not (repo / ".git").exists():
            continue
        origin = get_origin_url(repo)
        metadata = metadata_by_repo.get(normalize_repo_url(origin))
        if metadata is None:
            metadata = metadata_by_name.get(repo.name.lower())
        app, category = metadata if metadata else (None, None)
        scans.append(scan_repository(
            repo,
            app=app,
            category=category,
            min_screens=min_screens,
            selected_screen_limit=selected_screen_limit,
            min_fixable_issues=min_fixable_issues,
            max_fixable_issues=max_fixable_issues,
        ))

    scans.sort(
        key=lambda scan: (
            not scan.eligible,
            scan.category == "Unknown",
            scan.category,
            scan.name.lower(),
        )
    )
    category_counts = Counter()
    for scan in scans:
        if not scan.eligible:
            continue
        if (
            max_per_category > 0
            and category_counts[scan.category] >= max_per_category
        ):
            scan.eligible = False
            scan.exclusion_reasons.append("category quota already filled")
            continue
        category_counts[scan.category] += 1
    scans.sort(
        key=lambda scan: (
            not scan.eligible,
            scan.category == "Unknown",
            scan.category,
            scan.name.lower(),
        )
    )
    write_reports(scans, output_dir, target=target)
    return scans


def write_reports(scans: list[AppScan], output_dir: Path, target: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = [scan for scan in scans if scan.eligible][:target]
    payload = {
        "summary": {
            "attempted": len(scans),
            "eligible": sum(scan.eligible for scan in scans),
            "selected": len(selected),
            "categories": dict(Counter(scan.category for scan in selected)),
        },
        "apps": [serialize_scan(scan) for scan in scans],
    }
    (output_dir / "app_screening.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "selected_apps.json").write_text(
        json.dumps(
            {
                "target": target,
                "selected_count": len(selected),
                "apps": [serialize_scan(scan) for scan in selected],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "selected",
        "app_id",
        "name",
        "category",
        "categories",
        "license",
        "repo_url",
        "local_path",
        "clone_status",
        "eligible",
        "exclusion_reasons",
        "layout_xml_count",
        "screen_candidate_count",
        "selected_screens",
        "composable_function_count",
        "detector_issue_count",
        "detector_fixable_issue_count",
        "detector_review_issue_count",
    ]
    selected_ids = {scan.app_id for scan in selected}
    with (output_dir / "app_screening.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for scan in scans:
            writer.writerow({
                "selected": scan.app_id in selected_ids,
                "app_id": scan.app_id,
                "name": scan.name,
                "category": scan.category,
                "categories": "|".join(scan.categories),
                "license": scan.license,
                "repo_url": scan.repo_url,
                "local_path": scan.local_path,
                "clone_status": scan.clone_status,
                "eligible": scan.eligible,
                "exclusion_reasons": "|".join(scan.exclusion_reasons),
                "layout_xml_count": scan.layout_xml_count,
                "screen_candidate_count": scan.screen_candidate_count,
                "selected_screens": "|".join(item.relative_path for item in scan.selected_screens),
                "composable_function_count": scan.composable_function_count,
                "detector_issue_count": scan.detector_issue_count,
                "detector_fixable_issue_count": scan.detector_fixable_issue_count,
                "detector_review_issue_count": scan.detector_review_issue_count,
            })


def serialize_scan(scan: AppScan) -> dict:
    data = asdict(scan)
    data["selected_screens"] = [asdict(item) for item in scan.selected_screens]
    return data


def run_pipeline(args) -> list[AppScan]:
    clone_root = Path(args.clone_root).expanduser().resolve()
    metadata_dir = Path(args.metadata_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    ensure_metadata_repo(metadata_dir, args.metadata_repo, args.update_metadata)
    apps = parse_fdroid_metadata(metadata_dir)

    allowed = None
    if args.categories:
        allowed = {item.strip() for item in args.categories.split(",") if item.strip()}
    candidates = balanced_candidates(apps, allowed)
    if args.max_candidates:
        candidates = candidates[:args.max_candidates]

    clone_root.mkdir(parents=True, exist_ok=True)
    existing = existing_repo_map(clone_root)
    reserved = {path.name.lower() for path in clone_root.iterdir() if path.is_dir()}
    destinations = {}
    for app, _ in candidates:
        existing_path = existing.get(normalize_repo_url(app.repo_url))
        destinations[app.app_id] = existing_path or destination_for(app, clone_root, reserved)

    scans: list[AppScan] = []
    selected_category_counts = Counter()
    candidate_index = 0
    batch_size = max(args.jobs * 2, 4)

    while candidate_index < len(candidates):
        if sum(scan.eligible for scan in scans) >= args.target:
            break
        batch = candidates[candidate_index:candidate_index + batch_size]
        candidate_index += len(batch)
        futures = {}
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            for app, category in batch:
                if selected_category_counts[category] >= args.max_per_category:
                    continue
                destination = destinations[app.app_id]
                futures[executor.submit(
                    clone_repository,
                    app,
                    destination,
                    args.clone_timeout,
                )] = (
                    app,
                    category,
                    destination,
                )

            for future in as_completed(futures):
                app, category, destination = futures[future]
                try:
                    clone_status, error = future.result()
                except Exception as exc:  # pragma: no cover - defensive boundary
                    clone_status, error = "failed", str(exc)

                if clone_status == "failed":
                    scans.append(AppScan(
                        app_id=app.app_id,
                        name=app.name,
                        category=category,
                        categories=app.categories,
                        license=app.license,
                        repo_url=app.repo_url,
                        local_path=str(destination),
                        clone_status="failed",
                        eligible=False,
                        exclusion_reasons=[f"clone failed: {error}"],
                        android_app_modules=[],
                        layout_xml_count=0,
                        screen_candidate_count=0,
                        selected_screens=[],
                        supporting_layout_count=0,
                        composable_function_count=0,
                        kotlin_java_file_count=0,
                        detector_issue_count=None,
                        detector_fixable_issue_count=None,
                        detector_review_issue_count=None,
                        detector_issue_codes={},
                    ))
                    continue

                scan = scan_repository(
                    destination,
                    app=app,
                    category=category,
                    min_screens=args.min_screens,
                    selected_screen_limit=args.screens_per_app,
                    run_a11y_detector=not args.skip_detector,
                    min_fixable_issues=args.min_fixable_issues,
                    max_fixable_issues=args.max_fixable_issues,
                    clone_status=clone_status,
                )
                if (
                    scan.eligible
                    and selected_category_counts[category] >= args.max_per_category
                ):
                    scan.eligible = False
                    scan.exclusion_reasons.append("category quota already filled")
                elif scan.eligible:
                    selected_category_counts[category] += 1
                scans.append(scan)

        write_reports(scans, output_dir, args.target)
        print(
            f"已扫描 {len(scans)} 个候选，合格 {sum(scan.eligible for scan in scans)}，"
            f"目标 {args.target}",
            file=sys.stderr,
        )

    scans.sort(key=lambda scan: (not scan.eligible, scan.category, scan.name.lower()))
    write_reports(scans, output_dir, args.target)
    return scans


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按类别筛选并批量克隆适合 Android XML 静态无障碍实验的 F-Droid app。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan-local", help="扫描已经克隆到本地的 Android 项目")
    scan.add_argument("clone_root", help="包含多个 Android Git 仓库的目录")
    scan.add_argument("--output-dir", default="reports/fdroid_screening")
    scan.add_argument(
        "--metadata-report",
        help="已有 app_screening.json；用于恢复 F-Droid app id、类别和许可证",
    )
    scan.add_argument("--target", type=int, default=40)
    scan.add_argument(
        "--max-per-category",
        type=int,
        default=1,
        help="正式候选中每个类别最多保留的 app 数；0 表示不限制",
    )
    scan.add_argument("--min-screens", type=int, default=2)
    scan.add_argument("--screens-per-app", type=int, default=3)
    scan.add_argument(
        "--min-fixable-issues",
        type=int,
        default=0,
        help="每个 app 推荐界面至少包含的可自动修复问题数 (default: 0)",
    )
    scan.add_argument(
        "--max-fixable-issues",
        type=int,
        default=0,
        help="每个 app 推荐界面的可自动修复问题数上限；0 表示不限制",
    )

    pipeline = subparsers.add_parser(
        "clone-screen",
        help="同步 F-Droid 元数据、按类别批量浅克隆并筛选",
    )
    pipeline.add_argument(
        "--clone-root",
        default="fdroid_apps/selected",
        help="候选源码克隆目录",
    )
    pipeline.add_argument(
        "--metadata-dir",
        default="fdroid_apps/_fdroiddata",
        help="fdroiddata 元数据仓库目录",
    )
    pipeline.add_argument("--metadata-repo", default=DEFAULT_METADATA_REPO)
    pipeline.add_argument("--update-metadata", action="store_true")
    pipeline.add_argument("--output-dir", default="reports/fdroid_screening")
    pipeline.add_argument("--target", type=int, default=40)
    pipeline.add_argument("--min-screens", type=int, default=2)
    pipeline.add_argument("--screens-per-app", type=int, default=3)
    pipeline.add_argument(
        "--min-fixable-issues",
        type=int,
        default=1,
        help="每个 app 推荐界面至少包含的可自动修复问题数 (default: 1)",
    )
    pipeline.add_argument(
        "--max-fixable-issues",
        type=int,
        default=40,
        help="排除问题规模过大的界面集合 (default: 40)",
    )
    pipeline.add_argument(
        "--max-per-category",
        type=int,
        default=1,
        help="每个 F-Droid 类别最多选择的 app 数 (default: 1)",
    )
    pipeline.add_argument("--max-candidates", type=int, default=160)
    pipeline.add_argument("--jobs", type=int, default=4)
    pipeline.add_argument(
        "--clone-timeout",
        type=int,
        default=300,
        help="单个 Git 仓库克隆超时秒数 (default: 300)",
    )
    pipeline.add_argument(
        "--categories",
        help="只允许这些 F-Droid 类别，逗号分隔；默认使用全部类别",
    )
    pipeline.add_argument(
        "--skip-detector",
        action="store_true",
        help="只做结构筛选，不运行 Android XML 无障碍检测器",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "scan-local":
        scans = scan_existing_root(
            Path(args.clone_root).expanduser().resolve(),
            Path(args.output_dir).expanduser().resolve(),
            args.min_screens,
            args.screens_per_app,
            args.min_fixable_issues,
            args.max_fixable_issues,
            (
                Path(args.metadata_report).expanduser().resolve()
                if args.metadata_report
                else None
            ),
            args.target,
            args.max_per_category,
        )
    else:
        scans = run_pipeline(args)

    eligible = [scan for scan in scans if scan.eligible]
    print(f"扫描完成：{len(scans)} 个候选，{len(eligible)} 个合格。")
    for scan in eligible:
        screens = ", ".join(item.name for item in scan.selected_screens)
        print(f"- [{scan.category}] {scan.name}: {screens}")


if __name__ == "__main__":
    main()
