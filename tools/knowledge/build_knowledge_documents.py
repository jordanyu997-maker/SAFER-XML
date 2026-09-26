#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "knowledge" / "sources" / "wcag_rules.json"
PATTERNS_PATH = ROOT / "knowledge" / "sources" / "component_patterns.json"
ANDROID_DOCS_PATH = ROOT / "knowledge" / "sources" / "android_accessibility_documents.json"
ANDROID_FIX_CASES_PATH = ROOT / "knowledge" / "sources" / "android_fix_cases.json"
ANDROID_FIX_MAPPINGS_PATH = ROOT / "knowledge" / "sources" / "android_fix_mappings.json"
OUTPUT_PATH = ROOT / "knowledge" / "rag" / "knowledge_documents.json"


ZH_NAMES = {
    "1.1.1": "非文本内容",
    "1.2.1": "纯音频和纯视频（预录）",
    "1.2.2": "字幕（预录）",
    "1.2.3": "音频描述或媒体替代（预录）",
    "1.2.4": "字幕（直播）",
    "1.2.5": "音频描述（预录）",
    "1.3.1": "信息和关系",
    "1.3.2": "有意义的顺序",
    "1.3.3": "感官特征",
    "1.3.4": "方向",
    "1.3.5": "识别输入目的",
    "1.4.1": "颜色的使用",
    "1.4.2": "音频控制",
    "1.4.3": "最低对比度",
    "1.4.4": "调整文本大小",
    "1.4.5": "文字图片",
    "1.4.10": "重排",
    "1.4.11": "非文本对比度",
    "1.4.12": "文本间距",
    "1.4.13": "悬停或焦点触发的内容",
    "2.1.1": "键盘",
    "2.1.2": "无键盘陷阱",
    "2.1.4": "字符键快捷键",
    "2.2.1": "时间可调整",
    "2.2.2": "暂停、停止、隐藏",
    "2.3.1": "三次闪烁或低于阈值",
    "2.4.1": "绕过区块",
    "2.4.2": "页面标题",
    "2.4.3": "焦点顺序",
    "2.4.4": "链接目的（上下文中）",
    "2.4.5": "多种方式",
    "2.4.6": "标题和标签",
    "2.4.7": "焦点可见",
    "2.4.11": "焦点不被遮挡（最低）",
    "2.5.1": "指针手势",
    "2.5.2": "指针取消",
    "2.5.3": "标签包含在名称中",
    "2.5.4": "运动触发",
    "2.5.7": "拖拽移动",
    "2.5.8": "目标大小（最低）",
    "3.1.1": "页面语言",
    "3.1.2": "局部语言",
    "3.2.1": "获得焦点",
    "3.2.2": "输入时",
    "3.2.3": "一致的导航",
    "3.2.4": "一致的标识",
    "3.2.6": "一致的帮助",
    "3.3.1": "错误识别",
    "3.3.2": "标签或说明",
    "3.3.3": "错误建议",
    "3.3.4": "错误预防（法律、金融、数据）",
    "3.3.7": "冗余输入",
    "3.3.8": "可访问认证（最低）",
    "4.1.2": "名称、角色、值",
    "4.1.3": "状态消息"
}


