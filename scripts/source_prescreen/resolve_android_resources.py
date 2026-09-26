#!/usr/bin/env python3
"""Resolve the Android resources needed by XML source prescreening."""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.source_prescreen.common import sha256_text  # noqa: E402
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    ANDROID_NS,
    load_dimension_resources,
    load_string_resources,
    load_style_resources,
    parse_id,
    resolve_dimension,
    resolve_string,
    strip_ns,
)


RESOURCE_REF_RE = re.compile(r"^@(?:\+)?([A-Za-z0-9_]+)/([A-Za-z0-9_.]+)$")
REQUIRED_RESOURCE_TYPES = {"string", "dimen", "style", "layout", "id"}
TAG_RE_TEMPLATE = r"<\s*{tag}(?:\s|/?>)"


def discover_layout_files(repository: Path, subdir: str = "") -> list[Path]:
    base = repository / subdir if subdir else repository
    if not base.exists():
        return []
    return sorted(
        path for path in base.rglob("*.xml")
        if path.parent.name.startswith("layout")
        and "build" not in path.parts
        and ".gradle" not in path.parts
        and ".git" not in path.parts
    )


def discover_res_roots(repository: Path, subdir: str = "") -> list[Path]:
    return sorted({
        path.parent.parent
        for path in discover_layout_files(repository, subdir)
        if path.parent.parent.name == "res"
    })


def _android_attr(element: ET.Element, name: str) -> str:
    return element.attrib.get(f"{{{ANDROID_NS}}}{name}", element.attrib.get(name, ""))


class AndroidResourceResolver:
    def __init__(self, repository: Path, subdir: str = ""):
        self.repository = repository.resolve()
        self.subdir = subdir
        self.res_roots = discover_res_roots(self.repository, subdir)
        self.strings = load_string_resources(self.res_roots)
        self.dimens = load_dimension_resources(self.res_roots)
        self.styles = load_style_resources(self.res_roots)
        self.layouts: dict[str, list[Path]] = defaultdict(list)
        self.ids: dict[str, list[Path]] = defaultdict(list)
        self.included_by: dict[str, list[str]] = defaultdict(list)
        self.parse_errors: list[str] = []
        self._index_layouts()

    def _index_layouts(self) -> None:
        for path in discover_layout_files(self.repository, self.subdir):
            relative = path.relative_to(self.repository).as_posix()
            self.layouts[path.stem].append(path)
            try:
                root = ET.parse(path).getroot()
            except (ET.ParseError, OSError) as exc:
                self.parse_errors.append(f"{relative}: {exc}")
                continue
            for element in root.iter():
                element_id = parse_id(_android_attr(element, "id"))
                if element_id:
                    self.ids[element_id].append(path)
                if strip_ns(element.tag) == "include":
                    layout_ref = element.attrib.get("layout", "")
                    match = RESOURCE_REF_RE.match(layout_ref)
                    if match and match.group(1) == "layout":
                        self.included_by[match.group(2)].append(relative)
        for res_root in self.res_roots:
            for values_file in res_root.rglob("*.xml"):
                if not values_file.parent.name.startswith("values"):
                    continue
                try:
                    root = ET.parse(values_file).getroot()
                except (ET.ParseError, OSError):
                    continue
                for item in root:
                    if strip_ns(item.tag) == "item" and item.attrib.get("type") == "id":
                        name = item.attrib.get("name")
                        if name:
                            self.ids[name].append(values_file)

    def resolve_value(self, value: str | None) -> tuple[object, str]:
        if value is None:
            return "", "missing"
        raw = str(value).strip()
        match = RESOURCE_REF_RE.match(raw)
        if not match:
            return raw, "literal"
        resource_type, name = match.groups()
        if resource_type == "string":
            resolved = resolve_string(raw, self.strings)
            return resolved, "resolved" if name in self.strings else "unresolved"
        if resource_type == "dimen":
            resolved, status = resolve_dimension(raw, self.dimens)
            return resolved if resolved is not None else raw, status
        if resource_type == "style":
            return self.styles.get(name, raw), "resolved" if name in self.styles else "unresolved"
        if resource_type == "layout":
            paths = [path.relative_to(self.repository).as_posix() for path in self.layouts.get(name, [])]
            return paths or raw, "resolved" if paths else "unresolved"
        if resource_type == "id":
            paths = [path.relative_to(self.repository).as_posix() for path in self.ids.get(name, [])]
            return paths or raw, "resolved" if paths else "unresolved"
        return raw, "unsupported"

    def resolve_attributes(self, attributes: dict) -> tuple[dict, list[str]]:
        resolved = {}
        unresolved = []
        for name, value in attributes.items():
            resolved_value, status = self.resolve_value(value)
            resolved[name] = {"raw": value, "value": resolved_value, "status": status}
            match = RESOURCE_REF_RE.match(str(value).strip())
            if (
                status in {"unresolved", "unresolved_resource"}
                and match
                and match.group(1) in REQUIRED_RESOURCE_TYPES
            ):
                unresolved.append(f"{name}={value}")
        style_ref = attributes.get("style", "")
        if style_ref.startswith("@style/"):
            style_name = style_ref.rsplit("/", 1)[-1]
            if style_name in self.styles:
                resolved["style_items"] = self.styles[style_name]
            else:
                unresolved.append(f"style={style_ref}")
        return resolved, sorted(set(unresolved))

    def context_for(self, xml_path: Path, selector: str) -> dict:
        return {
            "selector_ancestors": [part for part in selector.strip("/").split("/")[:-1] if part],
            "root_tag": root_tag(xml_path),
            "included_by": sorted(set(self.included_by.get(xml_path.stem, []))),
            "is_merge_layout": root_tag(xml_path) == "merge",
        }


