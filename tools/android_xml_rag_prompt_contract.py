#!/usr/bin/env python3
"""Equal-budget prompt contract for an isolated Android XML RAG comparison."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET


KNOWLEDGE_START = "<retrieved_knowledge>"
KNOWLEDGE_END = "</retrieved_knowledge>"
NO_RAG_MARKER = "No external accessibility document is provided in this condition."


from tools.generate_android_xml import (  # noqa: E402
    ANDROID_NS,
    find_by_selector,
    format_files,
    issue_files,
    path_inside,
    tag_local_name,
)
from tools.evaluation.android_xml_a11y_check import (  # noqa: E402
    build_parent_map,
    build_stack,
    element_path,
    is_weak_input_name,
    load_string_resources,
    resolve_string,
)
from tools.retrieval.build_rag_prompt import format_document  # noqa: E402
from tools.retrieval.v2_hybrid import (  # noqa: E402
    HashedSubwordVectorBackend,
    retrieve_for_issues,
)


def neutral_issue_query(issue):
    attributes = issue.get("attributes", {})
    attribute_text = " ".join(
        f"{name}={value}" for name, value in sorted(attributes.items())
    )
    parts = [
        "Android XML accessibility",
        issue.get("code", ""),
        issue.get("component", "") or issue.get("element", ""),
        issue.get("selector", ""),
        attribute_text,
        issue.get("message", ""),
        issue.get("repair_query", ""),
    ]
    return " ".join(str(part) for part in parts if part)


def android_attr(element, name):
    return element.attrib.get(f"{{{ANDROID_NS}}}{name}", "")


def existing_id_reference(value):
    value = str(value or "")
    if value.startswith("@+id/"):
        return "@id/" + value.split("/", 1)[1]
    return value if value.startswith("@id/") else ""


def related_label_element(issue):
    """Return one nearby visible TextView that can safely own labelFor."""
    if issue.get("code") not in {
        "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
        "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
        "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
    }:
        return None
    file_path = Path(issue.get("file", ""))
    selector = issue.get("selector", "")
    if not file_path.is_file() or not selector:
        return None
    try:
        root = ET.fromstring(file_path.read_text(encoding="utf-8"))
        target = find_by_selector(root, selector)
    except (ET.ParseError, ValueError, OSError):
        return None
    target_reference = existing_id_reference(android_attr(target, "id"))
    if not target_reference:
        return None
    parent_map = build_parent_map(root)
    parent = parent_map.get(target)
    if parent is None:
        return None
    resources = load_string_resources([file_path])

    def candidate_record(candidate, relationship):
        if not tag_local_name(candidate.tag).endswith("TextView"):
            return None
        if android_attr(candidate, "visibility") in {"gone", "invisible"}:
            return None
        visible_text = android_attr(candidate, "text") or android_attr(
            candidate, "contentDescription"
        )
        if not visible_text or android_attr(candidate, "labelFor"):
            return None
        resolved_text = resolve_string(visible_text, resources)
        if not resolved_text or is_weak_input_name(resolved_text):
            return None
        return {
            "component": tag_local_name(candidate.tag),
            "selector": element_path(build_stack(candidate, parent_map)),
            "observed_attributes": {
                key: value
                for key, value in {
                    "text": android_attr(candidate, "text"),
                    "contentDescription": android_attr(
                        candidate, "contentDescription"
                    ),
                }.items()
                if value
            },
            "relationship": relationship,
            "allowed_attribute": "android:labelFor",
            "required_value": target_reference,
        }

    def ordered_siblings(container, anchor):
        siblings = list(container)
        index = siblings.index(anchor)
        return list(reversed(siblings[:index])) + siblings[index + 1:]

    for candidate in ordered_siblings(parent, target):
        record = candidate_record(candidate, "nearby_visible_label_candidate")
        if record:
            return record

    grandparent = parent_map.get(parent)
    if grandparent is not None:
        for candidate in ordered_siblings(grandparent, parent):
            record = candidate_record(
                candidate,
                "adjacent_container_visible_label_candidate",
            )
            if record:
                return record

        great_grandparent = parent_map.get(grandparent)
        if great_grandparent is not None:
            records = [
                record
                for candidate in ordered_siblings(great_grandparent, grandparent)
                if (
                    record := candidate_record(
                        candidate,
                        "nested_container_visible_label_candidate",
                    )
                )
            ]
            if len(records) == 1:
                return records[0]
    return None


def related_text_input_layout_element(issue):
    """Expose the nearest ancestor TextInputLayout as a bounded hint target."""
    if issue.get("code") not in {
        "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
        "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
    }:
        return None
    file_path = Path(issue.get("file", ""))
    selector = issue.get("selector", "")
    if not file_path.is_file() or not selector:
        return None
    try:
        root = ET.fromstring(file_path.read_text(encoding="utf-8"))
        target = find_by_selector(root, selector)
    except (ET.ParseError, ValueError, OSError):
        return None
    parent_map = build_parent_map(root)
    ancestor = parent_map.get(target)
    while ancestor is not None:
        if tag_local_name(ancestor.tag).endswith("TextInputLayout"):
            if android_attr(ancestor, "hint"):
                return None
            return {
                "component": tag_local_name(ancestor.tag),
                "selector": element_path(build_stack(ancestor, parent_map)),
                "observed_attributes": {
                    key: value
                    for key, value in {
                        "id": android_attr(ancestor, "id"),
                    }.items()
                    if value
                },
                "relationship": "ancestor_text_input_layout",
                "allowed_attribute": "android:hint",
                "allowed_value_kind": (
                    "existing_or_added_nonweak_string_resource"
                ),
            }
        ancestor = parent_map.get(ancestor)
    return None


def format_neutral_issues(issues, res_dir):
    records = []
    for issue in issues:
        file_value = issue.get("file", "")
        relative = path_inside(Path(file_value), res_dir) if file_value else None
        record = {
            "issue_code": issue.get("code"),
            "file": relative.as_posix() if relative else file_value,
            "component": issue.get("component") or issue.get("element"),
            "selector": issue.get("selector"),
            "severity": issue.get("severity", "error"),
            "repairability": issue.get("repairability", "xml_safe"),
            "observed_attributes": issue.get("attributes", {}),
        }
        related = [
            item for item in (
                related_label_element(issue),
                related_text_input_layout_element(issue),
            )
            if item
        ]
        if related:
            record["related_elements"] = related
        records.append(record)
    return json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True)


def compact_trace(results):
    return [
        {
            "doc_id": result.get("doc_id"),
            "reason": result.get("reason"),
            "lexical_score": result.get("lexical_score"),
            "dense_score": result.get("dense_score"),
            "hybrid_score": result.get("hybrid_score"),
            "metadata": result.get("metadata"),
            "issue_index": result.get("issue_index"),
            "issue_code": result.get("issue_code"),
        }
        for result in results
    ]


def build_shared_prompt(issues, res_dir, knowledge_text):
    files = issue_files(issues, res_dir)
    return f"""You are repairing high-confidence accessibility defects in Android XML resources.

