#!/usr/bin/env python3
"""Android XML accessibility repair loop with RAG context."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_ROUNDS = 3
DEFAULT_MAX_MODEL_ATTEMPTS = 3
MAX_OPERATIONS_PER_RESPONSE = 100
DETECTOR_PROFILE_CHOICES = ("conservative_v1", "expanded_v2", "expanded_v3")
DEFAULT_DETECTOR_PROFILE = "conservative_v1"
ANDROID_NS = "http://schemas.android.com/apk/res/android"
TOOLS_NS = "http://schemas.android.com/tools"
APP_NS = "http://schemas.android.com/apk/res-auto"

ET.register_namespace("android", ANDROID_NS)
ET.register_namespace("tools", TOOLS_NS)
ET.register_namespace("app", APP_NS)

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "retrieval"))

from generate import (  # noqa: E402
    MODEL_PROVIDER_CHOICES,
    ModelError,
    model_error_metadata,
    run_model_with_metadata,
    validate_model_configuration,
)
from retrieval.build_rag_prompt import format_document  # noqa: E402
from retrieval.search_documents import load_documents  # noqa: E402
from retrieval.v2_hybrid import (  # noqa: E402
    HashedSubwordVectorBackend,
    retrieve_for_issues,
)


ALLOWED_ATTRIBUTE_OPERATIONS = {
    "android:accessibilityHeading",
    "android:autofillHints",
    "android:clickable",
    "android:contentDescription",
    "android:focusable",
    "android:focusableInTouchMode",
    "android:hint",
    "android:importantForAccessibility",
    "android:importantForAutofill",
    "android:imeActionLabel",
    "android:inputType",
    "android:labelFor",
    "android:minHeight",
    "android:minWidth",
    "android:screenReaderFocusable",
    "android:text",
    "android:tooltipText",
    "tools:ignore",
}

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


def is_stateful_control_tag(tag_name: str) -> bool:
    return any(
        tag_name == control_tag or tag_name.endswith(control_tag)
        for control_tag in STATEFUL_CONTROL_TAGS
    )


IMAGE_TAGS = {
    "ImageButton",
    "ImageView",
    "ShapeableImageView",
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

OPERATION_FIELDS = {
    "remove_attribute": {
        "required": {"op", "path", "selector", "attribute"},
        "allowed": {"op", "path", "selector", "attribute"},
    },
    "set_attribute": {
        "required": {"op", "path", "selector", "attribute", "value"},
        "allowed": {"op", "path", "selector", "attribute", "value"},
    },
    "remove_attribute_value": {
        "required": {"op", "path", "selector", "attribute", "value"},
        "allowed": {"op", "path", "selector", "attribute", "value"},
    },
    "add_string_resource": {
        "required": {"op", "path", "name", "value"},
        "allowed": {"op", "path", "name", "value"},
    },
}

STRING_RESOURCE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESOURCE_XML_DIRECTORIES = {
    "anim",
    "animator",
    "color",
    "drawable",
    "font",
    "interpolator",
    "layout",
    "menu",
    "mipmap",
    "navigation",
    "transition",
    "values",
    "xml",
}


def package_paths(path: Path):
    path = path.resolve()
    if path.name == "res":
        return path.parent, path
    res_dir = path / "res"
    if not res_dir.exists():
        raise SystemExit(f"找不到 Android res 目录: {res_dir}")
    return path, res_dir


def run_xml_checker(
    res_dir: Path,
    detector_profile: str = DEFAULT_DETECTOR_PROFILE,
):
    if detector_profile not in DETECTOR_PROFILE_CHOICES:
        raise ValueError(f"未知检测策略: {detector_profile}")
    checker = ROOT / "tools" / "evaluation" / "android_xml_a11y_check.py"
    result = subprocess.run(
        [
            sys.executable,
            str(checker),
            str(res_dir),
            "--json",
            "--detector-profile",
            detector_profile,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Android XML 检测失败:\n{result.stderr}")
    payload = json.loads(result.stdout)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    raise SystemExit("Android XML 检测器返回了无法识别的 JSON 格式。")


def save_report(package_dir: Path, issues, filename="android_xml_a11y_report.json"):
    report_dir = package_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / filename
    report_path.write_text(
        json.dumps(issue_report(issues), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def save_safety_report(
    package_dir: Path,
    findings,
    filename="android_xml_repair_safety_report.json",
):
    report_dir = package_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / filename
    report_path.write_text(
        json.dumps(findings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def relative_xml_files(res_dir: Path):
    return {
        path.relative_to(res_dir).as_posix()
        for path in res_dir.rglob("*.xml")
        if path.is_file()
    }


def local_name(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def xml_root_name(path: Path):
    try:
        return local_name(ET.parse(path).getroot().tag)
    except ET.ParseError:
        return None


def string_resource_names(path: Path):
    if not path.exists():
        return set()
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return set()
    return {
        child.attrib.get("name")
        for child in root
        if local_name(child.tag) == "string" and child.attrib.get("name")
    }


def validate_repair_safety(original_res: Path, repaired_res: Path):
    findings = []
    original_files = relative_xml_files(original_res)
    repaired_files = relative_xml_files(repaired_res)

    for rel in sorted(repaired_files - original_files):
        if rel.startswith("layout"):
            findings.append({
                "type": "error",
                "code": "ANDROID_XML_REPAIR_NEW_LAYOUT_FILE",
                "file": f"res/{rel}",
                "message": "模型新增了 layout XML 文件。当前实验要求保持原 XML 结构，避免引入未验证的新布局文件。",
            })

    for rel in sorted(original_files - repaired_files):
        findings.append({
            "type": "error",
            "code": "ANDROID_XML_REPAIR_DELETED_XML_FILE",
            "file": f"res/{rel}",
            "message": "模型删除了原有 XML 文件，可能破坏资源引用或原功能。",
        })

    for rel in sorted(original_files & repaired_files):
        if not rel.startswith("layout"):
            continue
        before_root = xml_root_name(original_res / rel)
        after_root = xml_root_name(repaired_res / rel)
        if before_root and after_root and before_root != after_root:
            findings.append({
                "type": "error",
                "code": "ANDROID_XML_REPAIR_CHANGED_LAYOUT_ROOT",
                "file": f"res/{rel}",
                "message": f"模型把 layout 根元素从 {before_root} 改成 {after_root}，可能改变 include 或 inflate 行为。",
            })

    before_strings = string_resource_names(original_res / "values" / "strings.xml")
    after_strings = string_resource_names(repaired_res / "values" / "strings.xml")
    for name in sorted(before_strings - after_strings):
        findings.append({
            "type": "error",
            "code": "ANDROID_XML_REPAIR_DELETED_STRING_RESOURCE",
            "file": "res/values/strings.xml",
            "message": f"模型删除了原有字符串资源 {name}，可能破坏代码或其他语言资源引用。",
        })

    return findings


def qualify_attr(name: str):
    if name.startswith("{"):
        return name
    if ":" in name:
        prefix, local = name.split(":", 1)
        namespaces = {
            "android": ANDROID_NS,
            "tools": TOOLS_NS,
            "app": APP_NS,
        }
        if prefix not in namespaces:
            raise ValueError(f"不支持的 XML 属性命名空间: {name}")
        return f"{{{namespaces[prefix]}}}{local}"

    android_attrs = {
        "contentDescription",
        "focusable",
        "focusableInTouchMode",
        "hint",
        "importantForAccessibility",
        "inputType",
        "labelFor",
        "minHeight",
        "minWidth",
        "text",
    }
    tools_attrs = {"ignore", "context"}
    if name in android_attrs:
        return f"{{{ANDROID_NS}}}{name}"
    if name in tools_attrs:
        return f"{{{TOOLS_NS}}}{name}"
    return name


def parse_selector_part(part: str):
    if not part.endswith("]") or "[" not in part:
        return part, 1
    name, index = part[:-1].rsplit("[", 1)
    return name, int(index)


def split_selector_parts(selector: str):
    if not selector or not selector.startswith("/"):
        raise ValueError(f"选择器必须是检测报告中的绝对 selector: {selector}")
    parts = []
    current = []
    bracket_depth = 0
    quote = None
    for char in selector[1:]:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'} and bracket_depth:
            quote = char
            current.append(char)
        elif char == "[":
            bracket_depth += 1
            current.append(char)
        elif char == "]":
            bracket_depth = max(bracket_depth - 1, 0)
            current.append(char)
        elif char == "/" and bracket_depth == 0:
            if current:
                parts.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def find_by_selector(root, selector: str):
    parts = split_selector_parts(selector)
    current = root
    if parts:
        first_name, first_index = parse_selector_part(parts[0])
        if tag_local_name(root.tag) != tag_local_name(first_name) or first_index != 1:
            raise ValueError(f"选择器根节点不匹配: {selector}")
        parts = parts[1:]

    for part in parts:
        name, index = parse_selector_part(part)
        name = tag_local_name(name)
        matches = [
            child
            for child in list(current)
            if tag_local_name(child.tag) == name
        ]
        if index < 1 or index > len(matches):
            raise ValueError(f"选择器无法定位元素: {selector}")
        current = matches[index - 1]
    return current


def selector_steps(selector: str):
    return [parse_selector_part(part) for part in split_selector_parts(selector)]


def tag_local_name(tag: str):
    return tag.split(":", 1)[-1].rsplit(".", 1)[-1]


ID_SELECTOR_RE = re.compile(
    r"^(?P<name>[A-Za-z_][\w.:-]*)\s*"
    r"\[\s*@(?:android:)?id\s*=\s*(['\"])(?P<id>[^'\"]+)\2\s*\]$"
)


def resource_id_name(value):
    if not value:
        return None
    return re.sub(r"^@\+?id/", "", value)


def normalize_id_selector(text: str, selector: str):
    if "@id" not in selector and "@android:id" not in selector:
        return selector
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"无法解析 XML 以定位 id selector: {selector}") from exc

    parts = split_selector_parts(selector)
    current = root
    normalized = []
    for position, part in enumerate(parts):
        id_match = ID_SELECTOR_RE.match(part)
        if id_match:
            name = tag_local_name(id_match.group("name"))
            target_id = resource_id_name(id_match.group("id"))
            index = None
        else:
            name, index = parse_selector_part(part)
            name = tag_local_name(name)
            target_id = None

        if position == 0:
            if tag_local_name(current.tag) != name:
                raise ValueError(f"选择器根节点不匹配: {selector}")
            if target_id is not None:
                current_id = resource_id_name(
                    current.attrib.get(f"{{{ANDROID_NS}}}id")
                    or current.attrib.get("id")
                )
                if current_id != target_id:
                    raise ValueError(f"选择器根节点 id 不匹配: {selector}")
            normalized.append(f"{name}[1]")
            continue

        matches = [
            child
            for child in list(current)
            if tag_local_name(child.tag) == name
        ]
        if target_id is not None:
            id_matches = [
                child
                for child in matches
                if resource_id_name(
                    child.attrib.get(f"{{{ANDROID_NS}}}id")
                    or child.attrib.get("id")
                )
                == target_id
            ]
            if len(id_matches) != 1:
                raise ValueError(f"选择器 id 无法唯一定位元素: {selector}")
            current = id_matches[0]
            index = matches.index(current) + 1
        else:
            if index < 1 or index > len(matches):
                raise ValueError(f"选择器无法定位元素: {selector}")
            current = matches[index - 1]
        normalized.append(f"{name}[{index}]")
    return "/" + "/".join(normalized)


def find_opening_tag_span(text: str, selector: str):
    selector = normalize_id_selector(text, selector)
    target = selector_steps(selector)
    stack = [{"path": [], "counts": {}}]
    token_re = re.compile(
        r"<!--.*?-->|<\?.*?\?>|<!\[CDATA\[.*?\]\]>|<[^<>]+>",
        re.DOTALL,
    )
    for match in token_re.finditer(text):
        token = match.group(0)
        if token.startswith("<!--") or token.startswith("<?") or token.startswith("<!"):
            continue
        end_match = re.match(r"</\s*([A-Za-z_][\w.:-]*)\s*>", token)
        if end_match:
            if len(stack) > 1:
                stack.pop()
            continue

        start_match = re.match(r"<\s*([A-Za-z_][\w.:-]*)\b", token)
        if not start_match:
            continue
        name = tag_local_name(start_match.group(1))
        parent = stack[-1]
        parent["counts"][name] = parent["counts"].get(name, 0) + 1
        index = parent["counts"][name]
        path = parent["path"] + [(name, index)]
        if path == target:
            return match.start(), match.end()
        if not token.rstrip().endswith("/>"):
            stack.append({"path": path, "counts": {}})
    raise ValueError(f"选择器无法定位元素: {selector}")


def text_attr_name(name: str):
    if ":" in name:
        return name
    android_attrs = {
        "contentDescription",
        "focusable",
        "focusableInTouchMode",
        "hint",
        "importantForAccessibility",
        "inputType",
        "labelFor",
        "minHeight",
        "minWidth",
        "text",
    }
    if name in android_attrs:
        return f"android:{name}"
    if name in {"ignore", "context"}:
        return f"tools:{name}"
    return name


def escape_attr_value(value: str):
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )


def attr_pattern(attr_name: str):
    return re.compile(
        rf"(\s+){re.escape(attr_name)}\s*=\s*(['\"])(.*?)\2",
        re.DOTALL,
    )


def replace_tag(text: str, span, tag: str):
    start, end = span
    return text[:start] + tag + text[end:]


def remove_attribute_text(text: str, selector: str, attr: str):
    span = find_opening_tag_span(text, selector)
    tag = text[span[0]:span[1]]
    new_tag = attr_pattern(text_attr_name(attr)).sub("", tag, count=1)
    return replace_tag(text, span, new_tag)


def set_attribute_text(text: str, selector: str, attr: str, value: str):
    span = find_opening_tag_span(text, selector)
    tag = text[span[0]:span[1]]
    attr_name = text_attr_name(attr)
    pattern = attr_pattern(attr_name)
    escaped = escape_attr_value(value)
    if pattern.search(tag):
        new_tag = pattern.sub(lambda m: f'{m.group(1)}{attr_name}={m.group(2)}{escaped}{m.group(2)}', tag, count=1)
    else:
        if "\n" in tag:
            indents = re.findall(r"\n([ \t]+)\S", tag)
            indent = indents[-1] if indents else "    "
            close_index = tag.rfind("/>") if tag.rstrip().endswith("/>") else tag.rfind(">")
            prefix = tag[:close_index]
            insertion = f'{indent}{attr_name}="{escaped}"'
            if prefix.endswith("\n"):
                new_tag = prefix + insertion + "\n" + tag[close_index:]
            else:
                new_tag = prefix + "\n" + insertion + tag[close_index:]
        else:
            close_index = tag.rfind("/>") if tag.rstrip().endswith("/>") else tag.rfind(">")
            new_tag = tag[:close_index].rstrip() + f' {attr_name}="{escaped}"' + tag[close_index:]
    return replace_tag(text, span, new_tag)


def remove_attribute_value_text(text: str, selector: str, attr: str, value: str):
    span = find_opening_tag_span(text, selector)
    tag = text[span[0]:span[1]]
    attr_name = text_attr_name(attr)
    pattern = attr_pattern(attr_name)
    match = pattern.search(tag)
    if not match:
        return text
    values = [part.strip() for part in match.group(3).split(",") if part.strip() and part.strip() != value]
    if not values:
        new_tag = pattern.sub("", tag, count=1)
    else:
        joined = ", ".join(values)
        new_tag = pattern.sub(lambda m: f'{m.group(1)}{attr_name}={m.group(2)}{escape_attr_value(joined)}{m.group(2)}', tag, count=1)
    return replace_tag(text, span, new_tag)


def add_string_resource_text(text: str, name: str, value: str):
    existing = re.compile(
        rf"(<string\s+name=(['\"]){re.escape(name)}\2\s*>)(.*?)(</string>)",
        re.DOTALL,
    )
    if existing.search(text):
        return existing.sub(lambda m: f"{m.group(1)}{value}{m.group(4)}", text, count=1)

    close = text.rfind("</resources>")
    if close == -1:
        raise ValueError("strings.xml 缺少 </resources>。")
    indent_match = re.search(r"\n([ \t]*)<string\b", text)
    indent = indent_match.group(1) if indent_match else "    "
    insertion = f'{indent}<string name="{name}">{value}</string>\n'
    return text[:close] + insertion + text[close:]


def write_xml_tree(tree, path: Path):
    try:
        ET.indent(tree, space="    ")
    except AttributeError:
        pass
    tree.write(path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def normalize_resource_path(rel: str):
    if not isinstance(rel, str):
        raise ValueError("操作 path 必须是字符串。")
    normalized = rel.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    path = Path(normalized)
    if normalized.startswith("/") or ".." in path.parts:
        raise ValueError(f"拒绝写入不安全路径: {rel}")
    parts = path.parts
    if (
        parts
        and parts[0] != "res"
        and parts[0].split("-", 1)[0] in RESOURCE_XML_DIRECTORIES
    ):
        normalized = f"res/{normalized}"
    if not normalized.startswith("res/") or not normalized.endswith(".xml"):
        raise ValueError(f"操作路径必须是 res/ 下的 XML 文件: {rel}")
    return normalized


def safe_target(output_package: Path, rel: str):
    normalized = normalize_resource_path(rel)
    root = output_package.resolve()
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"拒绝写入实验目录之外的路径: {normalized}") from exc
    return target


def is_default_values_resource(path: Path):
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return False
    return tag_local_name(root.tag) == "resources"


def default_string_resource_files(res_dir: Path):
    values = Path(res_dir) / "values"
    if not values.is_dir():
        return []
    candidates = []
    for path in sorted(values.glob("*.xml")):
        if not is_default_values_resource(path):
            continue
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        string_count = sum(
            tag_local_name(child.tag) == "string" for child in root
        )
        if not string_count:
            continue
        priority = (
            0 if path.name == "strings.xml"
            else 1 if path.name == "translatable.xml"
            else 2
        )
        candidates.append((priority, -string_count, path.name, path))
    return [item[-1].resolve() for item in sorted(candidates)]


def resolve_string_resource_target(output_package: Path, rel: str):
    requested = safe_target(output_package, rel)
    relative = requested.relative_to(output_package.resolve())
    if relative.parent.as_posix() != "res/values":
        raise ValueError("字符串资源只能写入默认 res/values 目录中的 XML 文件。")
    if requested.exists():
        if not is_default_values_resource(requested):
            raise ValueError(f"字符串资源目标不是有效的 <resources> XML: {relative}")
        return requested
    existing = default_string_resource_files(output_package / "res")
    if existing:
        return existing[0]
    return output_package.resolve() / "res/values/accessibility_strings.xml"


def apply_attribute_operation(output_package: Path, item: dict, mode: str):
    target = safe_target(output_package, item.get("path"))
    selector = item.get("selector")
    attr = item.get("attribute")
    if not target.exists():
        raise ValueError(f"目标文件不存在: {target}")
    if not isinstance(selector, str) or not isinstance(attr, str):
        raise ValueError(f"{mode} 操作必须包含 selector 和 attribute。")

    text = target.read_text(encoding="utf-8")
    if mode == "remove_attribute":
        new_text = remove_attribute_text(text, selector, attr)
    else:
        value = item.get("value")
        if not isinstance(value, str):
            raise ValueError("set_attribute 操作必须包含字符串 value。")
        new_text = set_attribute_text(text, selector, attr, value)
    target.write_text(new_text, encoding="utf-8")
    return target


def apply_remove_attribute_value(output_package: Path, item: dict):
    target = safe_target(output_package, item.get("path"))
    selector = item.get("selector")
    attr = item.get("attribute")
    value = item.get("value")
    if not isinstance(selector, str) or not isinstance(attr, str) or not isinstance(value, str):
        raise ValueError("remove_attribute_value 操作必须包含 selector、attribute 和 value。")

    text = target.read_text(encoding="utf-8")
    target.write_text(remove_attribute_value_text(text, selector, attr, value), encoding="utf-8")
    return target


def apply_add_string_resource(output_package: Path, item: dict):
    rel = item.get("path", "res/values/strings.xml")
    target = resolve_string_resource_target(output_package, rel)
    name = item.get("name")
    value = item.get("value")
    if not isinstance(name, str) or not name:
        raise ValueError("add_string_resource 操作必须包含 name。")
    if not isinstance(value, str):
        raise ValueError("add_string_resource 操作必须包含字符串 value。")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = (
        target.read_text(encoding="utf-8")
        if target.exists()
        else "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<resources>\n</resources>\n"
    )
    target.write_text(add_string_resource_text(text, name, value), encoding="utf-8")
    return target


def issue_query(issue):
    parts = [
        "Android XML accessibility repair",
        issue.get("code", ""),
        issue.get("element", ""),
        issue.get("message", ""),
        issue.get("repair_query", ""),
    ]
    return " ".join(part for part in parts if part)


def retrieve_documents(issues, limit):
    if limit < 1:
        return []
    results = retrieve_for_issues(
        issues,
        load_documents(),
        per_issue_limit=min(limit, 3),
        prompt_limit=min(limit, 4),
        direct_limit=2,
        candidate_limit=20,
        dense_backend=HashedSubwordVectorBackend(),
        lexical_weight=0.65,
        query_builder=issue_query,
    )
    return [result["document"] for result in results]


def path_inside(path: Path, root: Path):
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None


def issue_files(issues, res_dir: Path):
    files = []
    seen = set()
    for issue in issues:
        file_value = issue.get("file")
        if not file_value:
            continue
        path = Path(file_value)
        rel = path_inside(path, res_dir)
        if rel is None:
            continue
        target = res_dir / rel
        if target.exists() and target.suffix == ".xml" and rel.as_posix() not in seen:
            seen.add(rel.as_posix())
            files.append(target)

    supporting = [
        Path("values/colors.xml"),
        Path("values/dimens.xml"),
        Path("values/styles.xml"),
    ]
    supporting = [
        path.relative_to(Path(res_dir).resolve())
        for path in default_string_resource_files(res_dir)
    ] + supporting
    for rel in supporting:
        target = res_dir / rel
        if target.exists() and rel.as_posix() not in seen:
            seen.add(rel.as_posix())
            files.append(target)
    return files


def format_issues(issues, res_dir: Path):
    lines = []
    for index, issue in enumerate(issues, 1):
        file_value = issue.get("file", "")
        rel = path_inside(Path(file_value), res_dir) if file_value else None
        file_label = rel.as_posix() if rel else file_value
        lines.append(
            f"{index}. [{issue_severity(issue)}] {issue.get('code')}\n"
            f"   File: {file_label}\n"
            f"   Element: {issue.get('element')} at {issue.get('selector')}\n"
            f"   Severity: {issue_severity(issue)}\n"
            f"   Repairability: {issue.get('repairability', 'xml_safe')}\n"
            f"   Message: {issue.get('message')}\n"
            f"   Repair query: {issue.get('repair_query', '')}\n"
            f"   Attributes: {json.dumps(issue.get('attributes', {}), ensure_ascii=False)}"
        )
    return "\n\n".join(lines)


def format_files(files, res_dir: Path):
    sections = []
    for path in files:
        rel = path.relative_to(res_dir).as_posix()
        sections.append(
            f"### res/{rel}\n"
            "```xml\n"
            f"{path.read_text(encoding='utf-8')}\n"
            "```"
        )
    return "\n\n".join(sections)


def build_android_repair_prompt(
    issues,
    res_dir: Path,
    limit: int,
    use_rag: bool = True,
    repairability_filtering: bool = True,
):
    documents = retrieve_documents(issues, limit) if use_rag else []
    docs_text = "\n\n".join(format_document(document) for document in documents)
    if use_rag and not docs_text:
        docs_text = "No relevant documents were retrieved. Follow Android accessibility best practices."
    if not use_rag:
        docs_text = "RAG retrieval is disabled for this ablation condition."
    knowledge_instruction = (
        "Use the retrieved accessibility knowledge as authoritative context."
        if use_rag
        else "Use the detector findings and your general Android accessibility knowledge."
    )
    repair_scope = (
        "Only repair issues with Severity: error and Repairability: xml_safe.\n"
        "Do not attempt issues marked manual_review or requires_structure_or_code."
        if repairability_filtering
        else "Attempt every issue with Severity: error regardless of its Repairability value.\n"
        "The deterministic operation validator and structural safety checks still apply."
    )

    files = issue_files(issues, res_dir)
    return f"""You are an accessibility-focused Android XML repair assistant.

