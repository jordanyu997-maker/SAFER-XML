#!/usr/bin/env python3
"""Run or parse Android Lint reports and normalize accessibility findings.

The script can either:
- run a Gradle lint task in an Android project, then parse lint XML reports; or
- parse an existing lint-results*.xml file.

Output is shaped for the RAG repair loop: each issue includes related_docs and
repair_query fields.
"""
import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ACCESSIBILITY_KEYWORDS = {
    "accessibility",
    "contentdescription",
    "content description",
    "clickableviewaccessibility",
    "touch target",
    "speakable",
    "label",
    "autofill",
    "hardcodedtext",
    "hardcoded text",
    "contrast",
    "focus",
    "performclick",
    "textcontrast",
}

ISSUE_MAPPINGS = {
    "ContentDescription": {
        "related_docs": ["android.rule.content-labels", "android.fixmap.content-labeling"],
        "repair_query": "Android lint ContentDescription missing contentDescription accessibility label",
    },
    "ClickableViewAccessibility": {
        "related_docs": ["android.rule.custom-views", "android.fixmap.clickable-view-accessibility"],
        "repair_query": "Android lint ClickableViewAccessibility performClick onTouchEvent custom View",
    },
    "HardcodedText": {
        "related_docs": ["android.rule.content-labels", "android.rule.forms-errors"],
        "repair_query": "Android lint HardcodedText use string resource text contentDescription hint localization",
    },
    "LabelFor": {
        "related_docs": ["android.rule.forms-errors", "android.fixmap.textfield-error-not-announced"],
        "repair_query": "Android lint labelFor EditText TextInputEditText input label association",
    },
    "TextContrast": {
        "related_docs": ["android.rule.touch-targets-contrast", "android.fixmap.low-contrast"],
        "repair_query": "Android lint text contrast low contrast color token Material theme",
    },
    "Autofill": {
        "related_docs": ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
        "repair_query": "Android lint autofillHints input purpose email password name phone WCAG 1.3.5",
    },
}

DEFAULT_MAPPING = {
    "related_docs": ["android.eval.testing-toolchain"],
    "repair_query": "Android lint accessibility issue repair",
}


def normalize_type(severity):
    severity = (severity or "").lower()
    if severity in {"fatal", "error"}:
        return "error"
    if severity in {"warning"}:
        return "warning"
    return "notice"


def is_accessibility_related(issue):
    text = " ".join([
        issue.get("id", ""),
        issue.get("category", ""),
        issue.get("message", ""),
        issue.get("summary", ""),
        issue.get("explanation", ""),
    ]).lower()
    return any(keyword in text for keyword in ACCESSIBILITY_KEYWORDS)


def mapping_for(issue_id, message):
    for key, mapping in ISSUE_MAPPINGS.items():
        if key.lower() in issue_id.lower() or key.lower() in message.lower():
            return mapping
    if "touch" in message.lower() and "target" in message.lower():
        return {
            "related_docs": ["android.rule.touch-targets-contrast", "android.fixmap.touch-target-small"],
            "repair_query": "Android lint touch target too small 48dp minWidth minHeight padding",
        }
    return DEFAULT_MAPPING


def parse_lint_xml(path, include_all=False):
    tree = ET.parse(path)
    root = tree.getroot()
    issues = []
    for issue in root.findall("issue"):
        raw = {
            "id": issue.attrib.get("id", ""),
            "severity": issue.attrib.get("severity", ""),
            "category": issue.attrib.get("category", ""),
            "message": issue.attrib.get("message", ""),
            "summary": issue.attrib.get("summary", ""),
            "explanation": issue.attrib.get("explanation", ""),
        }
        if not include_all and not is_accessibility_related(raw):
            continue
        locations = []
        for location in issue.findall("location"):
            locations.append({
                "file": location.attrib.get("file", ""),
                "line": location.attrib.get("line", ""),
                "column": location.attrib.get("column", ""),
            })
        mapping = mapping_for(raw["id"], raw["message"])
        primary = locations[0] if locations else {}
        issues.append({
            "type": normalize_type(raw["severity"]),
            "code": f"ANDROID_LINT_{raw['id'] or 'UNKNOWN'}",
            "lint_id": raw["id"],
            "severity": raw["severity"],
            "category": raw["category"],
            "message": raw["message"] or raw["summary"],
            "file": primary.get("file", str(path)),
            "line": primary.get("line", ""),
            "column": primary.get("column", ""),
            "locations": locations,
            "related_docs": mapping["related_docs"],
            "repair_query": mapping["repair_query"],
        })
    return issues


