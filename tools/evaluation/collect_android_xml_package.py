#!/usr/bin/env python3
"""Collect a minimal Android XML resource package for static a11y experiments.

The collector copies layout XML plus resource XML files that help static
analysis and RAG repair understand references such as @string, @dimen, @color,
@style, @drawable, @menu, and @navigation. It intentionally skips bitmap assets,
compiled outputs, and source code.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

RESOURCE_DIR_PREFIXES = (
    "layout",
    "values",
    "drawable",
    "menu",
    "navigation",
    "xml",
)

INCLUDE_LAYOUT_RE = re.compile(
    r"<include\b[^>]*\blayout=[\"']@layout/([^\"']+)[\"']"
)


def find_res_dir(source):
    source = source.resolve()
    if source.name == "res" and source.is_dir():
        return source
    candidates = sorted(source.glob("**/src/main/res"))
    if candidates:
        return candidates[0]
    candidates = sorted(path for path in source.glob("**/res") if path.is_dir())
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"未找到 Android res 目录：{source}")


def layout_name(path, res_dir):
    relative = path.relative_to(res_dir)
    top_dir = relative.parts[0] if relative.parts else ""
    if top_dir.startswith("layout"):
        return path.stem
    return None


def included_layout_names(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return set(INCLUDE_LAYOUT_RE.findall(text))


def resolve_layout_selection(res_dir, selected_layouts):
    if not selected_layouts:
        return None

    available = {}
    for path in res_dir.rglob("*.xml"):
        name = layout_name(path, res_dir)
        if name:
            available.setdefault(name, []).append(path)

    resolved = set()
    pending = list(selected_layouts)
    while pending:
        name = pending.pop()
        if name in resolved:
            continue
        if name not in available:
            raise FileNotFoundError(f"找不到 layout 资源：@layout/{name}")
        resolved.add(name)
        for path in available[name]:
            pending.extend(included_layout_names(path) - resolved)
    return resolved


def should_copy(path, res_dir, selected_layouts=None):
    if path.name == ".DS_Store" or "/build/" in path.as_posix():
        return False
    if path.suffix != ".xml":
        return False
    relative = path.relative_to(res_dir)
    top_dir = relative.parts[0] if relative.parts else ""
    if top_dir.startswith("layout") and selected_layouts is not None:
        return path.stem in selected_layouts
    return top_dir.startswith(RESOURCE_DIR_PREFIXES)


def collect(source, output, force=False, selected_layouts=None):
    res_dir = find_res_dir(source)
    selected_layouts = resolve_layout_selection(res_dir, selected_layouts)
    output = output.resolve()
    if output.exists() and any(output.iterdir()) and not force:
        raise FileExistsError(f"输出目录已存在且非空：{output}。如需覆盖请加 --force。")
    output.mkdir(parents=True, exist_ok=True)

    copied = []
    for path in sorted(res_dir.rglob("*.xml")):
        if not should_copy(path, res_dir, selected_layouts):
            continue
        relative = path.relative_to(res_dir)
        target = output / "res" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(target)
    return res_dir, copied


def main():
    parser = argparse.ArgumentParser(description="Collect Android XML resources for static accessibility testing.")
    parser.add_argument("source", help="Android project directory or app/src/main/res directory")
    parser.add_argument("output", help="Output directory inside the current workspace")
    parser.add_argument("--force", action="store_true", help="Allow copying into a non-empty output directory")
    parser.add_argument(
        "--layouts",
        help=(
            "只复制这些入口 layout 及其递归 <include> 依赖，使用逗号分隔，"
            "例如 activity_main,fragment_settings"
        ),
    )
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if not source.exists():
        print(f"源路径不存在：{source}", file=sys.stderr)
        sys.exit(1)

    try:
        selected_layouts = None
        if args.layouts:
            selected_layouts = {
                item.strip().removeprefix("@layout/").removesuffix(".xml")
                for item in args.layouts.split(",")
                if item.strip()
            }
        res_dir, copied = collect(
            source,
            output,
            force=args.force,
            selected_layouts=selected_layouts,
        )
    except (FileNotFoundError, FileExistsError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    print(f"源 res 目录：{res_dir}")
    print(f"输出目录：{output.resolve()}")
    print(f"已复制 XML 文件：{len(copied)}")
    for path in copied:
        print(path.relative_to(output.resolve()))


if __name__ == "__main__":
    main()