{knowledge_instruction}
Repair the provided Android XML resources while preserving the original app behavior, layout intent, ids, input restrictions, and resource references.

Do not rewrite unrelated files.
Use the smallest possible XML changes needed to fix the reported issues.
Preserve existing element types, ids, styles, dimensions, layout hierarchy, and include tags unless the reported issue cannot be fixed otherwise.
Do not expand <include> tags into copied child layouts.
Do not replace a reusable layout file with a different screen or a larger layout.
Do not remove existing string, color, dimension, style, or drawable resources; only add new resources when needed.
Do not suppress accessibility warnings with tools:ignore unless the element is truly decorative or hidden from users.
Prefer stable string resources over hardcoded visible text or content descriptions.
When adding a new resource string, target the existing default string-resource XML shown below. If no default string-resource file is shown, use res/values/strings.xml and the executor will safely route it or create a dedicated accessibility string file.
{repair_scope}
Images whose id or resource name contains logo, brand, avatar, profile, QR, map, chart, photo, cover, or thumbnail are meaningful by default. Add an accurate localized contentDescription; never hide them as decorative.
Set importantForAccessibility="no" only for clearly decorative visuals that duplicate nearby accessible text or provide no meaning, context, identity, or function.
For input hints or labels, use meaningful purpose text such as "Enter threshold value"; do not use numeric-only examples such as "00" as the accessible name.
For stateful controls such as Spinner, SeekBar, RatingBar, Switch, and CheckBox, do not add a fixed contentDescription that could replace or obscure the current value/state announced by accessibility services.
When a visible TextView already labels a stateful control, prefer adding android:labelFor to that TextView and point it to the existing control id.