Use the issue evidence, current XML resources, and any retrieved knowledge below. Preserve app behavior, element types, ids, styles, dimensions, hierarchy, include tags, input restrictions, and existing resource references. Make only the smallest necessary change. Do not suppress a finding merely to make the detector pass.

The retrieved-knowledge block is the only experimental difference between the No-RAG and RAG conditions.

{KNOWLEDGE_START}
{knowledge_text}
{KNOWLEDGE_END}

Structured detector evidence:

{format_neutral_issues(issues, res_dir)}

Current XML resources:

{format_files(files, res_dir)}

Return only one strict JSON object with an `operations` array. Each element-targeting operation must use an exact file path and an exact selector from either `selector` or `related_elements[].selector` in the evidence. A related label element may only receive its declared `allowed_attribute` and `required_value`. Never add, remove, or change android:id. For labelFor, reference an existing target as `@id/name`, never `@+id/name`. Allowed operations are `remove_attribute`, `set_attribute`, `remove_attribute_value`, and `add_string_resource`. `add_string_resource` must target the existing default string-resource XML shown in the resources when one is present; otherwise use `res/values/strings.xml` and the executor will safely route or create a dedicated resource file. It must use `name` and `value`, and it must not contain `selector`, `attribute`, `key`, `resource_name`, or `resource_value`. Do not output complete XML files, delete files, delete resources, replace layouts, or modify unrelated elements.