def find_reports(project_dir):
    patterns = [
        "**/build/reports/lint-results*.xml",
        "**/build/reports/lint/lint-results*.xml",
        "**/lint-results*.xml",
    ]
    reports = []
    for pattern in patterns:
        reports.extend(project_dir.glob(pattern))
    return sorted(dict.fromkeys(reports), key=lambda item: item.stat().st_mtime, reverse=True)


def gradle_command(project_dir, task):
    wrapper = project_dir / "gradlew"
    if wrapper.exists():
        return [str(wrapper), task]
    wrapper_bat = project_dir / "gradlew.bat"
    if wrapper_bat.exists():
        return [str(wrapper_bat), task]
    return ["gradle", task]


def run_lint(project_dir, task):
    command = gradle_command(project_dir, task)
    return subprocess.run(command, cwd=project_dir, capture_output=True, text=True)


def summarize(issues):
    counts = {"error": 0, "warning": 0, "notice": 0}
    for issue in issues:
        issue_type = issue.get("type", "notice")
        counts[issue_type] = counts.get(issue_type, 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description="Run or parse Android Lint accessibility findings.")
    parser.add_argument("target", help="Android project directory or lint-results*.xml file")
    parser.add_argument("--task", default="lintDebug", help="Gradle lint task to run when target is a project directory")
    parser.add_argument("--report", default=None, help="Parse a specific lint XML report instead of discovering one")
    parser.add_argument("--no-run", action="store_true", help="Do not run Gradle; only parse existing reports")
    parser.add_argument("--all", action="store_true", help="Include non-accessibility lint findings too")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"路径不存在：{target}", file=sys.stderr)
        sys.exit(1)

    reports = []
    gradle_result = None
    if args.report:
        reports = [Path(args.report).resolve()]
    elif target.is_file():
        reports = [target]
    else:
        if not args.no_run:
            gradle_result = run_lint(target, args.task)
            if gradle_result.returncode not in {0, 1}:
                print(gradle_result.stdout, file=sys.stderr)
                print(gradle_result.stderr, file=sys.stderr)
                sys.exit(gradle_result.returncode)
        reports = find_reports(target)

    if not reports:
        print("未找到 lint XML 报告。可先运行 Gradle lint，或使用 --report 指定 lint-results*.xml。", file=sys.stderr)
        sys.exit(1)

    issues = []
    parse_errors = []
    for report in reports:
        try:
            issues.extend(parse_lint_xml(report, include_all=args.all))
        except ET.ParseError as exc:
            parse_errors.append({
                "type": "error",
                "code": "ANDROID_LINT_REPORT_PARSE_ERROR",
                "message": f"Lint XML 解析失败：{exc}",
                "file": str(report),
                "related_docs": ["android.eval.testing-toolchain"],
                "repair_query": "Android lint report parse error",
            })
    issues.extend(parse_errors)

    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        return

    counts = summarize(issues)
    print("Android Lint 无障碍相关报告")
    print(f"报告文件：{', '.join(str(report) for report in reports)}")
    if gradle_result is not None:
        print(f"Gradle 任务：{args.task}，退出码：{gradle_result.returncode}")
    print(f"问题总数：{len(issues)}，错误：{counts.get('error', 0)}，警告：{counts.get('warning', 0)}，提示：{counts.get('notice', 0)}")
    if not issues:
        print("未发现筛选后的无障碍相关 lint 问题。")
        return

    for index, issue in enumerate(issues, start=1):
        location = issue.get("file", "")
        if issue.get("line"):
            location += f":{issue['line']}"
        print()
        print(f"{index}. [{issue['type']}] {issue['code']}")
        print(f"   位置：{location}")
        print(f"   信息：{issue.get('message', '')}")
        print(f"   RAG 查询：{issue.get('repair_query', '')}")


if __name__ == "__main__":
    main()