EN_REQUIREMENTS = {
    "1.1.1": ["Provide text alternatives for meaningful non-text content.", "Use empty alt text for decorative images.", "Icon-only controls need an accessible name."],
    "1.2.1": ["Provide a transcript for prerecorded audio-only content.", "Provide a text or audio alternative for prerecorded video-only content."],
    "1.2.2": ["Provide captions for prerecorded synchronized media.", "Captions should include speech and important sound information."],
    "1.2.3": ["Provide audio description or a media alternative for prerecorded video.", "Cover important visual information that is not available in the audio."],
    "1.2.4": ["Provide captions for live synchronized media.", "Caption controls must be operable without a mouse."],
    "1.2.5": ["Provide audio description for prerecorded video.", "Make the described version discoverable from the page or player."],
    "1.3.1": ["Use semantic HTML to expose information and relationships.", "Associate labels with form controls.", "Use headings, lists, table headers, scope, and captions where appropriate."],
    "1.3.2": ["Keep DOM order consistent with meaningful reading order.", "Avoid using CSS to create a misleading reading order."],
    "1.3.3": ["Do not rely only on shape, color, size, visual location, orientation, or sound for instructions.", "Use textual labels or names in instructions."],
    "1.3.4": ["Do not restrict content to one display orientation unless essential.", "Support both portrait and landscape layouts where possible."],
    "1.3.5": ["Use autocomplete tokens for fields that collect user information.", "Expose the input purpose programmatically."],
    "1.4.1": ["Do not use color as the only way to convey information.", "Pair color with text, icons, labels, patterns, or other non-color cues."],
    "1.4.2": ["Avoid autoplaying audio.", "If audio plays automatically for more than three seconds, provide pause, stop, or volume control."],
    "1.4.3": ["Maintain at least 4.5:1 contrast for normal text.", "Maintain at least 3:1 contrast for large text."],
    "1.4.4": ["Support text resize up to 200% without loss of content or functionality.", "Avoid fixed heights that clip enlarged text."],
    "1.4.5": ["Use real text instead of images of text when possible.", "Provide alternatives for necessary text images such as logos."],
    "1.4.10": ["Allow content to reflow at small viewport widths.", "Avoid fixed-width layouts that require two-dimensional scrolling."],
    "1.4.11": ["Ensure visual boundaries, icons, and focus indicators have sufficient non-text contrast.", "Use visible borders and focus rings."],
    "1.4.12": ["Do not break content when users increase text spacing.", "Allow text containers to wrap and grow."],
    "1.4.13": ["Hover or focus triggered content must be dismissible, hoverable, and persistent.", "Provide keyboard-friendly tooltip and popover behavior."],
    "2.1.1": ["Make all functionality available from the keyboard.", "Prefer native interactive elements.", "Custom widgets need keyboard support."],
    "2.1.2": ["Do not trap keyboard focus.", "Provide a clear way to exit modal or widget focus areas."],
    "2.1.4": ["Avoid global single-character shortcuts.", "Allow shortcuts to be turned off, remapped, or active only on focus."],
    "2.2.1": ["Let users turn off, adjust, or extend time limits unless essential.", "Warn users before session timeouts."],
    "2.2.2": ["Provide controls to pause, stop, or hide moving, blinking, scrolling, or auto-updating content."],
    "2.3.1": ["Avoid flashing content more than three times per second.", "Check animation and video assets for flashing risk."],
    "2.4.1": ["Provide a mechanism to bypass repeated blocks.", "Use skip links and a main landmark."],
    "2.4.2": ["Provide a descriptive page title.", "Update document titles in single-page applications."],
    "2.4.3": ["Use a focus order that preserves meaning and operability.", "Avoid positive tabindex values."],
    "2.4.4": ["Make link purpose clear from link text or context.", "Avoid ambiguous repeated links such as more or click here."],
    "2.4.5": ["Provide more than one way to locate pages when applicable.", "Use navigation, search, sitemap, or related links."],
    "2.4.6": ["Use headings and labels that describe topic or purpose.", "Avoid vague labels."],
    "2.4.7": ["Provide a visible keyboard focus indicator.", "Do not remove outlines without an equivalent replacement."],
    "2.4.11": ["Do not let author-created content fully obscure the focused item.", "Account for sticky headers and overlays."],
    "2.5.1": ["Provide single-pointer alternatives for multipoint or path-based gestures.", "Do not make complex gestures the only way to operate."],
    "2.5.2": ["Avoid irreversible actions on pointer down.", "Use click/up events or provide cancellation and confirmation."],
    "2.5.3": ["Ensure the accessible name contains the visible label.", "Keep aria-label consistent with visible text."],
    "2.5.4": ["Provide interface controls as alternatives to motion actuation.", "Allow motion-triggered features to be disabled."],
    "2.5.7": ["Provide a non-dragging alternative for dragging operations.", "Support buttons or keyboard alternatives for sorting and sliders."],
    "2.5.8": ["Make pointer targets large enough or sufficiently spaced.", "Avoid tiny important touch targets."],
    "3.1.1": ["Declare the default language of the page using the html lang attribute."],
    "3.1.2": ["Mark passages in a different language using the lang attribute."],
    "3.2.1": ["Do not trigger major context changes merely on focus.", "Require an explicit user action for navigation or submission."],
    "3.2.2": ["Do not trigger unexpected major context changes on input.", "Use explicit buttons for major changes."],
    "3.2.3": ["Keep repeated navigation in the same relative order across pages."],
    "3.2.4": ["Identify components with the same functionality consistently."],
    "3.2.6": ["Keep help mechanisms in a consistent relative order when present."],
    "3.3.1": ["Identify input errors in text.", "Associate error messages with fields."],
    "3.3.2": ["Provide labels or instructions for user input.", "Do not use placeholder text as the only label."],
    "3.3.3": ["Provide correction suggestions when possible.", "Make error messages actionable."],
    "3.3.4": ["For legal, financial, or data-changing submissions, provide review, confirmation, or reversal mechanisms."],
    "3.3.7": ["Avoid asking users to re-enter information already provided in the same process unless necessary."],
    "3.3.8": ["Do not require cognitive function tests for authentication unless an accessible alternative exists.", "Support password managers and copy/paste."],
    "4.1.2": ["Expose name, role, and value for user interface components.", "Update ARIA states when custom widgets change."],
    "4.1.3": ["Expose status messages to assistive technologies without necessarily moving focus.", "Use role=status, aria-live, or role=alert appropriately."]
}


