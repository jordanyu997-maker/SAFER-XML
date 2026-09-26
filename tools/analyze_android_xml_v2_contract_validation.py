#!/usr/bin/env python3
"""Analyze the pre-registered V2.1 Development contract validation."""
import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.analyze_android_xml_v2_rag_development import (  # noqa: E402
    load_rows,
    paired_comparison,
    sha256_file,
    summarize_condition,
    validate_matrix,
)
from tools.generate_android_xml import extract_json_object  # noqa: E402


DEFAULT_ROOT = ROOT / "experiments/android_xml_v2_rag/contract_v2_1"
DEFAULT_MATRIX = DEFAULT_ROOT / "matrix"
PROTOCOL_PATH = DEFAULT_ROOT / "protocol_v2_1.json"
STRATEGY_FIELDS = (
    "candidate_id",
    "task_id",
    "group",
    "preferred_strategy",
    "preferred_strategy_selected",
    "matched_operation_index",
    "operation_parse_valid",
    "model_response_path",
    "notes",
)


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def operation_matches(actual: dict, expected: dict) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def strategy_rows(matrix: Path, protocol: dict) -> list[dict]:
    rows = []
    for target in protocol["contract_correction_targets"]:
        for group in protocol["execution"]["groups"]:
            response_path = (
                matrix
                / "runs"
                / target["task_id"]
                / group
                / "reports/model_response.txt"
            )
            item = {
                "candidate_id": target["candidate_id"],
                "task_id": target["task_id"],
                "group": group,
                "preferred_strategy": target["preferred_strategy"],
                "preferred_strategy_selected": False,
                "matched_operation_index": "",
                "operation_parse_valid": False,
                "model_response_path": str(response_path.resolve()),
                "notes": "",
            }
            if not response_path.is_file():
                item["notes"] = "model response missing"
                rows.append(item)
                continue
            try:
                payload = extract_json_object(
                    response_path.read_text(encoding="utf-8")
                )
                operations = payload.get("operations", [])
                if not isinstance(operations, list):
                    raise ValueError("operations is not a list")
                item["operation_parse_valid"] = True
                matched = [
                    index
                    for index, operation in enumerate(operations)
                    if isinstance(operation, dict)
                    and operation_matches(
                        operation,
                        target["expected_operation"],
                    )
                ]
                if matched:
                    item["preferred_strategy_selected"] = True
                    item["matched_operation_index"] = matched[0]
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                item["notes"] = str(exc)
            rows.append(item)
    return rows


def strategy_summary(rows: list[dict], groups: list[str]) -> dict:
    result = {}
    for group in groups:
        group_rows = [row for row in rows if row["group"] == group]
        count = sum(
            bool(row["preferred_strategy_selected"])
            for row in group_rows
        )
        result[group] = {
            "target_count": len(group_rows),
            "preferred_strategy_count": count,
            "preferred_strategy_rate": (
                count / len(group_rows) if group_rows else 0.0
            ),
            "parse_failure_count": sum(
                not bool(row["operation_parse_valid"])
                for row in group_rows
            ),
        }
    return result


def contribution_classification(
    condition_summaries: dict,
    strategy_summaries: dict,
) -> str:
    no_rag_rate = condition_summaries["no_rag"]["candidate_repair_rate"]
    rag_rate = condition_summaries["rag_topk2"]["candidate_repair_rate"]
    if rag_rate > no_rag_rate:
        return "limited_repair_contribution"
    no_rag_strategy = strategy_summaries["no_rag"][
        "preferred_strategy_rate"
    ]
    rag_strategy = strategy_summaries["rag_topk2"][
        "preferred_strategy_rate"
    ]
    if rag_strategy > no_rag_strategy:
        return "decision_quality_contribution"
    return "no_measurable_rag_contribution"


def report_markdown(analysis: dict) -> str:
    condition = analysis["condition_summaries"]
    strategy = analysis["preferred_strategy_summaries"]
    classification = analysis["rag_contribution_classification"]
    return "\n".join([
        "# V2.1 Development 契约一致性复验报告",
        "",
        "## 完整性",
        "",
        f"- 模型调用：{analysis['condition_run_count']} / 38；",
        f"- 基础设施失败：{analysis['infrastructure_failure_count']}；",
        "- 数据范围：仅冻结 Development；",
        "- Test 集未读取、未运行；",
        "- 检测器、知识库、检索算法与 Top-2 均未改变。",
        "",
        "## 修复结果",
        "",
        "| 条件 | 修复问题 | 候选修复率 | 完全修复任务 | 总 Token |",
        "|---|---:|---:|---:|---:|",
        *[
            (
                f"| {group} | {item['candidate_repaired']}/"
                f"{item['candidate_before']} | "
                f"{item['candidate_repair_rate']:.1%} | "
                f"{item['complete_task_count']}/{item['task_count']} | "
                f"{item['total_tokens']} |"
            )
            for group, item in condition.items()
        ],
        "",
        "## 预注册策略指标",
        "",
        "| 条件 | 正确标签关联策略 | 策略率 | 解析失败 |",
        "|---|---:|---:|---:|",
        *[
            (
                f"| {group} | {item['preferred_strategy_count']}/"
                f"{item['target_count']} | "
                f"{item['preferred_strategy_rate']:.1%} | "
                f"{item['parse_failure_count']} |"
            )
            for group, item in strategy.items()
        ],
        "",
        "## 判定",
        "",
        f"- 预注册判定：`{classification}`；",
        "- 本轮结束后停止继续根据 Development 结果调参；",
        "- 只有冻结指标支持时，才把 RAG 写成可测量贡献。",
        "",
    ])


def analyze(matrix: Path, protocol: dict) -> dict:
    result_path = matrix / "development_results.csv"
    result_rows = load_rows(result_path)
    groups = tuple(protocol["execution"]["groups"])
    validate_matrix(result_rows, groups)
    grouped = {
        group: [row for row in result_rows if row["group"] == group]
        for group in groups
    }
    condition_summaries = {
        group: summarize_condition(rows)
        for group, rows in grouped.items()
    }
    preferred_rows = strategy_rows(matrix, protocol)
    preferred_summaries = strategy_summary(
        preferred_rows,
        list(groups),
    )
    analysis = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "analysis_scope": "development_only",
        "test_set_loaded": False,
        "condition_run_count": len(result_rows),
        "infrastructure_failure_count": sum(
            row["status"] == "infrastructure_failed"
            for row in result_rows
        ),
        "condition_summaries": condition_summaries,
        "paired_vs_no_rag": paired_comparison(
            grouped["no_rag"],
            grouped["rag_topk2"],
        ),
        "preferred_strategy_summaries": preferred_summaries,
        "rag_contribution_classification": contribution_classification(
            condition_summaries,
            preferred_summaries,
        ),
        "stopping_rule_applied": True,
        "results_sha256": sha256_file(result_path),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
    }
    return analysis, preferred_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    analysis, preferred_rows = analyze(args.matrix, protocol)
    args.output.mkdir(parents=True, exist_ok=True)
    analysis_path = args.output / "contract_v2_1_analysis.json"
    strategy_path = args.output / "preferred_strategy_results.csv"
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(strategy_path, preferred_rows, STRATEGY_FIELDS)
    (args.output / "CONTRACT_V2_1_RESULTS_ZH.md").write_text(
        report_markdown(analysis),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "analyzed",
        "rag_contribution_classification": (
            analysis["rag_contribution_classification"]
        ),
        "test_set_loaded": False,
        "analysis": str(analysis_path.resolve()),
        "preferred_strategy_results": str(strategy_path.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
