#!/usr/bin/env python3
"""Analyze Android UIAutomator hierarchy dumps for accessibility issues.

Input is normally produced by:
  adb shell uiautomator dump /sdcard/window.xml
  adb pull /sdcard/window.xml

The script can also run those adb commands with --dump when a device/emulator is
connected. Output is normalized for the RAG repair loop.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


GENERIC_LABELS = {
    "more",
    "options",
    "menu",
    "open",
    "close",
    "delete",
    "edit",
    "button",
    "image",
    "icon",
    "更多",
    "菜单",
    "选项",
    "打开",
    "关闭",
    "删除",
    "编辑",
    "按钮",
    "图片",
    "图标",
}

BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_bool(value):
    return str(value).lower() == "true"


def node_class(node):
    return node.attrib.get("class", "").rsplit(".", 1)[-1]


def node_name(node):
    text = (node.attrib.get("text") or "").strip()
    content_desc = (node.attrib.get("content-desc") or "").strip()
    return content_desc or text


def node_path(stack):
    parts = []
    for node in stack:
        parts.append(f"{node_class(node) or 'node'}[{node.attrib.get('index', '0')}]")
    return "/" + "/".join(parts)


def build_parent_map(root):
    return {child: parent for parent in root.iter("node") for child in list(parent)}


def build_stack(node, parent_map):
    stack = []
    current = node
    while current is not None:
        stack.append(current)
        current = parent_map.get(current)
    return list(reversed(stack))


def parse_bounds(value):
    match = BOUNDS_RE.match(value or "")
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width_px": max(0, right - left),
        "height_px": max(0, bottom - top),
    }


def make_issue(node, parent_map, code, severity, message, related_docs, repair_query):
    return {
        "type": severity,
        "code": code,
        "message": message,
        "element": node_class(node),
        "selector": node_path(build_stack(node, parent_map)),
        "attributes": dict(node.attrib),
        "related_docs": related_docs,
        "repair_query": repair_query,
    }


def is_actionable(node):
    return any(parse_bool(node.attrib.get(name)) for name in ["clickable", "long-clickable", "checkable", "scrollable"])


def is_enabled(node):
    return node.attrib.get("enabled", "true") != "false"


def is_visible_to_user(node):
    return node.attrib.get("visible-to-user", "true") != "false"


def analyze_dump(path, density=1.0):
    tree = ET.parse(path)
    root = tree.getroot()
    parent_map = build_parent_map(root)
    issues = []
    names = defaultdict(list)

    for node in root.iter("node"):
        if not is_visible_to_user(node) or not is_enabled(node):
            continue
        name = node_name(node)
        actionable = is_actionable(node)
        focusable = parse_bool(node.attrib.get("focusable"))
        class_name = node_class(node)

        if actionable and not name:
            issues.append(make_issue(
                node,
                parent_map,
                "ANDROID_UIA_ACTIONABLE_NODE_MISSING_NAME",
                "error",
                "运行时可操作节点缺少 text/content-desc，TalkBack 可能无法说明其用途。",
                ["android.rule.content-labels", "android.fixmap.content-labeling"],
                "Android UIAutomator clickable node missing text content-desc contentDescription",
            ))

        if actionable:
            bounds = parse_bounds(node.attrib.get("bounds"))
            if bounds:
                width_dp = bounds["width_px"] / density
                height_dp = bounds["height_px"] / density
                if width_dp < 48 or height_dp < 48:
                    issues.append(make_issue(
                        node,
                        parent_map,
                        "ANDROID_UIA_TOUCH_TARGET_TOO_SMALL",
                        "error",
                        f"运行时可操作节点尺寸约为 {width_dp:.1f}dp x {height_dp:.1f}dp，小于 48dp 推荐目标。",
                        ["android.rule.touch-targets-contrast", "android.fixmap.touch-target-small"],
                        "Android UIAutomator touch target too small 48dp bounds",
                    ))

        if focusable and not actionable and not name:
            issues.append(make_issue(
                node,
                parent_map,
                "ANDROID_UIA_UNNAMED_FOCUSABLE_NODE",
                "warning",
                "运行时可聚焦节点没有名称且不可操作，可能造成无意义焦点停靠。",
                ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                "Android UIAutomator focusable node no name duplicate focus",
            ))

        if class_name in {"ImageView", "ImageButton"} and not name and actionable:
            issues.append(make_issue(
                node,
                parent_map,
                "ANDROID_UIA_IMAGE_ACTION_MISSING_DESCRIPTION",
                "error",
                "运行时图像操作节点缺少 content-desc。",
                ["android.rule.content-labels", "android.fixmap.content-labeling"],
                "Android UIAutomator ImageButton missing content-desc",
            ))

        if name and actionable:
            names[name.strip().lower()].append(node)

    for name, nodes in names.items():
        if len(nodes) < 2:
            continue
        if name in GENERIC_LABELS or len(name) <= 8:
            for node in nodes:
                issues.append(make_issue(
                    node,
                    parent_map,
                    "ANDROID_UIA_REPEATED_GENERIC_LABEL",
                    "warning",
                    f"运行时多个可操作节点使用相同且较泛的名称：{name!r}。",
                    ["android.pattern.list-item-actions", "android.fixcase.recycler-overflow-generic-label"],
                    "Android UIAutomator repeated generic label list item content-desc",
                ))

    return issues


def run_adb_dump(output_path):
    dump_remote = "/sdcard/window.xml"
    dump = subprocess.run(
        ["adb", "shell", "uiautomator", "dump", dump_remote],
        capture_output=True,
        text=True,
    )
    if dump.returncode != 0:
        return dump
    pull = subprocess.run(
        ["adb", "pull", dump_remote, str(output_path)],
        capture_output=True,
        text=True,
    )
    return pull


def summarize(issues):
    counts = {"error": 0, "warning": 0, "notice": 0}
    for issue in issues:
        issue_type = issue.get("type", "notice")
        counts[issue_type] = counts.get(issue_type, 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description="Analyze Android UIAutomator hierarchy dumps for accessibility issues.")
    parser.add_argument("dump_file", nargs="?", help="UIAutomator XML dump file")
    parser.add_argument("--dump", action="store_true", help="Run adb uiautomator dump before analyzing")
    parser.add_argument("--output", default=None, help="Where to save adb dump when --dump is used")
    parser.add_argument("--density", type=float, default=1.0, help="Device density used to convert px bounds to dp (default: 1.0)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    temp_file = None
    if args.dump:
        output = Path(args.output).resolve() if args.output else None
        if output is None:
            temp = tempfile.NamedTemporaryFile(prefix="uiautomator-", suffix=".xml", delete=False)
            temp_file = Path(temp.name)
            temp.close()
            output = temp_file
        result = run_adb_dump(output)
        if result.returncode != 0:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)
        dump_path = output
    else:
        if not args.dump_file:
            print("请提供 UIAutomator XML dump 文件，或使用 --dump 从连接设备获取。", file=sys.stderr)
            sys.exit(1)
        dump_path = Path(args.dump_file).resolve()

    if not dump_path.exists():
        print(f"dump 文件不存在：{dump_path}", file=sys.stderr)
        sys.exit(1)

    try:
        issues = analyze_dump(dump_path, density=args.density)
    except ET.ParseError as exc:
        print(f"UIAutomator XML 解析失败：{exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if temp_file and temp_file.exists():
            temp_file.unlink()

    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        return

    counts = summarize(issues)
    print("Android UIAutomator 运行时页面无障碍检测")
    print(f"dump 文件：{dump_path}")
    print(f"问题总数：{len(issues)}，错误：{counts.get('error', 0)}，警告：{counts.get('warning', 0)}")
    if not issues:
        print("未发现此运行时层级检测器可识别的问题。仍建议进行 TalkBack/Switch Access 人工测试。")
        return

    for index, issue in enumerate(issues, start=1):
        print()
        print(f"{index}. [{issue['type']}] {issue['code']}")
        print(f"   元素：{issue['element']}  位置：{issue['selector']}")
        print(f"   信息：{issue['message']}")
        print(f"   RAG 查询：{issue['repair_query']}")


if __name__ == "__main__":
    main()