COMPONENT_ZH_NAMES = {
    "pattern.login-form": "登录表单",
    "pattern.modal-dialog": "模态对话框",
    "pattern.navigation-menu": "导航菜单",
    "pattern.image-card": "图片卡片",
    "pattern.search-box": "搜索框",
    "pattern.modal-form": "弹窗表单",
    "pattern.tabs-settings": "选项卡设置页",
    "pattern.search-filter-live-results": "搜索筛选动态结果页",
    "pattern.autocomplete-combobox": "自动补全组合框",
    "pattern.sortable-filterable-data-grid": "可排序筛选数据表",
    "pattern.multi-step-form-wizard": "多步骤表单向导",
    "pattern.drag-drop-sortable-list": "拖拽排序列表"
}


COMPONENT_EN_SUMMARIES = {
    "pattern.login-form": "Accessible login form pattern with semantic form controls, labels, autocomplete, error association, keyboard support, and visible focus.",
    "pattern.modal-dialog": "Accessible modal dialog pattern with dialog semantics, accessible name, focus management, close control, and keyboard escape behavior.",
    "pattern.navigation-menu": "Accessible navigation pattern using semantic navigation landmarks, clear links, current page indication, skip links, and keyboard support.",
    "pattern.image-card": "Accessible image card pattern with meaningful alt text, semantic headings, clear link purposes, logical reading order, and visible focus.",
    "pattern.search-box": "Accessible search pattern with labelled search input, submit and clear buttons, stable focus behavior, and live status updates.",
    "pattern.modal-form": "Accessible modal form pattern with dialog semantics, focus management, keyboard dismissal, labelled fields, error association, and status announcements.",
    "pattern.tabs-settings": "Accessible tabs pattern for settings pages with tablist semantics, selected state, controlled tab panels, keyboard arrow navigation, and visible focus.",
    "pattern.search-filter-live-results": "Accessible search and filter results pattern with labelled controls, stable focus behavior, live result count announcements, semantic result lists, and keyboard-operable filters.",
    "pattern.autocomplete-combobox": "Accessible autocomplete combobox pattern with labelled input, combobox/listbox semantics, keyboard suggestion navigation, active descendant state, and live announcements.",
    "pattern.sortable-filterable-data-grid": "Accessible sortable and filterable data grid pattern with native table semantics, labelled filters, keyboard-operable sorting, exposed sort state, and live result updates.",
    "pattern.multi-step-form-wizard": "Accessible multi-step form wizard pattern with semantic step navigation, current step state, labelled fields, error summary, focus management, and confirmation for important submissions.",
    "pattern.drag-drop-sortable-list": "Accessible drag-and-drop sortable list pattern with semantic list structure, keyboard reordering alternatives, item-specific controls, focus preservation, and live position announcements."
}


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_direct_documents(paths):
    documents = []
    for path in paths:
        if not path.exists():
            continue
        payload = load_json(path)
        documents.extend(payload.get("documents", []))
    return documents


