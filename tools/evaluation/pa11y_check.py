#!/usr/bin/env python3
import argparse
import contextlib
import http.server
import json
import socket
import subprocess
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port):
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(ROOT), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_pa11y(url, standard):
    command = [
        "npx",
        "--no-install",
        "pa11y",
        url,
        "--standard",
        standard,
        "--reporter",
        "json",
    ]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def parse_issues(stdout):
    if not stdout.strip():
        return []
    return json.loads(stdout)


def summarize(issues):
    counts = {"error": 0, "warning": 0, "notice": 0}
    for issue in issues:
        issue_type = issue.get("type", "unknown")
        if issue_type in counts:
            counts[issue_type] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description="Run Pa11y WCAG checks against a local HTML file.")
    parser.add_argument("html_file", help="Path to an HTML file, for example: generated/result.html")
    parser.add_argument("--standard", default="WCAG2AA", choices=["WCAG2A", "WCAG2AA", "WCAG2AAA"])
    parser.add_argument("--json", action="store_true", help="Print raw Pa11y JSON output")
    args = parser.parse_args()

    html_path = (ROOT / args.html_file).resolve()
    if not html_path.exists():
        print(f"文件不存在：{html_path}", file=sys.stderr)
        sys.exit(1)
    if ROOT not in html_path.parents and html_path != ROOT:
        print("只能检测项目目录内的 HTML 文件。", file=sys.stderr)
        sys.exit(1)

    port = find_free_port()
    relative_path = html_path.relative_to(ROOT).as_posix()
    url = f"http://127.0.0.1:{port}/{relative_path}"

    server = start_server(port)
    try:
        result = run_pa11y(url, args.standard)
    finally:
        server.shutdown()

    if result.returncode == 1 and "could not determine executable" in result.stderr.lower():
        print("未找到本地 pa11y。请先运行：npm install", file=sys.stderr)
        sys.exit(1)

    if result.stderr.strip() and result.returncode not in {0, 2}:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)

    try:
        issues = parse_issues(result.stdout)
    except json.JSONDecodeError:
        print("Pa11y 输出不是有效 JSON：", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr, file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        return

    counts = summarize(issues)
    print(f"Pa11y 检测目标：{relative_path}")
    print(f"标准：{args.standard}")
    print(f"问题总数：{len(issues)}，错误：{counts['error']}，警告：{counts['warning']}，提示：{counts['notice']}")

    if not issues:
        print("未发现 Pa11y 可识别的无障碍问题。仍建议继续人工键盘测试和屏幕阅读器测试。")
        return

    for index, issue in enumerate(issues, start=1):
        print()
        print(f"{index}. [{issue.get('type', 'unknown')}] {issue.get('code', 'unknown')}")
        print(f"   信息：{issue.get('message', '').strip()}")
        print(f"   选择器：{issue.get('selector', 'N/A')}")
        context = issue.get("context", "")
        if context:
            print(f"   片段：{context[:240]}")


if __name__ == "__main__":
    main()
