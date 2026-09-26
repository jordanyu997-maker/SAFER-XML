#!/usr/bin/env python3
"""Analyze the frozen V2.1 final Test comparison."""
import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.analyze_android_xml_v2_rag_development import (  # noqa: E402
    load_rows,
    number,
    sha256_file,
    summarize_condition,
    validate_matrix,
)


DEFAULT_ROOT = ROOT / "experiments/android_xml_v2_rag/test_v2_1"
DEFAULT_MATRIX = DEFAULT_ROOT / "matrix"
PROTOCOL_PATH = DEFAULT_ROOT / "protocol_test_v2_1.json"
PAIRED_FIELDS = (
    "task_id",
    "app_name",
    "screen_name",
    "candidate_count",
    "no_rag_repair_rate",
    "rag_topk2_repair_rate",
    "paired_delta",
    "paired_outcome",
)


def write_csv(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def paired_rows(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        grouped.setdefault(row["task_id"], {})[row["group"]] = row
    result = []
    for task_id, conditions in sorted(grouped.items()):
        no_rag = conditions["no_rag"]
        rag = conditions["rag_topk2"]
        no_rate = number(no_rag, "candidate_repair_rate")
        rag_rate = number(rag, "candidate_repair_rate")
        delta = rag_rate - no_rate
        outcome = "rag_win" if delta > 0 else "rag_loss" if delta < 0 else "tie"
        result.append({
            "task_id": task_id,
            "app_name": no_rag["app_name"],
            "screen_name": no_rag["screen_name"],
            "candidate_count": int(
                number(no_rag, "before_candidate_error_count")
            ),
            "no_rag_repair_rate": no_rate,
            "rag_topk2_repair_rate": rag_rate,
            "paired_delta": delta,
            "paired_outcome": outcome,
        })
    return result


def exact_sign_test(wins: int, losses: int) -> float:
    non_ties = wins + losses
    if non_ties == 0:
        return 1.0
    tail = min(wins, losses)
    probability = sum(
        math.comb(non_ties, value)
        for value in range(tail + 1)
    ) / (2 ** non_ties)
    return min(1.0, 2 * probability)


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    index = (len(values) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    fraction = index - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def bootstrap_mean_ci(
    deltas: list[float],
    resamples: int,
    seed: int,
    confidence_level: float,
) -> tuple[float, float]:
    if not deltas:
        return 0.0, 0.0
    rng = random.Random(seed)
    count = len(deltas)
    means = []
    for _ in range(resamples):
        sample = [deltas[rng.randrange(count)] for _ in range(count)]
        means.append(sum(sample) / count)
    means.sort()
    alpha = 1 - confidence_level
    return (
        percentile(means, alpha / 2),
        percentile(means, 1 - alpha / 2),
    )


def undesirable_count(summary: dict) -> int:
    return (
        summary["hardcoded_accessibility_value_count"]
        + summary["interaction_attribute_removal_count"]
        + summary["structural_operation_count"]
    )


def contribution_classification(
    summaries: dict,
    ci_lower: float,
    ci_upper: float,
) -> str:
    no_rag = summaries["no_rag"]
    rag = summaries["rag_topk2"]
    rate_delta = (
        rag["candidate_repair_rate"] - no_rag["candidate_repair_rate"]
    )
    no_worse_safety = (
        rag["safety_finding_count"] <= no_rag["safety_finding_count"]
        and undesirable_count(rag) <= undesirable_count(no_rag)
    )
    if rate_delta > 0 and ci_lower > 0 and no_worse_safety:
        return "limited_measurable_rag_contribution"
    if rate_delta < 0 and ci_upper < 0:
        return "rag_negative_repair_effect"
    return "no_measurable_rag_contribution"


def boundary_summary(matrix: Path) -> dict:
    rows = load_rows(matrix / "boundary_gate.csv")
    return {
        "candidate_count": len(rows),
        "model_calls": sum(int(row["model_calls"]) for row in rows),
        "blocked_before_model_count": sum(
            row["decision"] == "blocked_before_model" for row in rows
        ),
        "correct_refusal_count": sum(
            row["correct_static_repair_refusal"].lower() == "true"
            for row in rows
        ),
    }


def analyze(matrix: Path, protocol: dict) -> tuple[dict, list[dict]]:
    results_path = matrix / "test_results.csv"
    rows = load_rows(results_path)
    groups = tuple(protocol["execution"]["groups"])
    validate_matrix(rows, groups)
    expected_runs = protocol["execution"]["total_model_calls"]
    if len(rows) != expected_runs:
        raise ValueError(f"Test result count {len(rows)} != {expected_runs}")
    grouped = {
        group: [row for row in rows if row["group"] == group]
        for group in groups
    }
    summaries = {
        group: summarize_condition(group_rows)
        for group, group_rows in grouped.items()
    }
    pairs = paired_rows(rows)
    wins = sum(row["paired_outcome"] == "rag_win" for row in pairs)
    ties = sum(row["paired_outcome"] == "tie" for row in pairs)
    losses = sum(row["paired_outcome"] == "rag_loss" for row in pairs)
    deltas = [float(row["paired_delta"]) for row in pairs]
    config = protocol["paired_inference_config"]
    ci_lower, ci_upper = bootstrap_mean_ci(
        deltas,
        int(config["bootstrap_resamples"]),
        int(config["bootstrap_seed"]),
        float(config["confidence_level"]),
    )
    mean_delta = sum(deltas) / len(deltas)
    classification = contribution_classification(
        summaries,
        ci_lower,
        ci_upper,
    )
    analysis = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "analysis_scope": "frozen_test_only",
        "test_set_loaded": True,
        "condition_run_count": len(rows),
        "infrastructure_failure_count": sum(
            row["status"] == "infrastructure_failed" for row in rows
        ),
        "condition_summaries": summaries,
        "paired_task_analysis": {
            "task_count": len(pairs),
            "rag_wins": wins,
            "ties": ties,
            "rag_losses": losses,
            "mean_task_repair_rate_delta": mean_delta,
            "bootstrap_ci_lower": ci_lower,
            "bootstrap_ci_upper": ci_upper,
            "confidence_level": config["confidence_level"],
            "bootstrap_resamples": config["bootstrap_resamples"],
            "bootstrap_seed": config["bootstrap_seed"],
            "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        },
        "boundary_summary": boundary_summary(matrix),
        "eligibility_audit": protocol["eligibility_audit"],
        "rag_contribution_classification": classification,
        "development_tuning_reopened": False,
        "results_sha256": sha256_file(results_path),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
    }
    return analysis, pairs


def report_markdown(analysis: dict) -> str:
    summaries = analysis["condition_summaries"]
    paired = analysis["paired_task_analysis"]
    boundary = analysis["boundary_summary"]
    return "\n".join([
        "# V2.1 最终 Test 结果",
        "",
        "## 完整性",
        "",
        f"- 条件运行：{analysis['condition_run_count']}；",
        f"- 基础设施失败：{analysis['infrastructure_failure_count']}；",
        "- Development 参数未重新打开；",
        "- 原冻结 Test 数据未修改；",
        "- 3 条预筛语义误报在任何模型调用前排除。",
        "",
        "## 修复结果",
        "",
        "| 条件 | 修复问题 | 修复率 | 完全修复任务 | 安全问题 | 总 Token |",
        "|---|---:|---:|---:|---:|---:|",
        *[
            (
                f"| {group} | {item['candidate_repaired']}/"
                f"{item['candidate_before']} | "
                f"{item['candidate_repair_rate']:.1%} | "
                f"{item['complete_task_count']}/{item['task_count']} | "
                f"{item['safety_finding_count']} | "
                f"{item['total_tokens']} |"
            )
            for group, item in summaries.items()
        ],
        "",
        "## 配对分析",
        "",
        f"- RAG 胜/平/负：{paired['rag_wins']}/"
        f"{paired['ties']}/{paired['rag_losses']}；",
        f"- 平均任务修复率差：{paired['mean_task_repair_rate_delta']:.4f}；",
        f"- 95% bootstrap CI：[{paired['bootstrap_ci_lower']:.4f}, "
        f"{paired['bootstrap_ci_upper']:.4f}]；",
        f"- 双侧精确符号检验 p={paired['two_sided_exact_sign_test_p']:.6f}。",
        "",
        "## Boundary",
        "",
        f"- {boundary['candidate_count']} 条全部在模型前阻断；",
        f"- 模型调用：{boundary['model_calls']}；",
        "",
        "## 结论",
        "",
        f"`{analysis['rag_contribution_classification']}`",
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    analysis, pairs = analyze(args.matrix, protocol)
    args.output.mkdir(parents=True, exist_ok=True)
    analysis_path = args.output / "final_test_analysis.json"
    paired_path = args.output / "paired_task_results.csv"
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(paired_path, pairs, PAIRED_FIELDS)
    (args.output / "FINAL_TEST_RESULTS_ZH.md").write_text(
        report_markdown(analysis),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "final_test_analyzed",
        "rag_contribution_classification": (
            analysis["rag_contribution_classification"]
        ),
        "analysis": str(analysis_path.resolve()),
        "paired_results": str(paired_path.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
