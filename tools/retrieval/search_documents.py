#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_PATH = ROOT / "knowledge" / "rag" / "knowledge_documents.json"


def load_documents():
    with DOCS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)["documents"]


def score_document(document, query):
    query_lower = query.lower()
    score = 0
    retrieval = document.get("retrieval", {})
    fields = [
        retrieval.get("search_text_mixed", ""),
        document.get("doc_id", ""),
        document.get("doc_type", ""),
        document.get("source", {}).get("title_en", ""),
        document.get("source", {}).get("title_zh", ""),
    ]
    text = " ".join(fields).lower()
    tokens = query_lower.replace(",", " ").replace("，", " ").split()
    for token in tokens:
        if token in text:
            score += 2
    for keyword in document.get("tags", {}).get("keywords_en", []) + document.get("tags", {}).get("keywords_zh", []):
        if matches_keyword(keyword, query_lower):
            score += 5
    for target in document.get("tags", {}).get("applies_to", []):
        if target.lower() in query_lower:
            score += 3
    if document.get("doc_type") == "component_pattern":
        score += component_boost(document, query_lower)
    return score


def component_boost(document, query_lower):
    title = (document.get("source", {}).get("title_zh", "") + document.get("source", {}).get("title_en", "")).lower()
    keyword_boost = max(
        (
            12
            for keyword in document.get("tags", {}).get("keywords_en", []) + document.get("tags", {}).get("keywords_zh", [])
            if matches_keyword(keyword, query_lower)
        ),
        default=0,
    )
    terms = [
        ("登录", "登录表单", 8),
        ("表单", "登录表单", 4),
        ("弹窗表单", "弹窗表单", 16),
        ("模态表单", "弹窗表单", 16),
        ("表单校验", "弹窗表单", 16),
        ("弹窗", "模态对话框", 8),
        ("对话框", "模态对话框", 8),
        ("导航", "导航菜单", 8),
        ("菜单", "导航菜单", 8),
        ("图片", "图片卡片", 8),
        ("卡片", "图片卡片", 8),
        ("搜索筛选", "搜索筛选动态结果页", 16),
        ("动态结果", "搜索筛选动态结果页", 16),
        ("筛选结果", "搜索筛选动态结果页", 16),
        ("live results", "Search Filter Live Results", 16),
        ("搜索框", "搜索框", 8),
        ("搜索", "搜索框", 4),
        ("选项卡", "选项卡设置页", 16),
        ("标签页", "选项卡设置页", 16),
        ("设置页", "选项卡设置页", 12),
        ("tabs", "Tabs", 16),
        ("自动补全", "自动补全组合框", 18),
        ("联想搜索", "自动补全组合框", 18),
        ("组合框", "自动补全组合框", 18),
        ("下拉建议", "自动补全组合框", 18),
        ("autocomplete", "Autocomplete", 18),
        ("combobox", "Combobox", 18),
        ("数据表格", "可排序筛选数据表", 16),
        ("可排序表格", "可排序筛选数据表", 16),
        ("筛选表格", "可排序筛选数据表", 16),
        ("排序", "可排序筛选数据表", 10),
        ("sortable", "Sortable", 16),
        ("多步骤表单", "多步骤表单向导", 18),
        ("多步骤", "多步骤表单向导", 18),
        ("分步表单", "多步骤表单向导", 18),
        ("结账", "多步骤表单向导", 18),
        ("向导", "多步骤表单向导", 16),
        ("wizard", "Wizard", 18),
        ("拖拽排序", "拖拽排序列表", 18),
        ("拖放", "拖拽排序列表", 18),
        ("看板", "拖拽排序列表", 16),
        ("drag", "Drag", 18),
        ("drop", "Drop", 18),
    ]
    curated_boost = max(
        (weight for term, label, weight in terms if term in query_lower and label.lower() in title),
        default=0,
    )
    return max(keyword_boost, curated_boost)


def matches_keyword(keyword, query_lower):
    keyword_lower = keyword.lower()
    if not keyword_lower:
        return False
    if any("\u4e00" <= char <= "\u9fff" for char in keyword_lower):
        return keyword_lower in query_lower
    if " " in keyword_lower:
        return keyword_lower in query_lower
    return re.search(rf"(?<![a-z0-9_]){re.escape(keyword_lower)}(?![a-z0-9_])", query_lower) is not None


def search(query, limit=8, doc_type=None):
    documents = load_documents()
    if doc_type:
        documents = [document for document in documents if document["doc_type"] == doc_type]
    ranked = sorted(
        ((score_document(document, query), document) for document in documents),
        key=lambda item: item[0],
        reverse=True,
    )
    return [(score, document) for score, document in ranked if score > 0][:limit]


def main():
    parser = argparse.ArgumentParser(description="Search bilingual multi-document accessibility knowledge base.")
    parser.add_argument("query", help="User request, for example: 生成一个登录表单")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--doc-type", choices=[
        "wcag_success_criterion",
        "component_pattern",
        "technique",
        "failure",
        "evaluation_rule",
        "fix_case",
        "fix_mapping",
        "project_context",
    ])
    args = parser.parse_args()

    results = search(args.query, args.limit, args.doc_type)
    if not results:
        print("没有检索到相关文档。")
        return

    for index, (score, document) in enumerate(results, start=1):
        source = document["source"]
        content = document["content"]
        print(f"{index}. [{document['doc_type']}] {source['title_en']} / {source['title_zh']}  score={score}")
        if content.get("official_text_en"):
            print(f"   Official: {content['official_text_en'][:240]}")
        print(f"   EN: {content['summary_en']}")
        print(f"   ZH: {content['summary_zh']}")
        if content["requirements_zh"]:
            print("   约束：")
            for item in content["requirements_zh"][:4]:
                print(f"   - {item}")
        print()


if __name__ == "__main__":
    main()