def split_keywords(values):
    zh = []
    en = []
    for value in values:
        target = zh if has_cjk(value) else en
        if value not in target:
            target.append(value)
    return en, zh


def has_cjk(text):
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def english_summary(rule):
    return f"WCAG {rule['id']} {rule['name']} requires accessible implementation for {', '.join(rule.get('applies_to', [])[:5]) or 'web content'}."


def make_example(example, fallback_title_en, fallback_title_zh):
    return {
        "title_en": fallback_title_en,
        "title_zh": example.get("title", fallback_title_zh),
        "code": example.get("code", ""),
        "explanation_en": "This example is used as a concrete implementation reference for generation or repair.",
        "explanation_zh": example.get("why", "")
    }


def make_component_example(example, fallback_title_en, fallback_title_zh):
    return {
        "title_en": fallback_title_en,
        "title_zh": example.get("title", fallback_title_zh),
        "code": example.get("code", ""),
        "explanation_en": "This component example illustrates an accessible or inaccessible interaction pattern.",
        "explanation_zh": example.get("why", "")
    }


def make_wcag_document(rule):
    keywords_en, keywords_zh = split_keywords(rule.get("keywords", []))
    requirements_en = EN_REQUIREMENTS.get(rule["id"], [english_summary(rule)])
    requirements_zh = rule.get("generation_constraints", rule.get("code_constraints", []))
    repair_zh = rule.get("repair_suggestions", [])
    repair_en = requirements_en[: min(3, len(requirements_en))]
    good_examples = [
        make_example(example, "Good example", "正确示例")
        for example in rule.get("good_examples", [])
    ]
    bad_examples = [
        make_example(example, "Bad example", "错误示例")
        for example in rule.get("bad_examples", [])
    ]
    title_zh = rule.get("name_zh") or ZH_NAMES.get(rule["id"], rule["name"])
    summary_en = english_summary(rule)
    summary_zh = rule.get("rule", "")
    search_text_en = " ".join([
        rule["id"],
        rule["name"],
        rule.get("official_text_en", ""),
        summary_en,
        " ".join(requirements_en),
        " ".join(keywords_en),
        " ".join(example["code"] for example in good_examples + bad_examples),
    ])
    search_text_zh = " ".join([
        rule["id"],
        title_zh,
        summary_zh,
        " ".join(requirements_zh),
        " ".join(keywords_zh),
        " ".join(repair_zh),
    ])
    return {
        "doc_id": f"wcag22.sc.{rule['id']}",
        "doc_type": "wcag_success_criterion",
        "standard": "WCAG 2.2",
        "language": "bilingual",
        "priority": "required" if rule.get("level") in {"A", "AA"} else "recommended",
        "conformance": {
            "level": rule.get("level"),
            "principle": rule.get("principle")
        },
        "source": {
            "title_en": f"{rule['id']} {rule['name']}",
            "title_zh": f"{rule['id']} {title_zh}",
            "standard_url": rule.get("source", {}).get("standard_url", ""),
            "understanding_url": rule.get("source", {}).get("understanding_url", ""),
            "techniques_urls": rule.get("source", {}).get("techniques_urls", []),
            "apg_urls": rule.get("source", {}).get("apg_urls", [])
        },
        "tags": {
            "applies_to": rule.get("applies_to", []),
            "keywords_en": keywords_en,
            "keywords_zh": keywords_zh,
            "related_wcag": [rule["id"]]
        },
        "content": {
            "summary_en": summary_en,
            "summary_zh": summary_zh,
            "official_text_en": rule.get("official_text_en", ""),
            "intent_en": summary_en,
            "intent_zh": rule.get("intent", ""),
            "requirements_en": requirements_en,
            "requirements_zh": requirements_zh,
            "good_examples": good_examples,
            "bad_examples": bad_examples,
            "repair_suggestions_en": repair_en,
            "repair_suggestions_zh": repair_zh,
            "manual_checks_en": rule.get("detection", {}).get("test_steps", []),
            "manual_checks_zh": rule.get("detection", {}).get("test_steps", [])
        },
        "retrieval": {
            "search_text_en": search_text_en,
            "search_text_zh": search_text_zh,
            "search_text_mixed": f"{search_text_en}\n{search_text_zh}"
        }
    }