Retrieved knowledge:

{docs_text}

Detected Android XML accessibility issues:

{format_issues(issues, res_dir)}

Current XML files:

{format_files(files, res_dir)}

Output rules:
Return only a strict JSON object, with no markdown and no explanation.
For element operations, use the exact absolute selector shown in the detected issue report.
Never use placeholder selector names such as Root or Child.
The JSON object must have this shape:
{{
  "operations": [
    {{
      "op": "remove_attribute",
      "path": "res/layout/example.xml",
      "selector": "/LinearLayout[1]/ImageButton[1]",
      "attribute": "android:focusable"
    }},
    {{
      "op": "set_attribute",
      "path": "res/layout/example.xml",
      "selector": "/EditText[1]",
      "attribute": "android:hint",
      "value": "@string/example_hint"
    }},
    {{
      "op": "remove_attribute_value",
      "path": "res/layout/example.xml",
      "selector": "/EditText[1]",
      "attribute": "tools:ignore",
      "value": "LabelFor"
    }},
    {{
      "op": "add_string_resource",
      "path": "res/values/strings.xml",
      "name": "example_hint",
      "value": "Example"
    }}
  ]
}}
Allowed operations are only remove_attribute, set_attribute, remove_attribute_value, and add_string_resource.
Do not output complete XML files.
Do not propose new layout files. A missing default string-resource file may only be handled through add_string_resource.
Do not propose deleting files or deleting resources.
For reusable included input layouts, prefer adding a generic hint to the reusable layout rather than expanding or replacing include tags.
"""


def extract_json_object(text: str):
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start : end + 1]
    return json.loads(stripped)


def canonical_attribute_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("attribute 必须是非空字符串。")
    canonical = text_attr_name(name.strip())
    if canonical not in ALLOWED_ATTRIBUTE_OPERATIONS:
        raise ValueError(f"不允许修改的 XML 属性: {name}")
    return canonical


def selector_target_element(text: str, selector: str):
    normalized = normalize_id_selector(text, selector)
    root = ET.fromstring(text)
    return find_by_selector(root, normalized)


def selector_target_tag(text: str, selector: str):
    return tag_local_name(selector_target_element(text, selector).tag)


def operation_target_identity(element):
    values = [
        element.attrib.get(f"{{{ANDROID_NS}}}id", ""),
        element.attrib.get(f"{{{ANDROID_NS}}}src", ""),
        element.attrib.get(f"{{{ANDROID_NS}}}background", ""),
        element.attrib.get(f"{{{APP_NS}}}srcCompat", ""),
    ]
    return " ".join(values)


def is_likely_meaningful_image(element):
    if tag_local_name(element.tag) not in IMAGE_TAGS:
        return False
    identity = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1 \2",
        operation_target_identity(element),
    ).lower()
    tokens = set(re.findall(r"[a-z0-9]+", identity))
    return bool(tokens & MEANINGFUL_IMAGE_TERMS)


def input_type_flags(value):
    if not value:
        return set()
    return {
        item.strip().lower()
        for item in str(value).split("|")
        if item.strip()
    }


def validate_operation(output_package: Path, item: dict, index: int):
    if not isinstance(item, dict):
        raise ValueError(f"operation[{index}] 必须是对象。")
    op = item.get("op")
    schema = OPERATION_FIELDS.get(op)
    if schema is None:
        raise ValueError(f"operation[{index}] 使用了不允许的 op: {op}")

    keys = set(item)
    missing = schema["required"] - keys
    extra = keys - schema["allowed"]
    if missing:
        raise ValueError(
            f"operation[{index}] 缺少字段: {', '.join(sorted(missing))}"
        )
    if extra:
        raise ValueError(
            f"operation[{index}] 包含未知字段: {', '.join(sorted(extra))}"
        )

    normalized = dict(item)
    if op == "add_string_resource":
        target = resolve_string_resource_target(output_package, item["path"])
        normalized["path"] = target.relative_to(
            output_package.resolve()
        ).as_posix()
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not STRING_RESOURCE_NAME_RE.fullmatch(name):
            raise ValueError(f"operation[{index}] string name 不合法: {name!r}")
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError(
                f"operation[{index}] string value 必须是 1-2000 字符的非空字符串。"
            )
        return normalized

    target = safe_target(output_package, item["path"])
    normalized["path"] = target.relative_to(output_package.resolve()).as_posix()
    if not target.exists():
        raise ValueError(
            f"operation[{index}] 目标文件不存在: {normalized['path']}"
        )

    selector = item.get("selector")
    if not isinstance(selector, str) or not selector.startswith("/"):
        raise ValueError(f"operation[{index}] selector 必须是绝对元素路径。")
    normalized["attribute"] = canonical_attribute_name(item.get("attribute"))
    if "value" in item:
        value = item["value"]
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError(
                f"operation[{index}] value 必须是最长 2000 字符的字符串。"
            )

    text = target.read_text(encoding="utf-8")
    target_element = selector_target_element(text, selector)
    target_tag = tag_local_name(target_element.tag)
    if (
        op == "set_attribute"
        and normalized["attribute"] == "android:labelFor"
    ):
        proposed_value = normalized.get("value", "")
        if not target_tag.endswith("TextView"):
            raise ValueError(
                f"operation[{index}] android:labelFor 只能设置在可见 TextView 标签上。"
            )
        match = re.fullmatch(r"@id/([A-Za-z_][A-Za-z0-9_.]*)", proposed_value)
        if not match:
            raise ValueError(
                f"operation[{index}] android:labelFor 必须使用已存在目标的 "
                "@id/name 引用，不能使用 @+id/name。"
            )
        target_id = match.group(1)
        root = ET.fromstring(text)
        referenced = next(
            (
                element
                for element in root.iter()
                if resource_id_name(
                    element.attrib.get(f"{{{ANDROID_NS}}}id", "")
                ) == target_id
            ),
            None,
        )
        if referenced is None:
            raise ValueError(
                f"operation[{index}] android:labelFor 指向不存在的 id: "
                f"{proposed_value}"
            )
        referenced_tag = tag_local_name(referenced.tag)
        labelable_suffixes = (
            "EditText",
            "AutoCompleteTextView",
            "Spinner",
            "RadioGroup",
            "CheckBox",
            "SwitchCompat",
            "Switch",
            "SeekBar",
            "RatingBar",
        )
        if not referenced_tag.endswith(labelable_suffixes):
            raise ValueError(
                f"operation[{index}] android:labelFor 目标不是受支持的输入或选择控件: "
                f"{referenced_tag}"
            )
    if normalized["attribute"] == "android:inputType":
        if op == "remove_attribute":
            raise ValueError(
                f"operation[{index}] 不允许删除现有 android:inputType；"
                "这可能改变键盘、掩码或输入校验行为。"
            )
        if op == "set_attribute":
            current_value = target_element.attrib.get(
                f"{{{ANDROID_NS}}}inputType",
                "",
            )
            proposed_value = normalized.get("value", "")
            proposed_flags = input_type_flags(proposed_value)
            if not proposed_flags:
                raise ValueError(
                    f"operation[{index}] android:inputType 不能为空。"
                )
            generic_flags = {"text", "number", "none"}
            protected_flags = input_type_flags(current_value) - generic_flags
            missing_flags = protected_flags - proposed_flags
            if missing_flags:
                raise ValueError(
                    f"operation[{index}] 修改 android:inputType 时丢失了原有"
                    f"输入限制: {', '.join(sorted(missing_flags))}。"
                )
    if (
        op == "set_attribute"
        and normalized["attribute"] == "android:contentDescription"
        and is_stateful_control_tag(target_tag)
    ):
        raise ValueError(
            f"operation[{index}] 拒绝给状态控件 {target_tag} 设置固定 "
            "contentDescription；请使用可见标签的 android:labelFor，"
            "避免覆盖当前值或状态播报。"
        )
    if (
        op == "set_attribute"
        and normalized["attribute"] == "android:importantForAccessibility"
        and str(normalized.get("value", "")).lower() in {"no", "nohidedescendants"}
        and is_likely_meaningful_image(target_element)
    ):
        raise ValueError(
            f"operation[{index}] 拒绝隐藏疑似有意义图片 {target_tag}。"
            "其 id 或资源名包含 logo/brand/avatar/profile/QR/map/chart/"
            "photo/cover/thumbnail 等语义，请添加准确的 contentDescription。"
        )
    return normalized


def validate_model_operations(output_package: Path, model_output: str):
    try:
        data = extract_json_object(model_output)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"模型输出不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"operations"}:
        raise ValueError("模型输出顶层必须且只能包含 operations。")
    operations = data.get("operations")
    if not isinstance(operations, list):
        raise ValueError("模型输出 JSON 缺少 operations 数组。")
    if not operations:
        raise ValueError("模型返回了空 operations，无法改善当前问题。")
    if len(operations) > MAX_OPERATIONS_PER_RESPONSE:
        raise ValueError(
            f"单次模型响应最多允许 {MAX_OPERATIONS_PER_RESPONSE} 个 operations。"
        )
    return [
        validate_operation(output_package, item, index)
        for index, item in enumerate(operations)
    ]


def validate_xml_files(paths):
    for path in paths:
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            raise ValueError(f"模型操作导致 XML 无法解析: {path}: {exc}") from exc


def apply_model_result(output_package: Path, model_output: str):
    operations = validate_model_operations(output_package, model_output)
    target_paths = {
        safe_target(output_package, item["path"])
        for item in operations
    }
    snapshots = {
        path: path.read_bytes() if path.exists() else None
        for path in target_paths
    }
    changed = []
    try:
        for item in operations:
            op = item["op"]
            if op in {"remove_attribute", "set_attribute"}:
                changed.append(apply_attribute_operation(output_package, item, op))
            elif op == "remove_attribute_value":
                changed.append(apply_remove_attribute_value(output_package, item))
            else:
                changed.append(apply_add_string_resource(output_package, item))
        changed = sorted(set(changed))
        validate_xml_files(changed)
        if all(
            snapshots[path] is not None and path.read_bytes() == snapshots[path]
            for path in changed
        ):
            raise ValueError("模型 operations 没有产生任何实际修改。")
        return changed
    except Exception:
        for path, content in snapshots.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise


def save_round_artifact(output_package: Path, filename: str, content: str):
    report_dir = output_package / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def save_json_artifact(output_package: Path, filename: str, payload):
    return save_round_artifact(
        output_package,
        filename,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def issue_quality(issues):
    report = issue_report(issues)
    return (
        report["error_count"],
        report["warning_count"],
        report["info_count"],
        report["total_issue_count"],
    )


def issue_severity(issue):
    severity = issue.get("severity", issue.get("type", "error"))
    return severity if severity in {"error", "warning", "info"} else "error"


def issue_report(issues):
    error_count = sum(issue_severity(issue) == "error" for issue in issues)
    warning_count = sum(issue_severity(issue) == "warning" for issue in issues)
    info_count = sum(issue_severity(issue) == "info" for issue in issues)
    return {
        "issue_count": error_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "total_issue_count": len(issues),
        "issues": issues,
    }


def error_count(issues):
    return sum(issue_severity(issue) == "error" for issue in issues)


def repair_rate(before_error_count, after_error_count):
    if before_error_count == 0:
        return None
    return (before_error_count - after_error_count) / before_error_count


def update_no_improvement_streak(before_error_count, after_error_count, current_streak):
    if after_error_count < before_error_count:
        return 0
    return current_streak + 1


def should_continue_repair(issues):
    return error_count(issues) > 0


def repairable_issues(issues):
    return [
        issue
        for issue in issues
        if issue_severity(issue) == "error"
        and issue.get("repairability", "xml_safe") == "xml_safe"
    ]


def deferred_issues(issues):
    return [
        issue
        for issue in issues
        if issue_severity(issue) != "error"
        or issue.get("repairability", "xml_safe") != "xml_safe"
    ]


def actionable_issues(issues, repairability_filtering=True):
    if repairability_filtering:
        return repairable_issues(issues)
    return [
        issue for issue in issues
        if issue_severity(issue) == "error"
    ]


def non_actionable_issues(issues, repairability_filtering=True):
    if repairability_filtering:
        return deferred_issues(issues)
    return [
        issue for issue in issues
        if issue_severity(issue) != "error"
    ]


def repairability_counts(issues):
    counts = {}
    for issue in issues:
        key = issue.get("repairability", "xml_safe")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def issue_signature(issues):
    rows = [
        (
            issue_severity(issue),
            issue.get("code", ""),
            Path(issue.get("file", "")).name,
            issue.get("selector", ""),
        )
        for issue in issues
    ]
    return tuple(sorted(rows))


def resource_state_hash(res_dir: Path):
    digest = hashlib.sha256()
    for path in sorted(res_dir.rglob("*.xml")):
        digest.update(path.relative_to(res_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_operation_retry_prompt(base_prompt: str, response: str, error: str):
    return (
        f"{base_prompt}\n\n"
        "Your previous JSON response was rejected by the deterministic XML "
        "operation validator. No changes from that response were committed.\n\n"
        f"Validator error:\n{error}\n\n"
        "Previous rejected response:\n"
        f"{response[:12000]}\n\n"
        "Return a corrected strict JSON object only. Keep the same smallest "
        "possible accessibility repair and follow the operation schema exactly."
    )


def evaluate_and_commit_candidate(
    output_package: Path,
    input_res: Path,
    current_issues,
    model_output: str,
    detector_profile: str = DEFAULT_DETECTOR_PROFILE,
):
    with tempfile.TemporaryDirectory(
        prefix="android_xml_candidate_",
        dir=str(output_package.parent),
    ) as temp:
        candidate_package = Path(temp) / "package"
        shutil.copytree(output_package, candidate_package)
        changed = apply_model_result(candidate_package, model_output)
        candidate_res = candidate_package / "res"
        candidate_issues = run_xml_checker(
            candidate_res,
            detector_profile=detector_profile,
        )
        candidate_safety = validate_repair_safety(input_res, candidate_res)
        if candidate_safety:
            codes = ", ".join(
                finding.get("code", "UNKNOWN")
                for finding in candidate_safety
            )
            raise ValueError(f"候选修复未通过结构安全检查: {codes}")

        before_quality = issue_quality(current_issues)
        after_quality = issue_quality(candidate_issues)
        if error_count(candidate_issues) >= error_count(current_issues):
            raise ValueError(
                "候选修复没有严格改善 error_count: "
                f"before={before_quality}, after={after_quality}"
            )

        committed = []
        for candidate_path in changed:
            rel = candidate_path.relative_to(candidate_package.resolve())
            destination = output_package / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_path, destination)
            committed.append(destination)
        return sorted(committed), candidate_issues


def initial_run_state(
    provider: str,
    model: str,
    max_rounds: int,
    max_attempts: int,
    use_rag: bool = True,
    repairability_filtering: bool = True,
    detector_profile: str = DEFAULT_DETECTOR_PROFILE,
):
    return {
        "provider": provider,
        "model": model,
        "status": "running",
        "max_rounds": max_rounds,
        "max_model_attempts_per_round": max_attempts,
        "uses_rag": use_rag,
        "uses_detector_feedback": max_rounds > 1,
        "repairability_filtering": repairability_filtering,
        "detector_profile": detector_profile,
        "rounds": [],
    }


def prepare_output(input_package: Path, output_package: Path, force: bool):
    if output_package.exists():
        if not force:
            raise SystemExit(f"输出目录已存在，请加 --force 覆盖: {output_package}")
        shutil.rmtree(output_package)
    shutil.copytree(input_package, output_package)


def main():
    parser = argparse.ArgumentParser(
        description="用 RAG + LLM + Android XML 静态检测器修复 Android XML 无障碍问题。"
    )
    parser.add_argument("input", help="原始 XML 测试包目录，或其中的 res 目录")
    parser.add_argument("output", nargs="?", help="修复输出目录，例如 test_apps/AppName/xml_fixed")
    parser.add_argument(
        "--provider",
        choices=MODEL_PROVIDER_CHOICES,
        default="deepseek",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    parser.add_argument(
        "--max-model-attempts",
        type=int,
        default=DEFAULT_MAX_MODEL_ATTEMPTS,
        help=(
            "每轮检测中允许模型修正无效 operation 的次数 "
            f"(default: {DEFAULT_MAX_MODEL_ATTEMPTS})"
        ),
    )
    parser.add_argument("--force", action="store_true", help="覆盖已存在的输出目录")
    parser.add_argument("--print-prompt", action="store_true", help="只打印第一轮修复 prompt，不调用模型")
    parser.add_argument("--save-prompt", help="把第一轮修复 prompt 保存到指定文件")
    parser.add_argument(
        "--disable-rag",
        action="store_true",
        help="消融实验：不检索或注入 RAG 文档。",
    )
    parser.add_argument(
        "--disable-repairability-filter",
        action="store_true",
        help="消融实验：将所有 error 送入模型，仍保留安全执行器。",
    )
    parser.add_argument(
        "--detector-profile",
        choices=DETECTOR_PROFILE_CHOICES,
        default=DEFAULT_DETECTOR_PROFILE,
        help=(
            "检测策略；conservative_v1 保持冻结预实验行为，"
            "expanded_v2 启用经过高置信条件约束的新增 XML 修复类型，"
            "expanded_v3 进一步细分控件语义并支持安全恢复被隐藏的标准控件。"
        ),
    )
    args = parser.parse_args()
    use_rag = not args.disable_rag
    repairability_filtering = not args.disable_repairability_filter

    if args.model is None:
        defaults = {
            "deepseek": "deepseek-v4-pro",
            "openai": "gpt-5",
            "anthropic": "claude-opus-4-20250514",
            "ollama": "gemma3:12b",
        }
        args.model = defaults[args.provider]

    input_package, input_res = package_paths(Path(args.input))
    initial_issues = run_xml_checker(
        input_res,
        detector_profile=args.detector_profile,
    )
    save_report(input_package, initial_issues)

    if args.print_prompt or args.save_prompt:
        selected_issues = actionable_issues(
            initial_issues, repairability_filtering
        )
        if selected_issues:
            prompt = build_android_repair_prompt(
                selected_issues,
                input_res,
                args.limit,
                use_rag=use_rag,
                repairability_filtering=repairability_filtering,
            )
        else:
            prompt = (
                "No Severity: error and Repairability: xml_safe issues were detected. "
                "The remaining findings require manual review, layout structure "
                "changes, or runtime code and must not be sent to the XML "
                "auto-repair model."
            )
        if args.save_prompt:
            prompt_path = Path(args.save_prompt)
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")
            print(f"已保存 prompt: {prompt_path}")
        if args.print_prompt:
            print(prompt)
        return

    if not args.output:
        raise SystemExit("调用模型修复时必须提供输出目录。")
    if args.max_rounds < 1 or args.max_model_attempts < 1:
        raise SystemExit("--max-rounds 和 --max-model-attempts 必须至少为 1。")

    output_package = Path(args.output).resolve()
    prepare_output(input_package, output_package, args.force)
    output_res = output_package / "res"
    run_state = initial_run_state(
        args.provider,
        args.model,
        args.max_rounds,
        args.max_model_attempts,
        use_rag,
        repairability_filtering,
        args.detector_profile,
    )
    run_state["initial_issue_quality"] = list(issue_quality(initial_issues))
    run_state["initial_error_count"] = error_count(initial_issues)
    run_state["initial_repairability"] = repairability_counts(initial_issues)
    save_json_artifact(output_package, "repair_run.json", run_state)
    no_improvement_rounds = 0

    for round_num in range(1, args.max_rounds + 1):
        issues = run_xml_checker(
            output_res,
            detector_profile=args.detector_profile,
        )
        report_path = save_report(output_package, issues)
        save_report(
            output_package,
            issues,
            f"android_xml_a11y_report_round_{round_num}.json",
        )
        safety_findings = validate_repair_safety(input_res, output_res)
        safety_report_path = save_safety_report(output_package, safety_findings)
        quality = issue_quality(issues)
        current_error_count = error_count(issues)
        selected_issues = actionable_issues(
            issues, repairability_filtering
        )
        deferred = non_actionable_issues(
            issues, repairability_filtering
        )
        round_state = {
            "round": round_num,
            "before_quality": list(quality),
            "before_error_count": current_error_count,
            "repairable_issue_count": len(selected_issues),
            "deferred_issue_count": len(deferred),
            "attempts": [],
        }
        run_state["rounds"].append(round_state)

        report = issue_report(issues)
        print(
            f"第 {round_num} 轮检测: {report['error_count']} errors, "
            f"{report['warning_count']} warnings, {report['info_count']} info"
        )
        print(f"报告: {report_path}")
        if safety_findings:
            print(f"结构安全检查: {len(safety_findings)} findings")
            print(f"结构安全报告: {safety_report_path}")
        if current_error_count == 0 and not safety_findings:
            run_state["status"] = (
                "completed" if not issues else "completed_with_observations"
            )
            run_state["final_issue_quality"] = list(issue_quality(issues))
            run_state["final_error_count"] = 0
            run_state["repair_rate"] = repair_rate(
                run_state["initial_error_count"],
                0,
            )
            run_state["final_repairability"] = repairability_counts(issues)
            run_state["deferred_issues"] = deferred
            run_state["completed_round"] = round_num
            save_json_artifact(output_package, "repair_run.json", run_state)
            if issues:
                print(
                    "所有 XML 安全可自动修复的问题均已处理；"
                    f"仍有 {len(deferred)} 个问题需要人工、结构或运行时代码处理。"
                )
            else:
                print("Android XML 静态检测通过。")
            return
        if current_error_count == 0 and safety_findings:
            run_state["status"] = "failed"
            run_state["failure"] = {
                "code": "ANDROID_XML_REPAIR_SAFETY_FAILED",
                "findings": safety_findings,
            }
            save_json_artifact(output_package, "repair_run.json", run_state)
            raise SystemExit("无障碍静态检测已通过，但结构安全检查未通过；本次模型修复不应采纳。")
        if not selected_issues:
            run_state["status"] = "stopped_non_repairable_errors"
            run_state["final_error_count"] = current_error_count
            run_state["repair_rate"] = repair_rate(
                run_state["initial_error_count"],
                current_error_count,
            )
            run_state["deferred_issues"] = deferred
            run_state["completed_round"] = round_num
            save_json_artifact(output_package, "repair_run.json", run_state)
            print(
                f"仍有 {current_error_count} 个 error，但没有可安全自动修改的 XML 修复项；"
                "已停止并保留人工复核记录。"
            )
            return

        base_prompt = build_android_repair_prompt(
            selected_issues,
            output_res,
            args.limit,
            use_rag=use_rag,
            repairability_filtering=repairability_filtering,
        )
        validate_model_configuration(args.provider, args.api_key)
        prompt = base_prompt
        accepted = None
        last_response = ""
        for attempt in range(1, args.max_model_attempts + 1):
            save_round_artifact(
                output_package,
                f"repair_prompt_round_{round_num}_attempt_{attempt}.txt",
                prompt,
            )
            print(
                f"调用模型修复中（第 {round_num} 轮，尝试 {attempt}/"
                f"{args.max_model_attempts}）..."
            )
            attempt_state = {"attempt": attempt}
            round_state["attempts"].append(attempt_state)
            try:
                model_result = run_model_with_metadata(
                    args.provider,
                    args.model,
                    prompt,
                    args.api_key,
                )
                model_output = model_result["content"]
                attempt_state["model_call"] = model_result["metadata"]
            except ModelError as exc:
                failed_call = model_error_metadata(
                    exc, args.provider, args.model
                )
                attempt_state.update({
                    "status": "model_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "model_call": failed_call,
                })
                run_state["status"] = "failed"
                run_state["failure"] = {
                    "code": "MODEL_PROVIDER_ERROR",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "model_call": failed_call,
                }
                save_json_artifact(output_package, "repair_run.json", run_state)
                raise SystemExit(f"模型调用失败: {exc}") from exc

            last_response = model_output
            save_round_artifact(
                output_package,
                f"model_response_round_{round_num}_attempt_{attempt}.txt",
                model_output,
            )
            try:
                changed, candidate_issues = evaluate_and_commit_candidate(
                    output_package,
                    input_res,
                    issues,
                    model_output,
                    detector_profile=args.detector_profile,
                )
                attempt_state.update({
                    "status": "accepted",
                    "after_quality": list(issue_quality(candidate_issues)),
                    "after_error_count": error_count(candidate_issues),
                    "changed_files": [
                        path.relative_to(output_package).as_posix()
                        for path in changed
                    ],
                })
                accepted = (changed, model_output)
                break
            except (ValueError, ET.ParseError) as exc:
                attempt_state.update({
                    "status": "rejected",
                    "error": str(exc),
                })
                save_round_artifact(
                    output_package,
                    f"operation_error_round_{round_num}_attempt_{attempt}.txt",
                    str(exc) + "\n",
                )
                if attempt < args.max_model_attempts:
                    prompt = build_operation_retry_prompt(
                        base_prompt,
                        model_output,
                        str(exc),
                    )

        if accepted is None:
            no_improvement_rounds = update_no_improvement_streak(
                current_error_count,
                current_error_count,
                no_improvement_rounds,
            )
            round_state["after_error_count"] = current_error_count
            round_state["no_improvement_streak"] = no_improvement_rounds
            if no_improvement_rounds >= 2:
                run_state["status"] = "no_improvement"
                run_state["stop_reason"] = "no_improvement"
                run_state["final_error_count"] = current_error_count
                run_state["repair_rate"] = repair_rate(
                    run_state["initial_error_count"],
                    current_error_count,
                )
                run_state["completed_round"] = round_num
                save_json_artifact(output_package, "repair_run.json", run_state)
                print("连续两轮 error_count 没有下降，已按 no_improvement 停止。")
                return
            save_json_artifact(output_package, "repair_run.json", run_state)
            print(
                f"第 {round_num} 轮未降低 error_count，"
                "将保留原 XML 并进入下一轮。"
            )
            continue

        changed, accepted_response = accepted
        accepted_issues = run_xml_checker(
            output_res,
            detector_profile=args.detector_profile,
        )
        accepted_error_count = error_count(accepted_issues)
        no_improvement_rounds = update_no_improvement_streak(
            current_error_count,
            accepted_error_count,
            no_improvement_rounds,
        )
        round_state["after_error_count"] = accepted_error_count
        round_state["no_improvement_streak"] = no_improvement_rounds
        save_round_artifact(
            output_package,
            f"repair_prompt_round_{round_num}.txt",
            base_prompt,
        )
        save_round_artifact(
            output_package,
            f"model_response_round_{round_num}.txt",
            accepted_response,
        )
        save_json_artifact(output_package, "repair_run.json", run_state)
        print("已写入模型修复文件:")
        for path in changed:
            print(f"- {path.relative_to(output_package)}")

    final_issues = run_xml_checker(
        output_res,
        detector_profile=args.detector_profile,
    )
    save_report(output_package, final_issues)
    final_safety_findings = validate_repair_safety(input_res, output_res)
    save_safety_report(output_package, final_safety_findings)
    final_actionable = actionable_issues(
        final_issues, repairability_filtering
    )
    final_error_count = error_count(final_issues)
    if final_error_count == 0 and not final_safety_findings:
        run_state["status"] = (
            "completed" if not final_issues else "completed_with_observations"
        )
        run_state["final_issue_quality"] = list(issue_quality(final_issues))
        run_state["final_error_count"] = 0
        run_state["repair_rate"] = repair_rate(run_state["initial_error_count"], 0)
        run_state["final_repairability"] = repairability_counts(final_issues)
        run_state["deferred_issues"] = non_actionable_issues(
            final_issues, repairability_filtering
        )
        save_json_artifact(output_package, "repair_run.json", run_state)
        if final_issues:
            print(
                "所有 XML 安全可自动修复的问题均已处理；"
                f"仍有 {len(final_issues)} 个问题需要人工、结构或运行时代码处理。"
            )
        else:
            print("Android XML 静态检测通过。")
        return
    run_state["status"] = "max_iterations"
    run_state["stop_reason"] = "max_iterations"
    run_state["final_issue_quality"] = list(issue_quality(final_issues))
    run_state["final_error_count"] = final_error_count
    run_state["repair_rate"] = repair_rate(
        run_state["initial_error_count"],
        final_error_count,
    )
    run_state["failure"] = {
        "code": "MAX_ROUNDS_REACHED",
        "remaining_error_count": final_error_count,
        "remaining_total_issue_count": len(final_issues),
        "remaining_repairable_issues": len(final_actionable),
        "remaining_safety_findings": len(final_safety_findings),
    }
    save_json_artifact(output_package, "repair_run.json", run_state)
    print(
        f"已达到最大轮数，剩余 error_count: {final_error_count}，"
        f"结构安全问题数: {len(final_safety_findings)}。"
    )


if __name__ == "__main__":
    try:
        main()
    except ModelError as exc:
        print(f"模型配置或调用失败: {exc}", file=sys.stderr)
        sys.exit(1)
