#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "knowledge" / "sources" / "wcag_rules.json"
WCAG_URL = "https://www.w3.org/TR/WCAG22/"


def strip_tags(fragment):
    fragment = re.sub(r"<script[\s\S]*?</script>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<style[\s\S]*?</style>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<div class=\"header-wrapper\">[\s\S]*?</div>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<div class=\"doclinks\">[\s\S]*?</div>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<p class=\"conformance-level\">[\s\S]*?</p>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"</(p|li|dt|dd|blockquote|div|h[1-6])>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<dt[^>]*>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<dd[^>]*>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<li[^>]*>", "\n- ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(fragment)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_section(document, slug):
    pattern = re.compile(
        rf"<section id=\"{re.escape(slug)}\" class=\"guideline\">([\s\S]*?)</section>",
        flags=re.IGNORECASE,
    )
    match = pattern.search(document)
    if not match:
        return ""
    return strip_tags(match.group(1))


def main():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    document = urlopen(WCAG_URL, timeout=30).read().decode("utf-8", "ignore")
    missing = []

    for rule in rules:
        source = rule.get("source", {})
        standard_url = source.get("standard_url", "")
        slug = standard_url.rsplit("#", 1)[-1]
        official_text = extract_section(document, slug)
        if not official_text:
            missing.append(rule["id"])
            continue
        rule["official_text_en"] = official_text
        rule["official_text_source_url"] = standard_url or WCAG_URL

    RULES_PATH.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已为 {len(rules) - len(missing)} 条规则补充 official_text_en。")
    if missing:
        print("未找到官方原文的规则：")
        for rule_id in missing:
            print(f"- {rule_id}")


if __name__ == "__main__":
    main()