def make_component_document(pattern):
    keywords_en, keywords_zh = split_keywords(pattern.get("keywords", []))
    title_zh = pattern.get("name_zh") or COMPONENT_ZH_NAMES.get(pattern["id"], pattern["name"])
    summary_en = COMPONENT_EN_SUMMARIES.get(pattern["id"], f"Accessible {pattern['name']} component pattern.")
    summary_zh = f"{title_zh}组件的无障碍实现模式。"
    requirements_zh = pattern.get("generation_constraints", [])
    requirements_en = [summary_en]
    good_examples = [
        make_component_example(example, "Good component example", "正确组件示例")
        for example in pattern.get("good_examples", [])
    ]
    bad_examples = [
        make_component_example(example, "Bad component example", "错误组件示例")
        for example in pattern.get("bad_examples", [])
    ]
    search_text_en = " ".join([
        pattern["id"],
        pattern["name"],
        summary_en,
        " ".join(keywords_en),
        " ".join(pattern.get("related_wcag", [])),
        " ".join(example["code"] for example in good_examples + bad_examples),
    ])
    search_text_zh = " ".join([
        pattern["id"],
        title_zh,
        summary_zh,
        " ".join(requirements_zh),
        " ".join(keywords_zh),
        " ".join(pattern.get("manual_checks", [])),
        " ".join(example["explanation_zh"] for example in good_examples + bad_examples),
    ])
    return {
        "doc_id": pattern["id"],
        "doc_type": "component_pattern",
        "standard": "local",
        "language": "bilingual",
        "priority": "recommended",
        "conformance": {
            "level": None,
            "principle": None
        },
        "source": {
            "title_en": pattern["name"],
            "title_zh": title_zh,
            "standard_url": "",
            "understanding_url": "",
            "techniques_urls": [],
            "apg_urls": []
        },
        "tags": {
            "applies_to": [pattern.get("component_type", "")],
            "keywords_en": keywords_en,
            "keywords_zh": keywords_zh,
            "related_wcag": pattern.get("related_wcag", [])
        },
        "content": {
            "summary_en": summary_en,
            "summary_zh": summary_zh,
            "intent_en": "Provide a reusable component-level accessibility pattern for code generation.",
            "intent_zh": "为代码生成提供可复用的组件级无障碍模式。",
            "requirements_en": requirements_en,
            "requirements_zh": requirements_zh,
            "good_examples": good_examples,
            "bad_examples": bad_examples,
            "repair_suggestions_en": requirements_en,
            "repair_suggestions_zh": requirements_zh,
            "manual_checks_en": [],
            "manual_checks_zh": pattern.get("manual_checks", [])
        },
        "retrieval": {
            "search_text_en": search_text_en,
            "search_text_zh": search_text_zh,
            "search_text_mixed": f"{search_text_en}\n{search_text_zh}"
        }
    }


def main():
    rules = load_json(RULES_PATH)
    patterns = load_json(PATTERNS_PATH)
    android_documents = load_direct_documents([
        ANDROID_DOCS_PATH,
        ANDROID_FIX_CASES_PATH,
        ANDROID_FIX_MAPPINGS_PATH,
    ])
    documents = [make_wcag_document(rule) for rule in rules]
    documents.extend(make_component_document(pattern) for pattern in patterns)
    documents.extend(android_documents)
    payload = {
        "schema_version": "2.0",
        "description": "Bilingual multi-document accessibility knowledge base for RAG retrieval.",
        "documents": documents
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(documents)} documents to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
