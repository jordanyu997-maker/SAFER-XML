#!/usr/bin/env python3
"""Static accessibility checks for Android XML layout resources.

This is a lightweight detector for the RAG repair loop. It does not replace
Android Lint, Accessibility Scanner, Espresso, or TalkBack testing, but it can
catch common XML-level accessibility issues before running an app.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ANDROID_NS = "http://schemas.android.com/apk/res/android"
APP_NS = "http://schemas.android.com/apk/res-auto"
TOOLS_NS = "http://schemas.android.com/tools"
RULE_CONFIG_PATH = Path(__file__).with_name("android_xml_a11y_rules.json")
DETECTOR_PROFILES = ("conservative_v1", "expanded_v2", "expanded_v3")
DEFAULT_DETECTOR_PROFILE = "conservative_v1"
INTERACTIVE_WIDGETS = {
    "Button",
    "ImageButton",
    "CheckBox",
    "RadioButton",
    "Switch",
    "SwitchCompat",
    "ToggleButton",
    "SeekBar",
    "Spinner",
    "RatingBar",
    "FloatingActionButton",
    "ExtendedFloatingActionButton",
    "MaterialButton",
    "MaterialSwitch",
    "MaterialCheckBox",
    "MaterialRadioButton",
}

INPUT_WIDGETS = {
    "EditText",
    "AutoCompleteTextView",
    "MultiAutoCompleteTextView",
    "TextInputEditText",
}

IMAGE_WIDGETS = {
    "ImageView",
    "ImageButton",
    "ShapeableImageView",
}

KNOWN_ACCESSIBLE_CLASS_PREFIXES = (
    "android.",
    "androidx.",
    "com.google.android.material.",
)

TEXT_WIDGETS = {
    "TextView",
    "Button",
    "EditText",
    "AutoCompleteTextView",
    "MultiAutoCompleteTextView",
    "TextInputEditText",
    "CheckBox",
    "RadioButton",
    "Switch",
    "SwitchCompat",
    "ToggleButton",
    "MaterialButton",
    "MaterialCheckBox",
    "MaterialRadioButton",
    "MaterialSwitch",
}

SEMANTIC_INTERACTIVE_WIDGETS = INTERACTIVE_WIDGETS | INPUT_WIDGETS
SEMANTIC_INTERACTIVE_WIDGETS.update({
    "ListView",
    "GridView",
    "ExpandableListView",
    "RecyclerView",
})

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

WEAK_INPUT_NAMES = {
    "input",
    "value",
    "number",
    "text",
    "field",
    "enter",
    "输入",
    "数值",
    "数字",
    "字段",
}

DIMENSION_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(dp|dip|sp|px)\s*$", re.I)
STRING_REF_RE = re.compile(r"^@(?:\+)?string/([A-Za-z0-9_.]+)$")
COLOR_REF_RE = re.compile(r"^@(?:\+)?color/([A-Za-z0-9_.]+)$")
DIMEN_REF_RE = re.compile(r"^@(?:\+)?dimen/([A-Za-z0-9_.]+)$")
ID_REF_RE = re.compile(r"^@(?:\+)?id/([A-Za-z0-9_.]+)$")
HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
ANDROID_STYLE_ATTRIBUTES = {
    "background",
    "clickable",
    "contentDescription",
    "editable",
    "focusable",
    "hint",
    "importantForAccessibility",
    "importantForAutofill",
    "inputType",
    "labelFor",
    "layout_height",
    "layout_width",
    "minHeight",
    "minWidth",
    "padding",
    "paddingBottom",
    "paddingEnd",
    "paddingLeft",
    "paddingRight",
    "paddingStart",
    "paddingTop",
    "src",
    "text",
    "textColor",
    "visibility",
}

EMAIL_TERMS = {"email", "mail", "e-mail", "邮箱", "邮件"}
PASSWORD_TERMS = {"password", "passwd", "pwd", "密码"}
PASSWORD_AUXILIARY_TERMS = {
    "delimiter",
    "generator",
    "hint",
    "label",
    "length",
    "prefix",
    "separator",
    "strength",
    "suffix",
    "toggle",
    "pwgen",
}
PHONE_TERMS = {"phone", "tel", "mobile", "手机号", "电话", "手机"}
PERSONAL_NAME_TERMS = {
    "username",
    "user_name",
    "user name",
    "first_name",
    "first name",
    "last_name",
    "last name",
    "full_name",
    "full name",
    "person name",
    "姓名",
    "用户名",
    "名字",
}
NUMBER_TERMS = {"number", "amount", "count", "age", "price", "数量", "金额", "年龄", "价格"}
SPECIFIC_NUMBER_TERMS = NUMBER_TERMS - {"number"}
STATEFUL_CONTROL_TAGS = {
    "CheckBox",
    "MaterialCheckBox",
    "MaterialRadioButton",
    "MaterialSwitch",
    "RadioButton",
    "RatingBar",
    "SeekBar",
    "Spinner",
    "Switch",
    "SwitchCompat",
    "ToggleButton",
}
MEANINGFUL_IMAGE_TERMS = {
    "avatar",
    "barcode",
    "brand",
    "chart",
    "cover",
    "graph",
    "logo",
    "map",
    "photo",
    "profile",
    "qr",
    "thumbnail",
}
DECORATIVE_IMAGE_TERMS = {
    "background",
    "bg",
    "decoration",
    "decorative",
    "divider",
    "shadow",
    "spacer",
}

TEXT_INPUT_LAYOUT_TAGS = {"TextInputLayout"}
CUSTOM_INTERACTIVE_SUFFIXES = {
    "Button",
    "CheckBox",
    "FloatingActionButton",
    "ImageButton",
    "RadioButton",
    "RatingBar",
    "SeekBar",
    "Spinner",
    "Switch",
    "ToggleButton",
}


def load_rule_config():
    try:
        data = json.loads(RULE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


RULE_CONFIG = load_rule_config()
PURPOSE_CONFIG = RULE_CONFIG.get("field_purpose_terms", {})
EMAIL_TERMS = set(PURPOSE_CONFIG.get("email", EMAIL_TERMS))
PASSWORD_TERMS = set(PURPOSE_CONFIG.get("password", PASSWORD_TERMS))
PHONE_TERMS = set(PURPOSE_CONFIG.get("phone", PHONE_TERMS))
PERSONAL_NAME_TERMS = set(PURPOSE_CONFIG.get("personal_name", PERSONAL_NAME_TERMS))
NUMBER_TERMS = set(PURPOSE_CONFIG.get("number", NUMBER_TERMS))

COMPONENT_ALIASES = RULE_CONFIG.get("component_aliases", {})
INTERACTIVE_WIDGETS.update(COMPONENT_ALIASES.get("interactive", []))
INPUT_WIDGETS.update(COMPONENT_ALIASES.get("input", []))
IMAGE_WIDGETS.update(COMPONENT_ALIASES.get("image", []))
TEXT_WIDGETS.update(COMPONENT_ALIASES.get("text", []))
TEXT_INPUT_LAYOUT_TAGS.update(COMPONENT_ALIASES.get("text_input_layout", []))
CUSTOM_INTERACTIVE_SUFFIXES.update(RULE_CONFIG.get("custom_interactive_suffixes", []))
SEMANTIC_INTERACTIVE_WIDGETS.update(INTERACTIVE_WIDGETS | INPUT_WIDGETS)

ADVISORIES = RULE_CONFIG.get("advisories", {})
EMIT_HARDCODED_TEXT = bool(ADVISORIES.get("hardcoded_text", False))
EMIT_MISSING_AUTOFILL = bool(ADVISORIES.get("missing_autofill", False))


def strip_ns(name):
    return name.rsplit("}", 1)[-1].rsplit(".", 1)[-1]


def attr(element, name, namespace=ANDROID_NS):
    qualified = f"{{{namespace}}}{name}"
    if qualified in element.attrib:
        return element.attrib[qualified]
    return element.attrib.get(name)


def all_attrs(element):
    return {strip_ns(key): value for key, value in element.attrib.items()}


def truthy(value):
    return str(value).lower() == "true"


def is_empty_value(value):
    if value is None:
        return True
    normalized = str(value).strip()
    return normalized in {"", "@null", "@empty"} or normalized.lower() == "null"


def parse_id(value):
    if not value:
        return None
    match = ID_REF_RE.match(value.strip())
    return match.group(1) if match else None


def parse_string_name(value):
    if not value:
        return None
    match = STRING_REF_RE.match(value.strip())
    return match.group(1) if match else None


def parse_color_name(value):
    if not value:
        return None
    match = COLOR_REF_RE.match(value.strip())
    return match.group(1) if match else None


def parse_dimen_name(value):
    if not value:
        return None
    match = DIMEN_REF_RE.match(value.strip())
    return match.group(1) if match else None


def resource_roots(paths):
    roots = []
    for path in paths:
        path = path.resolve()
        if path.is_dir():
            roots.append(path)
            roots.extend(parent for parent in path.parents if parent.name == "res")
        else:
            roots.extend(parent for parent in path.parents if parent.name == "res")
    return list(dict.fromkeys(roots))


def values_xml_files(paths):
    files = []
    for root in resource_roots(paths):
        files.extend(
            item
            for item in root.rglob("*.xml")
            if item.parent.name.startswith("values")
        )
        if root.name.startswith("values"):
            files.extend(root.glob("*.xml"))
    files = list(dict.fromkeys(files))
    return sorted(
        files,
        key=lambda item: (
            0 if item.parent.name == "values" else 1,
            item.parent.name,
            item.name,
        ),
    )


def load_string_resources(paths):
    resources = {}
    for values_file in values_xml_files(paths):
        try:
            tree = ET.parse(values_file)
        except ET.ParseError:
            continue
        for item in tree.getroot():
            is_string = strip_ns(item.tag) == "string" or (
                strip_ns(item.tag) == "item" and item.attrib.get("type") == "string"
            )
            if not is_string:
                continue
            name = item.attrib.get("name")
            if name and name not in resources:
                resources[name] = "".join(item.itertext()).strip()
    return resources


def load_color_resources(paths):
    resources = {}
    for values_file in values_xml_files(paths):
        try:
            tree = ET.parse(values_file)
        except ET.ParseError:
            continue
        for item in tree.getroot():
            is_color = strip_ns(item.tag) == "color" or (
                strip_ns(item.tag) == "item" and item.attrib.get("type") == "color"
            )
            if not is_color:
                continue
            name = item.attrib.get("name")
            value = "".join(item.itertext()).strip()
            if name and value and name not in resources:
                resources[name] = value
    return resources


def load_dimension_resources(paths):
    resources = {}
    for values_file in values_xml_files(paths):
        try:
            tree = ET.parse(values_file)
        except ET.ParseError:
            continue
        for item in tree.getroot():
            is_dimen = strip_ns(item.tag) == "dimen" or (
                strip_ns(item.tag) == "item" and item.attrib.get("type") == "dimen"
            )
            if not is_dimen:
                continue
            name = item.attrib.get("name")
            value = "".join(item.itertext()).strip()
            if name and value and name not in resources:
                resources[name] = value
    return resources


def qualify_style_attribute(name):
    if name.startswith("android:"):
        return f"{{{ANDROID_NS}}}{name.split(':', 1)[1]}"
    if name.startswith("app:"):
        return f"{{{APP_NS}}}{name.split(':', 1)[1]}"
    if name in ANDROID_STYLE_ATTRIBUTES:
        return f"{{{ANDROID_NS}}}{name}"
    return name


def load_style_resources(paths):
    raw_styles = {}
    for values_file in values_xml_files(paths):
        try:
            tree = ET.parse(values_file)
        except ET.ParseError:
            continue
        for style in tree.getroot().findall("style"):
            name = style.attrib.get("name")
            if not name or name in raw_styles:
                continue
            parent = style.attrib.get("parent", "")
            if parent.startswith("@style/"):
                parent = parent.rsplit("/", 1)[-1]
            items = {}
            for item in style.findall("item"):
                item_name = item.attrib.get("name")
                if item_name:
                    items[qualify_style_attribute(item_name)] = "".join(item.itertext()).strip()
            raw_styles[name] = {"parent": parent, "items": items}

    resolved = {}

    def resolve_style(name, active):
        if name in resolved:
            return resolved[name]
        if name in active or name not in raw_styles:
            return {}
        active.add(name)
        style = raw_styles[name]
        values = {}
        parent = style["parent"]
        if not parent and "." in name:
            implicit_parent = name.rsplit(".", 1)[0]
            if implicit_parent in raw_styles:
                parent = implicit_parent
        if parent:
            values.update(resolve_style(parent, active))
        values.update(style["items"])
        active.remove(name)
        resolved[name] = values
        return values

    for style_name in raw_styles:
        resolve_style(style_name, set())
    return resolved


def apply_explicit_styles(root, styles):
    for element in root.iter():
        style_ref = element.attrib.get("style", "")
        if not style_ref.startswith("@style/"):
            continue
        style_name = style_ref.rsplit("/", 1)[-1]
        for key, value in styles.get(style_name, {}).items():
            element.attrib.setdefault(key, value)


def resolve_string(value, resources):
    if not value:
        return ""
    value = value.strip()
    name = parse_string_name(value)
    if name:
        seen = set()
        resolved = resources.get(name, name)
        while parse_string_name(resolved) and resolved not in seen:
            seen.add(resolved)
            resolved_name = parse_string_name(resolved)
            resolved = resources.get(resolved_name, resolved_name)
        return resolved
    if value.startswith("@android:string/"):
        return value.rsplit("/", 1)[-1]
    return value


def is_resource_or_expression(value):
    if value is None:
        return True
    value = value.strip()
    return (
        not value
        or value.startswith("@")
        or value.startswith("?")
        or value.startswith("${")
        or value.startswith("@{")
        or value.startswith("#")
    )


def is_likely_user_visible_text(value):
    if value is None:
        return False
    value = value.strip()
    if not value or is_resource_or_expression(value):
        return False
    if value in {"true", "false"}:
        return False
    return any(char.isalpha() or "\u4e00" <= char <= "\u9fff" for char in value)


def parse_dp(value):
    if not value:
        return None
    value = value.strip()
    if value in {"wrap_content", "match_parent", "fill_parent", "0dp"}:
        return None
    match = DIMENSION_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"dp", "dip"}:
        return number
    return None


def resolve_dimension(value, dimensions):
    if value is None:
        return None, "missing"
    raw = value.strip()
    parsed = parse_dp(raw)
    if parsed is not None:
        return parsed, "resolved"
    name = parse_dimen_name(raw)
    seen = set()
    while name and name not in seen:
        seen.add(name)
        resolved = dimensions.get(name)
        if resolved is None:
            return None, "unresolved_resource"
        parsed = parse_dp(resolved)
        if parsed is not None:
            return parsed, "resolved"
        name = parse_dimen_name(resolved)
        if not name:
            return None, "unresolved_resource"
    if raw in {"wrap_content", "match_parent", "fill_parent", "0dp"}:
        return None, "dynamic"
    if raw.startswith("?") or raw.startswith("@style/"):
        return None, "dynamic"
    if raw.startswith("@dimen/"):
        return None, "unresolved_resource"
    return None, "unknown"


def resolve_color(value, colors):
    if not value:
        return None
    value = value.strip()
    color_name = parse_color_name(value)
    seen = set()
    while color_name and color_name not in seen:
        seen.add(color_name)
        value = colors.get(color_name, "")
        color_name = parse_color_name(value)
    if not value or not HEX_COLOR_RE.match(value):
        return None
    raw = value.lstrip("#")
    if len(raw) in {3, 4}:
        raw = "".join(char * 2 for char in raw)
    if len(raw) == 8:
        raw = raw[2:]
    if len(raw) != 6:
        return None
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def relative_luminance(rgb):
    channels = []
    for value in rgb:
        value = value / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground, background):
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def tag_has_suffix(tag, suffixes):
    return any(tag == suffix or tag.endswith(suffix) for suffix in suffixes)


def normalize_view_type(tag_name):
    tag = strip_ns(tag_name)
    if tag_has_suffix(tag, {"ImageButton"}):
        return "ImageButton"
    if tag_has_suffix(tag, {"AutoCompleteTextView"}):
        return "SelectionControl"
    if tag_has_suffix(tag, {"EditText"}):
        return "EditText"
    if tag_has_suffix(tag, {"Spinner"}):
        return "SelectionControl"
    if tag_has_suffix(tag, {"Button"}):
        return "Button"
    if tag_has_suffix(tag, {"ImageView"}):
        return "ImageView"
    if tag_has_suffix(tag, {"RadioGroup"}):
        return "SelectionControl"
    if tag_has_suffix(tag, {"CheckBox", "Switch", "SeekBar", "RatingBar"}):
        return "SelectionControl"
    if tag_has_suffix(tag, {"TextView"}):
        return "TextView"
    return tag


def is_interactive(element):
    tag = strip_ns(element.tag)
    if tag in INTERACTIVE_WIDGETS or tag_has_suffix(tag, CUSTOM_INTERACTIVE_SUFFIXES):
        return True
    if normalize_view_type(element.tag) == "ImageView" and truthy(attr(element, "focusable")):
        return True
    return truthy(attr(element, "clickable")) or attr(element, "onClick") is not None


def is_input(element):
    return normalize_view_type(element.tag) in {"EditText", "SelectionControl"} and (
        tag_has_suffix(strip_ns(element.tag), {"EditText", "AutoCompleteTextView"})
    )


def is_editable_input(element):
    if not is_input(element):
        return False
    tag = strip_ns(element.tag)
    is_auto_complete = tag_has_suffix(tag, {"AutoCompleteTextView"})
    if (attr(element, "editable") or "").lower() == "false":
        return False
    if (attr(element, "inputType") or "").lower() == "none" and not is_auto_complete:
        return False
    if (
        (attr(element, "focusable") or "").lower() == "false"
        and not truthy(attr(element, "clickable"))
    ):
        return False
    return True


def is_image_widget(element):
    return normalize_view_type(element.tag) in {"ImageView", "ImageButton"}


def is_text_widget(element):
    tag = strip_ns(element.tag)
    return tag in TEXT_WIDGETS or tag_has_suffix(
        tag,
        {"TextView", "Button", "EditText", "CheckBox", "RadioButton", "Switch"},
    )


def is_custom_view(element):
    tag = element.tag
    if tag.startswith("{") or "." not in tag:
        return False
    return not tag.startswith(KNOWN_ACCESSIBLE_CLASS_PREFIXES)


def is_nonsemantic_clickable(element):
    tag = strip_ns(element.tag)
    semantic_suffixes = INTERACTIVE_WIDGETS | {
        "Button",
        "CheckBox",
        "ImageButton",
        "RadioButton",
        "RatingBar",
        "SeekBar",
        "Spinner",
        "Switch",
        "ToggleButton",
    }
    return (
        is_interactive(element)
        and not attr(element, "accessibilityClassName")
        and tag not in SEMANTIC_INTERACTIVE_WIDGETS
        and not tag_has_suffix(tag, semantic_suffixes)
    )


def text_input_layout_hint(element, parent_map):
    parent = parent_map.get(element)
    while parent is not None:
        parent_tag = strip_ns(parent.tag)
        if tag_has_suffix(parent_tag, TEXT_INPUT_LAYOUT_TAGS):
            if (attr(parent, "hintEnabled", APP_NS) or "").lower() != "false":
                hint = attr(parent, "hint")
                if not is_empty_value(hint):
                    return hint
        parent = parent_map.get(parent)
    return None


def ignores_content_description(element):
    ignored = attr(element, "ignore", TOOLS_NS) or ""
    return "contentdescription" in {
        item.strip().lower()
        for item in ignored.split(",")
    }


def explicitly_decorative_image(element):
    content_description = attr(element, "contentDescription")
    important = attr(element, "importantForAccessibility")
    return (
        important in {"no", "noHideDescendants"}
        or content_description is not None and is_empty_value(content_description)
        or ignores_content_description(element)
    )


def unresolved_style(element, styles):
    style_ref = element.attrib.get("style", "")
    return style_ref.startswith("@style/") and style_ref.rsplit("/", 1)[-1] not in styles


def has_padding(element):
    return any(
        attr(element, name) is not None
        for name in (
            "padding",
            "paddingStart",
            "paddingEnd",
            "paddingLeft",
            "paddingRight",
            "paddingTop",
            "paddingBottom",
        )
    )


def touch_target_assessment(element, dimensions):
    min_width, min_width_status = resolve_dimension(attr(element, "minWidth"), dimensions)
    min_height, min_height_status = resolve_dimension(attr(element, "minHeight"), dimensions)
    if (min_width is not None and min_width >= 48) or (
        min_height is not None and min_height >= 48
    ):
        return None

    width, width_status = resolve_dimension(attr(element, "layout_width"), dimensions)
    height, height_status = resolve_dimension(attr(element, "layout_height"), dimensions)
    statuses = {width_status, height_status, min_width_status, min_height_status}
    if "unresolved_resource" in statuses:
        return {
            "severity": "info",
            "code": "ANDROID_XML_TOUCH_TARGET_SIZE_REQUIRES_REVIEW",
            "message": (
                "触控目标尺寸引用了无法解析的 @dimen 资源，静态检测无法确认实际大小。"
            ),
            "confidence": 0.35,
        }
    if width is None or height is None:
        return None
    if width >= 48 or height >= 48:
        return None
    return {
        "severity": "warning",
        "code": "ANDROID_XML_TOUCH_TARGET_TOO_SMALL",
        "message": (
            "交互控件的 XML 宽度和高度均可静态解析且小于 48dp。"
            + ("控件还设置了 padding，实际触控区域建议人工复核。" if has_padding(element) else "建议人工复核实际触控区域。")
        ),
        "confidence": 0.65 if has_padding(element) else 0.75,
    }


def descendant_accessible_text(element, resources):
    values = []
    for child in element.iter():
        if child is element:
            continue
        if is_text_widget(child):
            values.extend([attr(child, "text"), attr(child, "contentDescription")])
    for value in values:
        resolved = resolve_string(value, resources)
        if not is_empty_value(resolved):
            return resolved.strip()
    return ""


def accessible_name_candidates(element, resources, id_to_label, parent_map):
    tag = strip_ns(element.tag)
    values = [
        attr(element, "text"),
        attr(element, "contentDescription"),
    ]
    if is_input(element):
        values.append(attr(element, "hint"))
        values.append(text_input_layout_hint(element, parent_map))
    element_id = parse_id(attr(element, "id"))
    if element_id and element_id in id_to_label:
        values.append(id_to_label[element_id])
    if is_nonsemantic_clickable(element):
        values.append(descendant_accessible_text(element, resources))
    return values


def has_accessible_name(element, resources, id_to_label, parent_map):
    candidates = accessible_name_candidates(element, resources, id_to_label, parent_map)
    return any(not is_empty_value(resolve_string(value, resources)) for value in candidates)


def get_accessible_name(element, resources, id_to_label, parent_map):
    candidates = accessible_name_candidates(element, resources, id_to_label, parent_map)
    for candidate in candidates:
        resolved = resolve_string(candidate, resources)
        if not is_empty_value(resolved):
            return resolved.strip()
    return ""


def get_stable_input_label(element, resources, id_to_label, parent_map):
    """Return a programmatic or container label before considering a hint."""
    element_id = parse_id(attr(element, "id"))
    candidates = []
    if element_id and element_id in id_to_label:
        candidates.append(id_to_label[element_id])
    parent_hint = text_input_layout_hint(element, parent_map)
    if parent_hint:
        candidates.append(parent_hint)
    for candidate in candidates:
        resolved = resolve_string(candidate, resources)
        if not is_empty_value(resolved):
            return resolved.strip()
    return ""


def element_identity_text(element, resources, id_to_label, parent_map):
    values = [
        strip_ns(element.tag),
        attr(element, "id") or "",
        attr(element, "hint") or "",
        attr(element, "text") or "",
        attr(element, "contentDescription") or "",
        text_input_layout_hint(element, parent_map) or "",
    ]
    element_id = parse_id(attr(element, "id"))
    if element_id and element_id in id_to_label:
        values.append(id_to_label[element_id])
    return " ".join(resolve_string(value, resources) for value in values if value)


def image_identity_text(element):
    values = [
        attr(element, "id") or "",
        attr(element, "src") or "",
        attr(element, "srcCompat", APP_NS) or "",
        attr(element, "background") or "",
    ]
    return " ".join(values)


def image_identity_tokens(element):
    identity = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1 \2",
        image_identity_text(element),
    ).lower()
    return set(re.findall(r"[a-z0-9]+", identity))


def looks_like_meaningful_image(element):
    return bool(image_identity_tokens(element) & MEANINGFUL_IMAGE_TERMS)


def looks_like_decorative_image(element):
    return bool(image_identity_tokens(element) & DECORATIVE_IMAGE_TERMS)


def has_any_term(text, terms):
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    normalized = re.sub(r"[_./:@+\-]+", " ", normalized.lower())
    normalized = re.sub(r"\s+", " ", normalized)
    for term in terms:
        lowered = term.lower()
        if any("\u4e00" <= char <= "\u9fff" for char in lowered):
            if lowered in normalized:
                return True
            continue
        term_tokens = re.findall(r"[a-z0-9]+", lowered)
        if not term_tokens:
            continue
        pattern = r"(?<![a-z0-9])" + r"[\s_-]+".join(map(re.escape, term_tokens)) + r"(?![a-z0-9])"
        if re.search(pattern, normalized):
            return True
    return False


def is_weak_input_name(name):
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    if not normalized:
        return False
    if normalized in WEAK_INPUT_NAMES:
        return True
    if re.fullmatch(r"[\d\s.,:%+-]+", normalized):
        return True
    return False


def is_expanded_profile(profile):
    return profile in {"expanded_v2", "expanded_v3"}


def is_expanded_v3(profile):
    return profile == "expanded_v3"


def stable_input_purpose_evidence(
    element,
    resources,
    id_to_label,
    parent_map,
    purpose_terms=None,
    include_input_type=True,
):
    """Return stable XML evidence that identifies an input's purpose.

    The current hint/contentDescription is intentionally excluded because this
    helper is used when that accessible name is already known to be weak.
    """
    values = [attr(element, "id") or ""]
    if include_input_type:
        values.append(attr(element, "inputType") or "")
    element_id = parse_id(attr(element, "id"))
    if element_id and element_id in id_to_label:
        values.append(id_to_label[element_id])
    parent_hint = text_input_layout_hint(element, parent_map)
    if parent_hint:
        values.append(parent_hint)
    evidence = " ".join(
        resolve_string(value, resources)
        for value in values
        if value
    )
    if purpose_terms is None:
        purpose_terms = (
            EMAIL_TERMS
            | PASSWORD_TERMS
            | PHONE_TERMS
            | PERSONAL_NAME_TERMS
        )
    return evidence if has_any_term(evidence, purpose_terms) else ""


def high_confidence_standard_control(element, styles):
    return (
        not is_custom_view(element)
        and not unresolved_style(element, styles)
        and normalize_view_type(element.tag)
        in {"Button", "ImageButton", "EditText", "SelectionControl"}
        and (attr(element, "enabled") or "").lower() != "false"
        and (attr(element, "clickable") or "").lower() != "false"
    )


def high_confidence_input_semantics(element, styles, purpose_evidence):
    return (
        bool(purpose_evidence)
        and normalize_view_type(element.tag) == "EditText"
        and not is_custom_view(element)
        and not unresolved_style(element, styles)
    )


def high_confidence_password_evidence(
    element,
    resources,
    id_to_label,
    parent_map,
):
    """Identify a password value field, excluding password-related controls.

    IDs such as password_length and password_separator describe generator
    parameters, not secret values. Treating every occurrence of "password" as
    a password input creates unsafe inputType edits.
    """
    evidence = stable_input_purpose_evidence(
        element,
        resources,
        id_to_label,
        parent_map,
        purpose_terms=PASSWORD_TERMS,
        include_input_type=False,
    )
    if evidence and has_any_term(evidence, PASSWORD_AUXILIARY_TERMS):
        return ""
    return evidence


def element_path(stack):
    parts = []
    for item in stack:
        parent_children = [child for child in item["siblings"] if strip_ns(child.tag) == strip_ns(item["element"].tag)]
        index = parent_children.index(item["element"]) + 1 if item["element"] in parent_children else 1
        parts.append(f"{strip_ns(item['element'].tag)}[{index}]")
    return "/" + "/".join(parts)


def build_parent_map(root):
    return {child: parent for parent in root.iter() for child in parent}


def build_id_map(root):
    id_map = {}
    for element in root.iter():
        element_id = parse_id(attr(element, "id"))
        if element_id:
            id_map[element_id] = element
    return id_map


def build_stack(element, parent_map):
    reversed_items = []
    current = element
    while current is not None:
        parent = parent_map.get(current)
        siblings = list(parent) if parent is not None else [current]
        reversed_items.append({"element": current, "siblings": siblings})
        current = parent
    return list(reversed(reversed_items))


def ancestor_has_no_hide_descendants(element, parent_map):
    current = parent_map.get(element)
    while current is not None:
        if attr(current, "importantForAccessibility") == "noHideDescendants":
            return True
        current = parent_map.get(current)
    return False


def nearest_background_color(element, parent_map, colors):
    current = element
    while current is not None:
        color = resolve_color(attr(current, "background"), colors)
        if color:
            return color
        current = parent_map.get(current)
    return None


def is_visible_in_layout(element, parent_map):
    current = element
    while current is not None:
        if attr(current, "visibility") in {"gone", "invisible"}:
            return False
        current = parent_map.get(current)
    return True


def looks_like_layout_xml(path):
    if path.parent.name.startswith("layout"):
        return True
    if path.name in {"strings.xml", "styles.xml", "colors.xml", "dimens.xml", "ids.xml", "attrs.xml"}:
        return False
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return True
    return strip_ns(root.tag) != "resources"


def make_issue(
    path,
    root,
    parent_map,
    element,
    code,
    severity,
    message,
    related_docs,
    repair_query,
    repairability="xml_safe",
    confidence=None,
    requires_review=None,
    fix_hint=None,
):
    selector = element_path(build_stack(element, parent_map))
    if confidence is None:
        confidence = {"error": 0.9, "warning": 0.65, "info": 0.35}.get(severity, 0.9)
    if requires_review is None:
        requires_review = severity != "error" or repairability != "xml_safe"
    if fix_hint is None:
        fix_hint = (
            "建议人工复核页面上下文、运行时语义和实际交互后再决定是否修改。"
            if severity in {"warning", "info"}
            else message
        )
    return {
        "id": f"{code}:{Path(path).name}:{selector}",
        "type": severity,
        "severity": severity,
        "confidence": confidence,
        "requires_review": requires_review,
        "component": normalize_view_type(element.tag),
        "code": code,
        "repairability": repairability,
        "message": message,
        "fix_hint": fix_hint,
        "file": str(path),
        "element": strip_ns(element.tag),
        "selector": selector,
        "attributes": all_attrs(element),
        "related_docs": related_docs,
        "repair_query": repair_query,
    }


def build_label_map(root, resources):
    label_map = {}
    for element in root.iter():
        label_for = parse_id(attr(element, "labelFor"))
        if not label_for:
            continue
        label_text = resolve_string(attr(element, "text") or attr(element, "contentDescription"), resources)
        if label_text:
            label_map[label_for] = label_text
    return label_map


def visible_label_candidates(element, parent_map, resources):
    parent = parent_map.get(element)
    if parent is None:
        return []
    candidates = []
    for sibling in list(parent):
        if sibling is element or not tag_has_suffix(strip_ns(sibling.tag), {"TextView"}):
            continue
        if attr(sibling, "visibility") in {"gone", "invisible"}:
            continue
        text = resolve_string(
            attr(sibling, "text") or attr(sibling, "contentDescription"),
            resources,
        )
        if text and not attr(sibling, "labelFor"):
            candidates.append(sibling)
    return candidates


def missing_name_repairability(
    element,
    parent_map,
    resources,
    id_to_label,
    detector_profile=DEFAULT_DETECTOR_PROFILE,
):
    if not tag_has_suffix(strip_ns(element.tag), STATEFUL_CONTROL_TAGS):
        return "xml_safe"
    has_existing_id = bool(parse_id(attr(element, "id")))
    parent = parent_map.get(element)
    unnamed_peer_count = sum(
        tag_has_suffix(strip_ns(child.tag), STATEFUL_CONTROL_TAGS)
        and not has_accessible_name(child, resources, id_to_label, parent_map)
        for child in list(parent) if parent is not None
    )
    if (
        len(visible_label_candidates(element, parent_map, resources)) == 1
        and unnamed_peer_count == 1
        and (not is_expanded_v3(detector_profile) or has_existing_id)
    ):
        return "xml_safe"
    return "requires_structure_or_code"


def missing_name_issue_code(element, detector_profile):
    if not is_expanded_v3(detector_profile):
        return "ANDROID_XML_MISSING_ACCESSIBLE_NAME"
    tag = strip_ns(element.tag)
    normalized = normalize_view_type(element.tag)
    if normalized == "ImageButton":
        return "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME"
    if tag_has_suffix(tag, STATEFUL_CONTROL_TAGS) or normalized == "SelectionControl":
        return "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL"
    if normalized == "Button":
        return "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME"
    if normalized == "ImageView":
        return "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME"
    if is_nonsemantic_clickable(element):
        return "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME"
    return "ANDROID_XML_MISSING_ACCESSIBLE_NAME"


def is_known_label_target(element):
    if normalize_view_type(element.tag) in {"EditText", "SelectionControl"}:
        return True
    return tag_has_suffix(
        strip_ns(element.tag),
        {"CheckBox", "RadioGroup", "RatingBar", "SeekBar", "Spinner", "Switch"},
    )


def check_tree(
    path,
    root,
    resources,
    colors,
    dimensions,
    styles,
    detector_profile=DEFAULT_DETECTOR_PROFILE,
):
    issues = []
    parent_map = build_parent_map(root)
    id_map = build_id_map(root)
    id_to_label = build_label_map(root, resources)
    names_by_value = defaultdict(list)

    for element in root.iter():
        tag = strip_ns(element.tag)
        if tag in {"layout", "data", "variable", "import", "requestFocus"}:
            continue
        if not is_visible_in_layout(element, parent_map):
            continue
        important = attr(element, "importantForAccessibility")
        hidden_from_a11y = important in {"no", "noHideDescendants"} or ancestor_has_no_hide_descendants(element, parent_map)

        if attr(element, "labelFor"):
            target_id = parse_id(attr(element, "labelFor"))
            target = id_map.get(target_id)
            if target is None:
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_LABELFOR_TARGET_MISSING",
                    "error",
                    "TextView 的 android:labelFor 指向不存在的 id。请修正目标 id 或删除无效关联。",
                    ["android.rule.forms-errors", "android.fixmap.textfield-error-not-announced"],
                    "Android XML labelFor target missing input label association",
                ))
            elif not is_known_label_target(target) and not is_interactive(target):
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_LABELFOR_TARGET_NOT_INPUT",
                    "warning",
                    "android:labelFor 指向的不是输入控件或语义交互控件。请确认目标是否需要程序化标签。",
                    ["android.rule.forms-errors"],
                    "Android XML labelFor target not labelable input interactive control",
                    "manual_review",
                    confidence=0.45,
                    requires_review=True,
                    fix_hint="建议人工复核目标自定义控件是否暴露了可标注的输入或选择语义。",
                ))

        if (
            is_interactive(element)
            and important in {"no", "noHideDescendants"}
            and not is_image_widget(element)
        ):
            v3_hidden_rule = is_expanded_v3(detector_profile)
            direct_hidden_is_safe = (
                v3_hidden_rule
                and high_confidence_standard_control(element, styles)
            )
            hidden_message = (
                "交互控件被 importantForAccessibility 隐藏，辅助技术可能无法发现或操作它。"
            )
            issues.append(make_issue(
                path,
                root,
                parent_map,
                element,
                "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY",
                "error",
                hidden_message,
                ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                "Android XML interactive control hidden importantForAccessibility no noHideDescendants",
                (
                    "xml_safe"
                    if direct_hidden_is_safe or not v3_hidden_rule
                    else "requires_structure_or_code"
                ),
                confidence=(
                    0.95
                    if direct_hidden_is_safe
                    else 0.8
                    if v3_hidden_rule
                    else 0.9
                ),
                requires_review=v3_hidden_rule and not direct_hidden_is_safe,
                fix_hint=(
                    "移除标准交互控件显式设置的 android:importantForAccessibility，恢复默认可访问性。"
                    if direct_hidden_is_safe
                    else (
                        "建议人工复核控件为何被隐藏，并结合运行时语义决定是否恢复可访问性。"
                        if v3_hidden_rule
                        else hidden_message
                    )
                ),
            ))

        if (
            is_interactive(element)
            and ancestor_has_no_hide_descendants(element, parent_map)
            and not is_image_widget(element)
        ):
            issues.append(make_issue(
                path,
                root,
                parent_map,
                element,
                "ANDROID_XML_INTERACTIVE_HIDDEN_BY_PARENT",
                "error",
                "交互控件被父容器 importantForAccessibility=\"noHideDescendants\" 隐藏。",
                ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                "Android XML interactive child hidden by parent noHideDescendants",
            ))

        if is_interactive(element) and not hidden_from_a11y:
            suppress_image_name_error = (
                is_image_widget(element) and explicitly_decorative_image(element)
            )
            style_unknown = unresolved_style(element, styles)
            unknown_custom = (
                is_custom_view(element)
                and normalize_view_type(element.tag) == strip_ns(element.tag)
            )
            if (
                not suppress_image_name_error
                and not has_accessible_name(element, resources, id_to_label, parent_map)
            ):
                repairability = missing_name_repairability(
                    element,
                    parent_map,
                    resources,
                    id_to_label,
                    detector_profile,
                )
                severity = "info" if style_unknown or unknown_custom else "error"
                if style_unknown or unknown_custom:
                    repairability = "manual_review"
                if repairability == "xml_safe":
                    missing_name_message = (
                        "交互控件缺少可访问名称。请使用 text、contentDescription、"
                        "hint 或把现有可见 TextView 通过 labelFor 与控件关联。"
                    )
                else:
                    missing_name_message = (
                        "状态控件缺少可访问名称，且同级没有唯一、无歧义的可见文本标签"
                        "可通过 labelFor 关联。安全修复需要补充完整标签结构或在运行时代码中"
                        "提供保留当前值/状态的无障碍语义。"
                    )
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    missing_name_issue_code(element, detector_profile),
                    severity,
                    missing_name_message,
                    ["android.rule.content-labels", "android.fixmap.content-labeling"],
                    "Android XML content labeling missing label contentDescription",
                    repairability,
                    confidence=0.35 if style_unknown else (0.45 if unknown_custom else 0.95),
                    requires_review=style_unknown or unknown_custom or repairability != "xml_safe",
                    fix_hint=(
                        "建议人工复核未解析 style 是否已经提供可访问名称。"
                        if style_unknown
                        else (
                            "建议人工复核自定义控件是否在运行时代码中提供了可访问名称。"
                            if unknown_custom
                            else "为交互控件提供准确的 text、contentDescription、hint 或 labelFor 标签。"
                        )
                    ),
                ))

            if is_nonsemantic_clickable(element):
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_NON_SEMANTIC_CLICKABLE",
                    "warning",
                    "非按钮/非输入控件承担点击操作。请优先使用 Button、CheckBox、Switch 等语义控件；若保留容器点击，请确保名称、触控目标和焦点顺序正确。",
                    ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                    "Android XML clickable LinearLayout TextView non semantic role accessible name",
                    "requires_structure_or_code",
                ))

            touch_assessment = touch_target_assessment(element, dimensions)
            if touch_assessment:
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    touch_assessment["code"],
                    touch_assessment["severity"],
                    touch_assessment["message"],
                    ["android.rule.touch-targets-contrast", "android.fixmap.touch-target-small"],
                    "Android XML touch target size below 48dp verify TouchDelegate",
                    "manual_review",
                    confidence=touch_assessment["confidence"],
                    requires_review=True,
                    fix_hint="建议人工复核实际渲染尺寸、padding 和 TouchDelegate 后再决定是否扩大触控区域。",
                ))

            name = get_accessible_name(element, resources, id_to_label, parent_map)
            if name:
                names_by_value[name.strip().lower()].append(element)

        if truthy(attr(element, "focusable")) and not is_interactive(element) and not is_input(element) and not has_accessible_name(element, resources, id_to_label, parent_map):
            issues.append(make_issue(
                path,
                root,
                parent_map,
                element,
                "ANDROID_XML_UNNAMED_FOCUSABLE_CONTAINER",
                "warning",
                "非交互容器设置了 focusable=\"true\"，但没有可访问名称。它可能造成无意义焦点停靠。",
                ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                "Android XML focusable container no accessible name duplicate focus",
            ))

        if attr(element, "focusable") == "false" and is_interactive(element):
            hidden = important in {"no", "noHideDescendants"} or ancestor_has_no_hide_descendants(element, parent_map)
            blocked_standard_control = (
                is_expanded_profile(detector_profile)
                and not hidden
                and high_confidence_standard_control(element, styles)
            )
            if blocked_standard_control:
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
                    "error",
                    "已启用的标准交互控件显式设置了 focusable=\"false\"，会阻止键盘或方向键焦点访问。",
                    ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                    "Android XML interactive control focusable false keyboard TalkBack",
                    "xml_safe",
                    confidence=0.9,
                    requires_review=False,
                    fix_hint="移除标准交互控件显式设置的 android:focusable=\"false\"，恢复组件默认焦点行为。",
                ))
            else:
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE",
                    "warning",
                    "交互控件设置了 focusable=\"false\"，可能阻止键盘、方向键或辅助技术访问。",
                    ["android.rule.focus-navigation", "android.fixmap.implementation-focus-order"],
                    "Android XML interactive control focusable false keyboard TalkBack",
                ))

        if is_editable_input(element) and not hidden_from_a11y:
            if not has_accessible_name(element, resources, id_to_label, parent_map):
                style_unknown = unresolved_style(element, styles)
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
                    "info" if style_unknown else "error",
                    (
                        "输入框引用的 style 无法解析，无法确认是否已提供 hint 或标签。"
                        if style_unknown
                        else "输入框缺少稳定标签或 hint。请添加 android:hint，或使用 TextView android:labelFor 关联标签。"
                    ),
                    ["android.rule.forms-errors", "android.fixmap.textfield-error-not-announced"],
                    "Android XML EditText missing label hint labelFor",
                    "manual_review" if style_unknown else "xml_safe",
                    confidence=0.35 if style_unknown else 0.95,
                    requires_review=style_unknown,
                    fix_hint=(
                        "建议人工复核未解析 style 和运行时主题是否提供了输入标签。"
                        if style_unknown
                        else "为输入框添加稳定 hint、祖先 TextInputLayout hint、labelFor 或 contentDescription。"
                    ),
                ))
            else:
                input_name = (
                    get_stable_input_label(
                        element, resources, id_to_label, parent_map
                    )
                    or get_accessible_name(
                        element, resources, id_to_label, parent_map
                    )
                )
                if is_weak_input_name(input_name):
                    purpose_evidence = stable_input_purpose_evidence(
                        element,
                        resources,
                        id_to_label,
                        parent_map,
                    )
                    weak_name_is_actionable = (
                        is_expanded_profile(detector_profile)
                        and bool(purpose_evidence)
                        and not is_custom_view(element)
                        and not unresolved_style(element, styles)
                    )
                    if weak_name_is_actionable:
                        issues.append(make_issue(
                            path,
                            root,
                            parent_map,
                            element,
                            "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
                            "error",
                            f"输入框的可访问名称 {input_name!r} 过于泛化或只是格式示例；XML 中存在可识别字段用途的稳定证据：{purpose_evidence!r}。",
                            ["android.rule.forms-errors", "android.fixcase.textfield-placeholder-label"],
                            "Android XML EditText weak generic numeric hint label purpose",
                            "xml_safe",
                            confidence=0.9,
                            requires_review=False,
                            fix_hint="使用 XML 中已有的字段用途证据，把弱 hint 或标签替换为说明输入目的的稳定文本。",
                        ))
                    else:
                        issues.append(make_issue(
                            path,
                            root,
                            parent_map,
                            element,
                            "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
                            "warning",
                            f"输入框的可访问名称过于泛化或只是格式示例：{input_name!r}。请使用能说明字段用途的标签或 hint。",
                            ["android.rule.forms-errors", "android.fixcase.textfield-placeholder-label"],
                            "Android XML EditText weak generic numeric hint label purpose",
                        ))

            identity = element_identity_text(element, resources, id_to_label, parent_map)
            input_type = (attr(element, "inputType") or "").lower()
            autofill = (attr(element, "autofillHints") or "").lower()
            autofill_disabled = (attr(element, "importantForAutofill") or "").lower() in {
                "no",
                "noexcludedescendants",
            }
            if has_any_term(identity, EMAIL_TERMS):
                if "email" not in input_type:
                    email_evidence = stable_input_purpose_evidence(
                        element,
                        resources,
                        id_to_label,
                        parent_map,
                        purpose_terms=EMAIL_TERMS,
                        include_input_type=False,
                    )
                    email_is_actionable = (
                        is_expanded_profile(detector_profile)
                        and high_confidence_input_semantics(
                            element,
                            styles,
                            email_evidence,
                        )
                    )
                    if email_is_actionable:
                        issues.append(make_issue(
                            path,
                            root,
                            parent_map,
                            element,
                            "ANDROID_XML_EMAIL_INPUTTYPE_MISSING",
                            "error",
                            f"XML 中存在明确邮箱字段证据 {email_evidence!r}，但输入框缺少 textEmailAddress 类型。",
                            ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
                            "Android XML email EditText missing inputType textEmailAddress",
                            "xml_safe",
                            confidence=0.9,
                            requires_review=False,
                            fix_hint="把 android:inputType 设置为 textEmailAddress，并保留已有的其他输入限制标志。",
                        ))
                    else:
                        issues.append(make_issue(
                            path,
                            root,
                            parent_map,
                            element,
                            "ANDROID_XML_EMAIL_INPUTTYPE_MISSING",
                            "warning",
                            "邮箱字段疑似缺少 android:inputType=\"textEmailAddress\"。",
                            ["android.rule.forms-errors"],
                            "Android XML email EditText missing inputType textEmailAddress",
                        ))
                if EMIT_MISSING_AUTOFILL and "email" not in autofill and not autofill_disabled:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_EMAIL_AUTOFILL_MISSING",
                        "warning",
                        "邮箱字段疑似缺少 android:autofillHints=\"emailAddress\"。",
                        ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
                        "Android XML email EditText missing autofillHints emailAddress WCAG 1.3.5",
                        "manual_review",
                    ))
            if has_any_term(identity, PASSWORD_TERMS):
                legacy_password = truthy(attr(element, "password"))
                if (
                    "password" not in input_type
                    and not (
                        is_expanded_profile(detector_profile)
                        and legacy_password
                    )
                ):
                    password_evidence = high_confidence_password_evidence(
                        element,
                        resources,
                        id_to_label,
                        parent_map,
                    )
                    password_is_actionable = (
                        is_expanded_profile(detector_profile)
                        and high_confidence_input_semantics(
                            element,
                            styles,
                            password_evidence,
                        )
                    )
                    if password_is_actionable:
                        issues.append(make_issue(
                            path,
                            root,
                            parent_map,
                            element,
                            "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
                            "error",
                            "XML 中存在明确密码字段证据，但输入框缺少 password 类型的 android:inputType。",
                            ["android.rule.forms-errors"],
                            "Android XML password EditText missing inputType textPassword",
                            "xml_safe",
                            confidence=0.9,
                            requires_review=False,
                            fix_hint="根据现有输入约束设置 textPassword、textVisiblePassword 或 numberPassword，保留其他 inputType 标志。",
                        ))
                    else:
                        issues.append(make_issue(
                            path,
                            root,
                            parent_map,
                            element,
                            "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
                            "warning",
                            "密码字段疑似缺少 password 类型 inputType，例如 textPassword、textVisiblePassword 或 numberPassword。",
                            ["android.rule.forms-errors"],
                            "Android XML password EditText missing inputType textPassword",
                        ))
                if EMIT_MISSING_AUTOFILL and "password" not in autofill and not autofill_disabled:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_PASSWORD_AUTOFILL_MISSING",
                        "warning",
                        "密码字段疑似缺少 android:autofillHints=\"password\"。",
                        ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
                        "Android XML password EditText missing autofillHints password WCAG 1.3.5",
                        "manual_review",
                    ))
            if has_any_term(identity, PHONE_TERMS) and "phone" not in input_type:
                phone_evidence = stable_input_purpose_evidence(
                    element,
                    resources,
                    id_to_label,
                    parent_map,
                    purpose_terms=PHONE_TERMS,
                    include_input_type=False,
                )
                phone_is_actionable = (
                    is_expanded_profile(detector_profile)
                    and high_confidence_input_semantics(
                        element,
                        styles,
                        phone_evidence,
                    )
                )
                if phone_is_actionable:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_PHONE_INPUTTYPE_MISSING",
                        "error",
                        f"XML 中存在明确电话字段证据 {phone_evidence!r}，但输入框缺少 phone 类型。",
                        ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
                        "Android XML phone EditText missing inputType phone",
                        "xml_safe",
                        confidence=0.9,
                        requires_review=False,
                        fix_hint="把 android:inputType 设置为 phone，并保留已有的其他输入限制标志。",
                    ))
                else:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_PHONE_INPUTTYPE_MISSING",
                        "warning",
                        "电话字段疑似缺少 android:inputType=\"phone\"。",
                        ["android.rule.forms-errors"],
                        "Android XML phone EditText missing inputType phone",
                    ))
            if (
                has_any_term(identity, NUMBER_TERMS)
                and "phone" not in input_type
                and not any(token in input_type for token in ["number", "decimal"])
            ):
                number_evidence = stable_input_purpose_evidence(
                    element,
                    resources,
                    id_to_label,
                    parent_map,
                    purpose_terms=SPECIFIC_NUMBER_TERMS,
                    include_input_type=False,
                )
                number_is_actionable = (
                    is_expanded_profile(detector_profile)
                    and high_confidence_input_semantics(
                        element,
                        styles,
                        number_evidence,
                    )
                )
                if number_is_actionable:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
                        "error",
                        f"XML 中存在明确数值字段证据 {number_evidence!r}，但输入框缺少 number 或 numberDecimal 类型。",
                        ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
                        "Android XML number EditText missing inputType number decimal",
                        "xml_safe",
                        confidence=0.9,
                        requires_review=False,
                        fix_hint="根据字段是否允许小数设置 number 或 numberDecimal，并保留已有的其他输入限制标志。",
                    ))
                else:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
                        "warning",
                        "数字字段疑似缺少 number/numberDecimal 类型 inputType。",
                        ["android.rule.forms-errors"],
                        "Android XML number EditText missing inputType number decimal",
                    ))
            is_person_name = (
                has_any_term(identity, PERSONAL_NAME_TERMS)
                or "textpersonname" in input_type
            )
            if EMIT_MISSING_AUTOFILL and is_person_name and not autofill and not autofill_disabled:
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_NAME_AUTOFILL_MISSING",
                    "warning",
                    "姓名或用户名字段疑似缺少 android:autofillHints。",
                    ["android.rule.forms-errors", "wcag22.sc.1.3.5"],
                    "Android XML name username EditText missing autofillHints",
                    "manual_review",
                ))

        if is_image_widget(element) and not is_interactive(element):
            content_description = attr(element, "contentDescription")
            if (
                content_description is None
                and important not in {"no", "noHideDescendants"}
                and not ignores_content_description(element)
            ):
                if looks_like_meaningful_image(element):
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION",
                        "warning",
                        "图片的 id 或资源名表明它可能是 Logo、品牌、头像、二维码、"
                        "图表或其他有意义内容，可能需要准确的 contentDescription。"
                        "请结合页面上下文确认是否已有等价文本，再决定是否添加描述。",
                        ["android.rule.content-labels", "android.fixmap.content-labeling"],
                        "Android meaningful logo brand image missing contentDescription do not hide decorative",
                        "manual_review",
                        confidence=0.7,
                        requires_review=True,
                        fix_hint="建议人工复核图片是否传达独立信息；有等价文本时可保持装饰语义，否则补充准确描述。",
                    ))
                elif looks_like_decorative_image(element):
                    pass
                else:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_IMAGE_SEMANTICS_REQUIRES_REVIEW",
                        "warning",
                        "无法仅根据 XML 确定图片是有意义内容还是纯装饰。"
                        "请结合页面上下文人工判断后再添加描述或隐藏。",
                        ["android.rule.content-labels", "android.fixmap.content-labeling"],
                        "Android ImageView semantic review meaningful or decorative context",
                        "manual_review",
                        confidence=0.55,
                        requires_review=True,
                        fix_hint="建议人工复核图片是信息内容还是装饰内容，不要仅凭资源名自动修改。",
                    ))

        if tag == "ProgressBar" and not hidden_from_a11y and not has_accessible_name(element, resources, id_to_label, parent_map):
            issues.append(make_issue(
                path,
                root,
                parent_map,
                element,
                "ANDROID_XML_PROGRESS_MISSING_STATUS_LABEL",
                "warning",
                "无法仅根据 XML 确定 ProgressBar 是否通过邻近文本或运行时代码"
                "提供状态说明，请结合界面和动态行为人工复核。",
                ["android.rule.compose-semantics-role-state", "android.fixcase.dynamic-status-silent"],
                "Android XML ProgressBar missing contentDescription status loading announcement",
                "manual_review",
            ))

        if is_custom_view(element) and (
            is_interactive(element)
            or is_input(element)
            or truthy(attr(element, "focusable"))
            or attr(element, "importantForAccessibility") == "yes"
        ):
            issues.append(make_issue(
                path,
                root,
                parent_map,
                element,
                "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW",
                "warning",
                "发现自定义 View。请检查 Kotlin/Java 是否实现 performClick、AccessibilityNodeInfo、键盘/方向键支持和必要的虚拟节点。",
                ["android.rule.custom-views", "android.fixcase.clickable-custom-view-no-performclick"],
                "Android custom View accessibility review performClick AccessibilityNodeInfo ExploreByTouchHelper",
                "manual_review",
            ))

        for text_attr in ["text", "hint", "contentDescription"] if EMIT_HARDCODED_TEXT else []:
            value = attr(element, text_attr)
            if is_likely_user_visible_text(value):
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_HARDCODED_ACCESSIBLE_TEXT",
                    "warning",
                    f"发现硬编码 android:{text_attr}。建议改为 @string/...，以支持本地化和一致的无障碍文本管理。",
                    ["android.rule.content-labels", "android.rule.forms-errors"],
                    "Android XML hardcoded text contentDescription hint use string resource localization",
                    "manual_review",
                ))

        if is_text_widget(element):
            foreground = resolve_color(attr(element, "textColor"), colors)
            background = nearest_background_color(element, parent_map, colors)
            if foreground and background:
                ratio = contrast_ratio(foreground, background)
                threshold = 3.0 if tag in {"Button", "MaterialButton"} else 4.5
                if ratio < threshold:
                    issues.append(make_issue(
                        path,
                        root,
                        parent_map,
                        element,
                        "ANDROID_XML_LOW_TEXT_CONTRAST",
                        "warning",
                        f"文本颜色与背景颜色静态计算对比度约为 {ratio:.2f}:1，低于建议阈值 {threshold}:1。",
                        ["android.rule.touch-targets-contrast", "android.fixmap.low-contrast"],
                        "Android XML low contrast textColor background color contrast ratio",
                        "manual_review",
                    ))

    for name, elements in names_by_value.items():
        if len(elements) < 2:
            continue
        normalized = name.strip().lower()
        parents = {parent_map.get(element) for element in elements}
        if normalized in GENERIC_LABELS and len(parents) == 1:
            for element in elements:
                issues.append(make_issue(
                    path,
                    root,
                    parent_map,
                    element,
                    "ANDROID_XML_REPEATED_GENERIC_LABEL",
                    "warning",
                    f"多个交互控件使用相同且较泛的可访问名称：{name!r}。列表或重复操作应加入条目上下文。",
                    ["android.pattern.list-item-actions", "android.fixcase.recycler-overflow-generic-label"],
                    "Android XML repeated generic label RecyclerView contentDescription item-specific",
                    "manual_review",
                ))

    return issues


def collect_xml_files(paths):
    files = []
    for raw_path in paths:
        path = raw_path.resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            layout_files = [
                item
                for item in path.rglob("*.xml")
                if "/build/" not in item.as_posix()
                and item.parent.name.startswith("layout")
            ]
            if layout_files:
                files.extend(layout_files)
            else:
                files.extend(item for item in path.glob("*.xml") if looks_like_layout_xml(item))
        else:
            files.append(path)
    return sorted(dict.fromkeys(files))


def scan(paths, detector_profile=DEFAULT_DETECTOR_PROFILE):
    if detector_profile not in DETECTOR_PROFILES:
        raise ValueError(f"未知检测策略: {detector_profile}")
    resources = load_string_resources(paths)
    colors = load_color_resources(paths)
    dimensions = load_dimension_resources(paths)
    styles = load_style_resources(paths)
    issues = []
    parse_errors = []
    for path in collect_xml_files(paths):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            parse_errors.append({
                "id": f"ANDROID_XML_PARSE_ERROR:{path.name}",
                "type": "error",
                "severity": "error",
                "confidence": 1.0,
                "requires_review": True,
                "component": "",
                "code": "ANDROID_XML_PARSE_ERROR",
                "message": f"XML 解析失败：{exc}",
                "fix_hint": "修正 XML 语法后重新运行检测。",
                "file": str(path),
                "element": "",
                "selector": "",
                "attributes": {},
                "related_docs": [],
                "repair_query": "Android XML parse error",
                "repairability": "manual_review",
            })
            continue
        apply_explicit_styles(root, styles)
        issues.extend(check_tree(
            path,
            root,
            resources,
            colors,
            dimensions,
            styles,
            detector_profile=detector_profile,
        ))
    return issues + parse_errors


def summarize(issues):
    return Counter(issue_severity(issue) for issue in issues)


def issue_severity(issue):
    severity = issue.get("severity", issue.get("type", "error"))
    return severity if severity in {"error", "warning", "info"} else "error"


def build_report(issues):
    counts = Counter(issue_severity(issue) for issue in issues)
    return {
        "issue_count": counts["error"],
        "error_count": counts["error"],
        "warning_count": counts["warning"],
        "info_count": counts["info"],
        "total_issue_count": len(issues),
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="Run static accessibility checks against Android XML layout files.")
    parser.add_argument("paths", nargs="+", help="Android XML file or directory, for example app/src/main/res/layout")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument(
        "--detector-profile",
        choices=DETECTOR_PROFILES,
        default=DEFAULT_DETECTOR_PROFILE,
        help="Detection policy profile; conservative_v1 preserves the frozen experiment behavior.",
    )
    args = parser.parse_args()

    paths = [Path(path) for path in args.paths]
    try:
        issues = scan(paths, detector_profile=args.detector_profile)
    except FileNotFoundError as exc:
        print(f"路径不存在：{exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(build_report(issues), ensure_ascii=False, indent=2))
        return

    counts = summarize(issues)
    print("Android XML 静态无障碍检测")
    print(f"检测目标：{', '.join(str(path) for path in paths)}")
    print(
        f"问题总数：{len(issues)}，错误：{counts['error']}，"
        f"警告：{counts['warning']}，提示：{counts['info']}"
    )
    if not issues:
        print("未发现此静态检测器可识别的问题。仍建议继续运行 Android Lint、Accessibility Scanner、TalkBack/Switch Access 测试。")
        return

    for index, issue in enumerate(issues, start=1):
        print()
        print(f"{index}. [{issue['type']}] {issue['code']}")
        print(f"   文件：{issue['file']}")
        print(f"   元素：{issue['element']}  位置：{issue['selector']}")
        print(f"   信息：{issue['message']}")
        print(f"   RAG 查询：{issue['repair_query']}")


if __name__ == "__main__":
    main()
