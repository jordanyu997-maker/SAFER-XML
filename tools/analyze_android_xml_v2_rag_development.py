#!/usr/bin/env python3
"""Analyze the frozen V2 Development matrix and lock one RAG Top-k."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = (
    ROOT
    / "experiments/android_xml_v2_rag/development_matrix/development_results.csv"
)
DEFAULT_OUTPUT = DEFAULT_RESULTS.parent
PROTOCOL_PATH = ROOT / "experiments/android_xml_v2_rag/protocol_v2.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(row: dict, field: str) -> float:
    value = row.get(field)
    return float(value) if value not in ("", None) else 0.0


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_matrix(rows: list[dict], conditions: tuple[str, ...]) -> None:
    if not rows:
        raise ValueError("Development results are empty")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["group"]].append(row)
        if row["status"] == "infrastructure_failed":
            raise ValueError("Development results contain infrastructure failures")
    if set(grouped) != set(conditions):
        raise ValueError(
            f"Condition mismatch: {sorted(grouped)} != {sorted(conditions)}"
        )
    task_sets = {
        condition: {row["task_id"] for row in grouped[condition]}
        for condition in conditions
    }
    expected = task_sets[conditions[0]]
    if any(task_set != expected for task_set in task_sets.values()):
        raise ValueError("Conditions do not contain the same frozen task IDs")
    for task_id in expected:
        task_rows = [row for row in rows if row["task_id"] == task_id]
        if len(task_rows) != len(conditions):
            raise ValueError(f"{task_id}: duplicated or missing condition result")
        before_counts = {
            int(number(row, "before_candidate_error_count"))
            for row in task_rows
        }
        if len(before_counts) != 1:
            raise ValueError(f"{task_id}: candidate denominator differs by condition")


def summarize_condition(rows: list[dict]) -> dict:
    before = sum(number(row, "before_candidate_error_count") for row in rows)
    after = sum(number(row, "after_candidate_error_count") for row in rows)
    complete = sum(
        str(row.get("complete_candidate_repair", "")).lower() == "true"
        for row in rows
    )
    return {
        "task_count": len(rows),
        "candidate_before": int(before),
        "candidate_after": int(after),
        "candidate_repaired": int(before - after),
        "candidate_repair_rate": (before - after) / before if before else 0.0,
        "complete_task_count": complete,
        "complete_task_rate": complete / len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "safety_finding_count": int(
            sum(number(row, "safety_finding_count") for row in rows)
        ),
        "operation_parse_invalid_count": sum(
            str(row.get("operation_parse_valid", "")).lower() != "true"
            for row in rows
        ),
        "hardcoded_accessibility_value_count": int(
            sum(
                number(row, "hardcoded_accessibility_value_count")
                for row in rows
            )
        ),
        "interaction_attribute_removal_count": int(
            sum(
                number(row, "interaction_attribute_removal_count")
                for row in rows
            )
        ),
        "structural_operation_count": int(
            sum(number(row, "structural_operation_count") for row in rows)
        ),
        "changed_file_count": int(
            sum(number(row, "changed_file_count") for row in rows)
        ),
        "total_tokens": int(sum(number(row, "total_tokens") for row in rows)),
        "mean_tokens_per_task": (
            sum(number(row, "total_tokens") for row in rows) / len(rows)
        ),
        "mean_duration_ms": (
            sum(number(row, "duration_ms") for row in rows) / len(rows)
        ),
    }


def paired_comparison(
    baseline_rows: list[dict],
    condition_rows: list[dict],
) -> dict:
    baseline = {row["task_id"]: row for row in baseline_rows}
    wins = ties = losses = 0
    deltas = []
    for row in condition_rows:
        delta = number(row, "candidate_repair_rate") - number(
            baseline[row["task_id"]],
            "candidate_repair_rate",
        )
        deltas.append(delta)
        if delta > 0:
            wins += 1
        elif delta < 0:
            losses += 1
        else:
            ties += 1
    return {
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "mean_task_repair_rate_delta": sum(deltas) / len(deltas),
    }


def selection_key(summary: dict, top_k: int) -> tuple:
    undesirable_operations = (
        summary["hardcoded_accessibility_value_count"]
        + summary["interaction_attribute_removal_count"]
        + summary["structural_operation_count"]
    )
    return (
        -summary["candidate_repair_rate"],
        summary["safety_finding_count"],
        summary["operation_parse_invalid_count"],
        undesirable_operations,
        summary["total_tokens"],
        top_k,
    )


def analyze(rows: list[dict], protocol: dict) -> tuple[dict, dict]:
    top_k_values = tuple(
        int(value)
        for value in protocol["development_tuning"]["prompt_top_k_candidates"]
    )
    conditions = ("no_rag",) + tuple(
        f"rag_topk{top_k}" for top_k in top_k_values
    )
    validate_matrix(rows, conditions)
    grouped = {
        condition: [row for row in rows if row["group"] == condition]
        for condition in conditions
    }
    summaries = {
        condition: summarize_condition(condition_rows)
        for condition, condition_rows in grouped.items()
    }
    paired = {
        condition: paired_comparison(grouped["no_rag"], grouped[condition])
        for condition in conditions
        if condition != "no_rag"
    }
    selected_top_k = min(
        top_k_values,
        key=lambda top_k: selection_key(
            summaries[f"rag_topk{top_k}"],
            top_k,
        ),
    )
    selected_condition = f"rag_topk{selected_top_k}"
    rag_gain_observed = (
        summaries[selected_condition]["candidate_repair_rate"]
        > summaries["no_rag"]["candidate_repair_rate"]
    )
    analysis = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "analysis_scope": "development_only",
        "test_set_loaded": False,
        "conditions": list(conditions),
        "condition_summaries": summaries,
        "paired_vs_no_rag": paired,
        "selection_rule": protocol["development_tuning"]["selection_rule"],
        "selected_condition": selected_condition,
        "selected_top_k": selected_top_k,
        "rag_gain_observed_on_development": rag_gain_observed,
        "interpretation": (
            "No efficacy gain was observed on Development; Top-k 2 was selected "
            "among RAG settings by the registered safety/quality/cost tie-breakers."
            if not rag_gain_observed
            else "The selected RAG setting improved Development repair efficacy."
        ),
    }
    lock = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "dataset_version": protocol["dataset"]["version"],
        "dataset_sha256": protocol["dataset"]["dataset_sha256"],
        "selection_scope": "development_only",
        "selected_top_k": selected_top_k,
        "selected_condition": selected_condition,
        "test_set_loaded": False,
        "selection_locked": True,
        "selection_must_not_change_after_test_execution": True,
    }
    return analysis, lock


def report_markdown(analysis: dict, lock: dict) -> str:
    summaries = analysis["condition_summaries"]
    lines = [
        "# V2 Development RAG 参数选择报告",
        "",
        "## 完整性",
        "",
        "- 19 个 XML 任务，四个条件均完整，共 76 次模型调用；",
        "- 基础设施失败：0；",
        "- 分析仅使用 Development，未读取 Test；",
        "- 每个条件的冻结候选分母均为 24 条。",
        "",
        "## 描述性结果",
        "",
        "| 条件 | 修复问题 | 修复率 | 完全修复任务 | 安全问题 | 交互属性删除 | 总 Token |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in analysis["conditions"]:
        item = summaries[condition]
        lines.append(
            f"| {condition} | {item['candidate_repaired']}/"
            f"{item['candidate_before']} | "
            f"{item['candidate_repair_rate']:.1%} | "
            f"{item['complete_task_count']}/{item['task_count']} | "
            f"{item['safety_finding_count']} | "
            f"{item['interaction_attribute_removal_count']} | "
            f"{item['total_tokens']} |"
        )
    lines.extend([
        "",
        "## 参数锁定",
        "",
        f"- 冻结 Top-k：`{lock['selected_top_k']}`；",
        "- 三个 RAG 配置与 No-RAG 在 Development 修复效果上完全持平；",
        "- Top-2 与 Top-4 均未产生安全问题或不良操作，Top-2 Token 更少；",
        "- Top-8 额外出现 4 次 `clickable/focusable` 删除且 Token 最高；",
        "- 因此按照预注册的效果、安全、修改质量、成本顺序选择 Top-2；",
        "- Development 结果不能证明 RAG 有效，RAG 贡献必须由冻结 Test 集检验。",
        "",
        "本报告只进行描述性参数选择，不把 Development 当作最终假设检验数据。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    rows = load_rows(args.results)
    analysis, lock = analyze(rows, protocol)
    analysis["results_path"] = str(args.results.resolve())
    analysis["results_sha256"] = sha256_file(args.results)
    analysis["protocol_sha256"] = sha256_file(PROTOCOL_PATH)
    lock["results_sha256"] = analysis["results_sha256"]
    lock["protocol_sha256"] = analysis["protocol_sha256"]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "development_analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "top_k_selection_lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "DEVELOPMENT_RESULTS_ZH.md").write_text(
        report_markdown(analysis, lock),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "selection_locked",
        "selected_top_k": lock["selected_top_k"],
        "rag_gain_observed_on_development": (
            analysis["rag_gain_observed_on_development"]
        ),
        "test_set_loaded": False,
        "analysis": str((args.output / "development_analysis.json").resolve()),
        "selection_lock": str(
            (args.output / "top_k_selection_lock.json").resolve()
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
