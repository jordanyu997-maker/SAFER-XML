#!/usr/bin/env python3
"""Versioned V2.1 XML operation extension for Development validation."""
import json
import shutil
import tempfile
from pathlib import Path

from tools import generate_android_xml as base


CONTRACT_VERSION = "android_xml_operation_contract_v2_1"


def is_supported_radio_button_label_for_failure(
    output_package: Path,
    operation: dict,
    error: ValueError,
) -> bool:
    if (
        operation.get("op") != "set_attribute"
        or operation.get("attribute") != "android:labelFor"
        or "目标不是受支持的输入或选择控件" not in str(error)
    ):
        return False
    target = base.safe_target(output_package, operation["path"])
    text = target.read_text(encoding="utf-8")
    label = base.selector_target_element(text, operation["selector"])
    if not base.tag_local_name(label.tag).endswith("TextView"):
        return False
    target_id = str(operation.get("value", "")).removeprefix("@id/")
    referenced = next(
        (
            element
            for element in base.ET.fromstring(text).iter()
            if base.resource_id_name(
                element.attrib.get(f"{{{base.ANDROID_NS}}}id", "")
            )
            == target_id
        ),
        None,
    )
    return (
        referenced is not None
        and base.tag_local_name(referenced.tag).endswith("RadioButton")
    )


def validate_model_operations(output_package: Path, model_output: str):
    try:
        data = base.extract_json_object(model_output)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"模型输出不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"operations"}:
        raise ValueError("模型输出顶层必须且只能包含 operations。")
    operations = data.get("operations")
    if not isinstance(operations, list):
        raise ValueError("模型输出 JSON 缺少 operations 数组。")
    if not operations:
        raise ValueError("模型返回了空 operations，无法改善当前问题。")
    if len(operations) > base.MAX_OPERATIONS_PER_RESPONSE:
        raise ValueError(
            f"单次模型响应最多允许 {base.MAX_OPERATIONS_PER_RESPONSE} 个 operations。"
        )

    validated = []
    for index, operation in enumerate(operations):
        try:
            validated.append(
                base.validate_operation(output_package, operation, index)
            )
        except ValueError as exc:
            if not is_supported_radio_button_label_for_failure(
                output_package,
                operation,
                exc,
            ):
                raise
            target = base.safe_target(output_package, operation["path"])
            normalized = dict(operation)
            normalized["path"] = target.relative_to(
                output_package.resolve()
            ).as_posix()
            normalized["attribute"] = base.canonical_attribute_name(
                operation["attribute"]
            )
            validated.append(normalized)
    return validated


def apply_model_result(output_package: Path, model_output: str):
    operations = validate_model_operations(output_package, model_output)
    target_paths = {
        base.safe_target(output_package, item["path"])
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
                changed.append(
                    base.apply_attribute_operation(output_package, item, op)
                )
            elif op == "remove_attribute_value":
                changed.append(
                    base.apply_remove_attribute_value(output_package, item)
                )
            else:
                changed.append(
                    base.apply_add_string_resource(output_package, item)
                )
        changed = sorted(set(changed))
        base.validate_xml_files(changed)
        if all(
            snapshots[path] is not None
            and path.read_bytes() == snapshots[path]
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


def evaluate_and_commit_candidate(
    output_package: Path,
    input_res: Path,
    current_issues,
    model_output: str,
    detector_profile: str = base.DEFAULT_DETECTOR_PROFILE,
):
    with tempfile.TemporaryDirectory(
        prefix="android_xml_candidate_v2_1_",
        dir=str(output_package.parent),
    ) as temp:
        candidate_package = Path(temp) / "package"
        shutil.copytree(output_package, candidate_package)
        changed = apply_model_result(candidate_package, model_output)
        candidate_res = candidate_package / "res"
        candidate_issues = base.run_xml_checker(
            candidate_res,
            detector_profile=detector_profile,
        )
        candidate_safety = base.validate_repair_safety(input_res, candidate_res)
        if candidate_safety:
            codes = ", ".join(
                finding.get("code", "UNKNOWN")
                for finding in candidate_safety
            )
            raise ValueError(f"候选修复未通过结构安全检查: {codes}")

        before_quality = base.issue_quality(current_issues)
        after_quality = base.issue_quality(candidate_issues)
        if base.error_count(candidate_issues) >= base.error_count(current_issues):
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