def root_tag(path: Path) -> str:
    try:
        return strip_ns(ET.parse(path).getroot().tag)
    except (ET.ParseError, OSError):
        return ""


def line_number_for(path: Path, widget_id: str, element_name: str) -> int:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    if widget_id:
        clean_id = widget_id.rsplit("/", 1)[-1]
        for index, line in enumerate(lines, 1):
            if clean_id in line and ("@id/" in line or "@+id/" in line):
                return index
    tag = re.escape(element_name)
    pattern = re.compile(TAG_RE_TEMPLATE.format(tag=tag))
    for index, line in enumerate(lines, 1):
        if pattern.search(line):
            return index
    # Detector-normalized names may omit the package of a custom/AppCompat tag.
    simple_name = re.escape(str(element_name).rsplit(".", 1)[-1])
    suffix_pattern = re.compile(rf"<\s*(?:[A-Za-z_$][\w$]*\.)*{simple_name}(?:\s|/?>|$)")
    for index, line in enumerate(lines, 1):
        if suffix_pattern.search(line):
            return index
    return 0


def canonical_layout_signature(path: Path) -> str:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return sha256_text(path.read_text(encoding="utf-8", errors="replace") if path.exists() else "")

    def visit(element: ET.Element):
        attrs = []
        for key, value in sorted(element.attrib.items(), key=lambda item: strip_ns(item[0])):
            name = strip_ns(key)
            normalized = value
            if name == "id":
                normalized = "@id"
            elif value.startswith("@string/"):
                normalized = "@string"
            elif value.startswith("@drawable/") or value.startswith("@mipmap/"):
                normalized = "@image"
            elif value.startswith("@layout/"):
                normalized = "@layout"
            attrs.append((name, normalized))
        return [strip_ns(element.tag), attrs, [visit(child) for child in element]]

    return sha256_text(json.dumps(visit(root), ensure_ascii=True, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--subdir", default="")
    args = parser.parse_args()
    resolver = AndroidResourceResolver(args.repository, args.subdir)
    print(json.dumps({
        "repository": str(args.repository.resolve()),
        "res_roots": len(resolver.res_roots),
        "strings": len(resolver.strings),
        "dimens": len(resolver.dimens),
        "styles": len(resolver.styles),
        "layouts": sum(len(paths) for paths in resolver.layouts.values()),
        "ids": len(resolver.ids),
        "include_edges": sum(len(paths) for paths in resolver.included_by.values()),
        "parse_errors": resolver.parse_errors,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