Operation schemas:
{{
  "operations": [
    {{
      "op": "set_attribute",
      "path": "res/layout/FILE.xml",
      "selector": "/EXACT/SELECTOR[1]",
      "attribute": "android:ATTRIBUTE_NAME",
      "value": "VALUE"
    }},
    {{
      "op": "remove_attribute",
      "path": "res/layout/FILE.xml",
      "selector": "/EXACT/SELECTOR[1]",
      "attribute": "android:ATTRIBUTE_NAME"
    }},
    {{
      "op": "remove_attribute_value",
      "path": "res/layout/FILE.xml",
      "selector": "/EXACT/SELECTOR[1]",
      "attribute": "tools:ignore",
      "value": "ATTRIBUTE_VALUE_TO_REMOVE"
    }},
    {{
      "op": "add_string_resource",
      "path": "res/values/strings.xml",
      "name": "resource_name",
      "value": "Localized accessible text"
    }}
  ]
}}
"""


def build_prompt_pair(
    issues,
    res_dir,
    documents,
    per_issue_limit=3,
    prompt_limit=6,
):
    effective_per_issue_limit = min(max(int(per_issue_limit), 1), 8)
    effective_prompt_limit = min(max(int(prompt_limit), 1), 8)
    dense_backend = HashedSubwordVectorBackend()
    results = retrieve_for_issues(
        issues,
        documents,
        per_issue_limit=effective_per_issue_limit,
        prompt_limit=effective_prompt_limit,
        direct_limit=2,
        candidate_limit=20,
        dense_backend=dense_backend,
        lexical_weight=0.65,
        query_builder=neutral_issue_query,
    )
    rag_text = (
        "\n\n".join(format_document(result["document"]) for result in results)
        if results
        else "No sufficiently relevant Android XML document was retrieved."
    )
    return {
        "no_rag": build_shared_prompt(issues, res_dir, NO_RAG_MARKER),
        "rag": build_shared_prompt(issues, res_dir, rag_text),
        "trace": {
            "retrieval_contract_version": "v4_structured_hybrid",
            "direct_detector_mapping_enabled": True,
            "query_includes_message": True,
            "query_includes_repair_query": True,
            "app_context_retrieval_enabled": False,
            "dense_backend": dense_backend.backend_id,
            "requested_per_issue_limit": int(per_issue_limit),
            "effective_per_issue_limit": effective_per_issue_limit,
            "requested_prompt_limit": int(prompt_limit),
            "effective_prompt_limit": effective_prompt_limit,
            "knowledge_documents": compact_trace(results),
            "knowledge_document_count": len(results),
            "knowledge_injected_characters": len(rag_text),
        },
    }


def prompt_skeleton(prompt):
    before, separator, remainder = prompt.partition(KNOWLEDGE_START)
    if not separator:
        raise ValueError("Prompt does not contain the knowledge start marker")
    _, separator, after = remainder.partition(KNOWLEDGE_END)
    if not separator:
        raise ValueError("Prompt does not contain the knowledge end marker")
    return before + KNOWLEDGE_START + "\n<CONDITION_CONTENT>\n" + KNOWLEDGE_END + after


def audit_prompt_pair(pair, issues):
    failures = []
    if prompt_skeleton(pair["no_rag"]) != prompt_skeleton(pair["rag"]):
        failures.append("prompt_conditions_differ_outside_knowledge_block")
    for field in ("message", "repair_query", "fix_hint"):
        for issue in issues:
            value = str(issue.get(field, "")).strip()
            if value and value in format_neutral_issues([issue], Path(issue["file"]).parent):
                failures.append(f"neutral_issue_evidence_contains_{field}")
    if pair["trace"]["app_context_retrieval_enabled"]:
        failures.append("app_context_retrieval_enabled")
    return {
        "passed": not failures,
        "failures": failures,
        "conditions_differ_only_in_knowledge_block": not failures,
    }
