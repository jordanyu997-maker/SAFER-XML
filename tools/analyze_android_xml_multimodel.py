#!/usr/bin/env python3
"""Create reproducible app-level statistics for the multi-model XML study."""
import argparse
import csv
import hashlib
import json
import math
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = (
    ROOT / "experiments/android_xml_multimodel/multimodel_app_results.csv"
)
DEFAULT_SUBSET = (
    ROOT / "experiments/android_xml_multimodel/stability_subset_v1.json"
)
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_multimodel/analysis"
MODEL_ORDER = ["gpt_5_6_sol", "deepseek_v4_pro", "claude_opus_4_8"]
MODEL_LABELS = {
    "gpt_5_6_sol": "GPT 5.6 SOL",
    "deepseek_v4_pro": "DeepSeek V4 Pro",
    "claude_opus_4_8": "Claude Opus 4.8",
}
BOOTSTRAP_SEED = 20260719


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def integer(row, field):
    value = row.get(field)
    return int(value) if value not in {None, ""} else 0


def repair_rate(before, after):
    return None if before == 0 else (before - after) / before


def average_ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = ((cursor + 1) + end) / 2.0
        for position in range(cursor, end):
            ranks[order[position]] = rank
        cursor = end
    return ranks


def exact_wilcoxon_signed_rank(differences):
    """Two-sided exact sign-permutation Wilcoxon test with tied ranks."""
    nonzero = [float(value) for value in differences if float(value) != 0.0]
    if not nonzero:
        return {
            "n_total": len(differences),
            "n_nonzero": 0,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "statistic": 0.0,
            "p_value": 1.0,
            "rank_biserial": 0.0,
        }
    ranks = average_ranks([abs(value) for value in nonzero])
    scaled = [int(round(rank * 2)) for rank in ranks]
    observed = sum(
        rank for rank, difference in zip(scaled, nonzero) if difference > 0
    )
    total = sum(scaled)
    distribution = {0: 1}
    for rank in scaled:
        updated = dict(distribution)
        for subtotal, count in distribution.items():
            updated[subtotal + rank] = updated.get(subtotal + rank, 0) + count
        distribution = updated
    observed_distance = abs(2 * observed - total)
    extreme = sum(
        count
        for subtotal, count in distribution.items()
        if abs(2 * subtotal - total) >= observed_distance
    )
    p_value = min(extreme / (2 ** len(nonzero)), 1.0)
    w_plus = observed / 2.0
    w_minus = (total - observed) / 2.0
    return {
        "n_total": len(differences),
        "n_nonzero": len(nonzero),
        "w_plus": w_plus,
        "w_minus": w_minus,
        "statistic": min(w_plus, w_minus),
        "p_value": p_value,
        "rank_biserial": (w_plus - w_minus) / (w_plus + w_minus),
    }


def exact_mcnemar(baseline_success, enhanced_success):
    baseline_only = sum(
        before and not after
        for before, after in zip(baseline_success, enhanced_success)
    )
    enhanced_only = sum(
        after and not before
        for before, after in zip(baseline_success, enhanced_success)
    )
    discordant = baseline_only + enhanced_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, value)
            for value in range(min(baseline_only, enhanced_only) + 1)
        ) / (2 ** discordant)
        p_value = min(2 * tail, 1.0)
    return {
        "baseline_only_success": baseline_only,
        "enhanced_only_success": enhanced_only,
        "discordant_pairs": discordant,
        "p_value": p_value,
    }


def bootstrap_mean_ci(values, rng, resamples):
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"estimate": None, "ci_low": None, "ci_high": None}
    indices = rng.integers(0, array.size, size=(resamples, array.size))
    estimates = array[indices].mean(axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return {
        "estimate": float(array.mean()),
        "ci_low": float(low),
        "ci_high": float(high),
    }


def holm_adjust(p_values):
    count = len(p_values)
    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [1.0] * count
    running = 0.0
    for position, index in enumerate(order):
        candidate = min((count - position) * p_values[index], 1.0)
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def endpoint_fields(endpoint):
    if endpoint == "all_error":
        return (
            "before_error_count",
            "baseline_after_error_count",
            "enhanced_after_error_count",
        )
    return (
        "before_xml_safe_error_count",
        "baseline_after_xml_safe_error_count",
        "enhanced_after_xml_safe_error_count",
    )


def validate_design(rows, subset):
    formal = [row for row in rows if row.get("phase") == "formal"]
    if any(row.get("batch_status") != "completed" for row in formal):
        raise SystemExit("Formal 数据仍包含基础设施失败，停止统计分析。")
    main = [row for row in formal if integer(row, "repetition") == 1]
    by_model = {
        model: [row for row in main if row.get("model_key") == model]
        for model in MODEL_ORDER
    }
    if any(len(group) != 40 for group in by_model.values()):
        raise SystemExit("每个模型必须恰好包含 40 个 rep 1 主实验。")
    app_sets = [set(row["app_id"] for row in by_model[model]) for model in MODEL_ORDER]
    if not all(app_set == app_sets[0] for app_set in app_sets[1:]):
        raise SystemExit("三模型的 App 集合不一致。")
    indexed = {
        model: {row["app_id"]: row for row in by_model[model]}
        for model in MODEL_ORDER
    }
    for app_id in app_sets[0]:
        hashes = {
            indexed[model][app_id]["input_resource_sha256"]
            for model in MODEL_ORDER
        }
        if len(hashes) != 1:
            raise SystemExit(f"{app_id} 的输入资源哈希不一致。")
    subset_names = {app["app_name"] for app in subset["apps"]}
    for model in MODEL_ORDER:
        stability = [
            row for row in formal
            if row.get("model_key") == model
            and row.get("app_name") in subset_names
        ]
        repetitions = defaultdict(set)
        for row in stability:
            repetitions[row["app_name"]].add(integer(row, "repetition"))
        if set(repetitions) != subset_names or any(
            values != {1, 2, 3} for values in repetitions.values()
        ):
            raise SystemExit(f"{model} 的稳定性重复记录不完整。")
    return formal, main, by_model, subset_names


def primary_results(by_model, rng, resamples):
    results = []
    paired_rows = []
    for model in MODEL_ORDER:
        group = sorted(by_model[model], key=lambda row: row["app_id"])
        for row in group:
            paired_rows.append({
                "model_key": model,
                "model_display_name": MODEL_LABELS[model],
                "app_id": row["app_id"],
                "app_name": row["app_name"],
                "category": row["category"],
                "selected_interface_count": integer(
                    row, "selected_interface_count"
                ),
                "before_error_count": integer(row, "before_error_count"),
                "baseline_after_error_count": integer(
                    row, "baseline_after_error_count"
                ),
                "enhanced_after_error_count": integer(
                    row, "enhanced_after_error_count"
                ),
                "paired_residual_error_difference": integer(
                    row, "baseline_after_error_count"
                ) - integer(row, "enhanced_after_error_count"),
                "before_xml_safe_error_count": integer(
                    row, "before_xml_safe_error_count"
                ),
                "baseline_after_xml_safe_error_count": integer(
                    row, "baseline_after_xml_safe_error_count"
                ),
                "enhanced_after_xml_safe_error_count": integer(
                    row, "enhanced_after_xml_safe_error_count"
                ),
            })
        for endpoint in ("all_error", "xml_safe_error"):
            before_field, baseline_field, enhanced_field = endpoint_fields(endpoint)
            before = [integer(row, before_field) for row in group]
            baseline = [integer(row, baseline_field) for row in group]
            enhanced = [integer(row, enhanced_field) for row in group]
            residual_differences = [
                left - right for left, right in zip(baseline, enhanced)
            ]
            paired_repair_rate_differences = [
                repair_rate(start, right) - repair_rate(start, left)
                for start, left, right in zip(before, baseline, enhanced)
                if start > 0
            ]
            wilcoxon = exact_wilcoxon_signed_rank(residual_differences)
            mean_difference = bootstrap_mean_ci(
                residual_differences, rng, resamples
            )
            macro_difference = bootstrap_mean_ci(
                paired_repair_rate_differences, rng, resamples
            )
            mcnemar = exact_mcnemar(
                [value == 0 for value in baseline],
                [value == 0 for value in enhanced],
            )
            before_total = sum(before)
            baseline_total = sum(baseline)
            enhanced_total = sum(enhanced)
            result = {
                "model_key": model,
                "model_display_name": MODEL_LABELS[model],
                "endpoint": endpoint,
                "n_apps": len(group),
                "n_apps_with_initial_findings": sum(value > 0 for value in before),
                "before_total": before_total,
                "baseline_after_total": baseline_total,
                "enhanced_after_total": enhanced_total,
                "baseline_aggregate_repair_rate": repair_rate(
                    before_total, baseline_total
                ),
                "enhanced_aggregate_repair_rate": repair_rate(
                    before_total, enhanced_total
                ),
                "aggregate_repair_rate_difference": (
                    repair_rate(before_total, enhanced_total)
                    - repair_rate(before_total, baseline_total)
                ),
                "mean_paired_residual_difference": mean_difference["estimate"],
                "mean_paired_residual_difference_ci_low": mean_difference["ci_low"],
                "mean_paired_residual_difference_ci_high": mean_difference["ci_high"],
                "median_paired_residual_difference": float(
                    np.median(residual_differences)
                ),
                "mean_paired_macro_repair_rate_difference": macro_difference["estimate"],
                "mean_paired_macro_repair_rate_difference_ci_low": macro_difference["ci_low"],
                "mean_paired_macro_repair_rate_difference_ci_high": macro_difference["ci_high"],
                "wilcoxon_n_nonzero": wilcoxon["n_nonzero"],
                "wilcoxon_statistic": wilcoxon["statistic"],
                "wilcoxon_p_value": wilcoxon["p_value"],
                "rank_biserial_correlation": wilcoxon["rank_biserial"],
                "baseline_zero_error_apps": sum(value == 0 for value in baseline),
                "enhanced_zero_error_apps": sum(value == 0 for value in enhanced),
                "mcnemar_baseline_only_success": mcnemar["baseline_only_success"],
                "mcnemar_enhanced_only_success": mcnemar["enhanced_only_success"],
                "mcnemar_p_value": mcnemar["p_value"],
            }
            results.append(result)
    for endpoint in ("all_error", "xml_safe_error"):
        indices = [
            index for index, result in enumerate(results)
            if result["endpoint"] == endpoint
        ]
        adjusted = holm_adjust([
            results[index]["wilcoxon_p_value"] for index in indices
        ])
        adjusted_mcnemar = holm_adjust([
            results[index]["mcnemar_p_value"] for index in indices
        ])
        for index, p_value, mcnemar_p in zip(indices, adjusted, adjusted_mcnemar):
            results[index]["wilcoxon_holm_p_value"] = p_value
            results[index]["mcnemar_holm_p_value"] = mcnemar_p
    return results, paired_rows


def descriptive_model_results(by_model):
    output = []
    for model in MODEL_ORDER:
        rows = by_model[model]
        before = sum(integer(row, "before_error_count") for row in rows)
        baseline = sum(integer(row, "baseline_after_error_count") for row in rows)
        enhanced = sum(integer(row, "enhanced_after_error_count") for row in rows)
        before_safe = sum(integer(row, "before_xml_safe_error_count") for row in rows)
        baseline_safe = sum(
            integer(row, "baseline_after_xml_safe_error_count") for row in rows
        )
        enhanced_safe = sum(
            integer(row, "enhanced_after_xml_safe_error_count") for row in rows
        )
        output.append({
            "model_key": model,
            "model_display_name": MODEL_LABELS[model],
            "n_apps": len(rows),
            "n_selected_interfaces": sum(
                integer(row, "selected_interface_count") for row in rows
            ),
            "before_error_count": before,
            "baseline_after_error_count": baseline,
            "enhanced_after_error_count": enhanced,
            "baseline_aggregate_repair_rate": repair_rate(before, baseline),
            "enhanced_aggregate_repair_rate": repair_rate(before, enhanced),
            "before_xml_safe_error_count": before_safe,
            "baseline_after_xml_safe_error_count": baseline_safe,
            "enhanced_after_xml_safe_error_count": enhanced_safe,
            "baseline_xml_safe_repair_rate": repair_rate(
                before_safe, baseline_safe
            ),
            "enhanced_xml_safe_repair_rate": repair_rate(
                before_safe, enhanced_safe
            ),
            "baseline_zero_error_apps": sum(
                integer(row, "baseline_after_error_count") == 0 for row in rows
            ),
            "enhanced_zero_error_apps": sum(
                integer(row, "enhanced_after_error_count") == 0 for row in rows
            ),
            "baseline_invalid_output_apps": sum(
                row.get("baseline_status") == "invalid_model_output"
                for row in rows
            ),
            "enhanced_invalid_or_rejected_attempts": sum(
                integer(row, "enhanced_rejected_attempts") for row in rows
            ),
            "baseline_model_calls": sum(
                integer(row, "baseline_model_calls") for row in rows
            ),
            "enhanced_model_calls": sum(
                integer(row, "enhanced_model_calls") for row in rows
            ),
            "baseline_total_tokens": sum(
                integer(row, "baseline_total_tokens") for row in rows
            ),
            "enhanced_total_tokens": sum(
                integer(row, "enhanced_total_tokens") for row in rows
            ),
            "baseline_duration_ms": sum(
                float(row.get("baseline_duration_ms") or 0) for row in rows
            ),
            "enhanced_duration_ms": sum(
                float(row.get("enhanced_duration_ms") or 0) for row in rows
            ),
        })
    return output


def cross_model_results(by_model):
    output = []
    for method in ("baseline", "enhanced"):
        for endpoint in ("all_error", "xml_safe_error"):
            _, baseline_field, enhanced_field = endpoint_fields(endpoint)
            field = baseline_field if method == "baseline" else enhanced_field
            for left_index in range(len(MODEL_ORDER)):
                for right_index in range(left_index + 1, len(MODEL_ORDER)):
                    left = MODEL_ORDER[left_index]
                    right = MODEL_ORDER[right_index]
                    left_rows = {
                        row["app_id"]: row for row in by_model[left]
                    }
                    right_rows = {
                        row["app_id"]: row for row in by_model[right]
                    }
                    differences = [
                        integer(left_rows[app_id], field)
                        - integer(right_rows[app_id], field)
                        for app_id in sorted(left_rows)
                    ]
                    test = exact_wilcoxon_signed_rank(differences)
                    output.append({
                        "method": method,
                        "endpoint": endpoint,
                        "left_model": left,
                        "right_model": right,
                        "mean_left_minus_right_residual": float(
                            np.mean(differences)
                        ),
                        "median_left_minus_right_residual": float(
                            np.median(differences)
                        ),
                        "wilcoxon_n_nonzero": test["n_nonzero"],
                        "wilcoxon_statistic": test["statistic"],
                        "wilcoxon_p_value": test["p_value"],
                        "rank_biserial_correlation": test["rank_biserial"],
                    })
    families = defaultdict(list)
    for index, result in enumerate(output):
        families[(result["method"], result["endpoint"])].append(index)
    for indices in families.values():
        adjusted = holm_adjust([
            output[index]["wilcoxon_p_value"] for index in indices
        ])
        for index, value in zip(indices, adjusted):
            output[index]["wilcoxon_holm_p_value"] = value
    return output


def stability_results(formal, subset_names):
    repeat_rows = []
    summary_rows = []
    for model in MODEL_ORDER:
        group = [
            row for row in formal
            if row.get("model_key") == model
            and row.get("app_name") in subset_names
        ]
        for method in ("baseline", "enhanced"):
            for endpoint in ("all_error", "xml_safe_error"):
                before_field, baseline_field, enhanced_field = endpoint_fields(endpoint)
                after_field = baseline_field if method == "baseline" else enhanced_field
                rates = []
                by_app = defaultdict(list)
                for repetition in (1, 2, 3):
                    rows = [
                        row for row in group
                        if integer(row, "repetition") == repetition
                    ]
                    before = sum(integer(row, before_field) for row in rows)
                    after = sum(integer(row, after_field) for row in rows)
                    rate = repair_rate(before, after)
                    rates.append(rate)
                    repeat_rows.append({
                        "model_key": model,
                        "model_display_name": MODEL_LABELS[model],
                        "method": method,
                        "endpoint": endpoint,
                        "repetition": repetition,
                        "n_apps": len(rows),
                        "before_total": before,
                        "after_total": after,
                        "aggregate_repair_rate": rate,
                    })
                    for row in rows:
                        by_app[row["app_name"]].append(integer(row, after_field))
                app_standard_deviations = [
                    float(np.std(values, ddof=1)) for values in by_app.values()
                ]
                summary_rows.append({
                    "model_key": model,
                    "model_display_name": MODEL_LABELS[model],
                    "method": method,
                    "endpoint": endpoint,
                    "n_apps": len(by_app),
                    "n_repetitions": 3,
                    "mean_aggregate_repair_rate": float(np.mean(rates)),
                    "sd_aggregate_repair_rate": float(np.std(rates, ddof=1)),
                    "minimum_aggregate_repair_rate": min(rates),
                    "maximum_aggregate_repair_rate": max(rates),
                    "apps_with_identical_after_count_all_repetitions": sum(
                        len(set(values)) == 1 for values in by_app.values()
                    ),
                    "mean_within_app_after_count_sd": float(
                        np.mean(app_standard_deviations)
                    ),
                })
    return repeat_rows, summary_rows


def format_p(value):
    if value < 0.001:
        return f"{value:.2e}"
    return f"{value:.3f}"


def markdown_report(
    manifest,
    model_results,
    primary,
    stability,
):
    primary_all = {
        row["model_key"]: row for row in primary
        if row["endpoint"] == "all_error"
    }
    stability_all = {
        (row["model_key"], row["method"]): row
        for row in stability if row["endpoint"] == "all_error"
    }
    lines = [
        "# Android XML Multi-model Statistical Report",
        "",
        "## Analysis scope",
        "",
        "- Independent unit: App (`n = 40` paired Apps per model).",
        "- XML interfaces are within-App subsamples and were not treated as independent observations.",
        "- Primary comparison: Baseline versus Enhanced residual error count within each App.",
        "- Stability repetitions are stochastic technical repeats on a frozen 10-App subset; they do not increase the primary independent sample size.",
        f"- Formal records analysed: {manifest['formal_row_count']}; Pilot records excluded: {manifest['excluded_pilot_row_count']}.",
        "- Missing formal runs and infrastructure failures: 0.",
        "",
        "## Main descriptive results",
        "",
        "| Model | Before | Baseline after | Enhanced after | Baseline repair | Enhanced repair |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in model_results:
        lines.append(
            f"| {row['model_display_name']} | {row['before_error_count']} | "
            f"{row['baseline_after_error_count']} | {row['enhanced_after_error_count']} | "
            f"{row['baseline_aggregate_repair_rate']:.1%} | "
            f"{row['enhanced_aggregate_repair_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Paired inference",
        "",
        "Positive residual differences favour Enhanced because they represent errors left by Baseline but not Enhanced.",
        "",
        "| Model | Mean paired difference (95% bootstrap CI) | Rank-biserial | Exact Wilcoxon p | Holm p |",
        "|---|---:|---:|---:|---:|",
    ])
    for model in MODEL_ORDER:
        row = primary_all[model]
        lines.append(
            f"| {MODEL_LABELS[model]} | "
            f"{row['mean_paired_residual_difference']:.2f} "
            f"({row['mean_paired_residual_difference_ci_low']:.2f}, "
            f"{row['mean_paired_residual_difference_ci_high']:.2f}) | "
            f"{row['rank_biserial_correlation']:.3f} | "
            f"{format_p(row['wilcoxon_p_value'])} | "
            f"{format_p(row['wilcoxon_holm_p_value'])} |"
        )
    lines.extend([
        "",
        "## Stability subset",
        "",
        "| Model | Baseline mean +/- s.d. | Enhanced mean +/- s.d. |",
        "|---|---:|---:|",
    ])
    for model in MODEL_ORDER:
        baseline = stability_all[(model, "baseline")]
        enhanced = stability_all[(model, "enhanced")]
        lines.append(
            f"| {MODEL_LABELS[model]} | "
            f"{baseline['mean_aggregate_repair_rate']:.1%} +/- "
            f"{baseline['sd_aggregate_repair_rate']:.1%} | "
            f"{enhanced['mean_aggregate_repair_rate']:.1%} +/- "
            f"{enhanced['sd_aggregate_repair_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Ready-to-paste Statistical analysis",
        "",
        "The App was the independent experimental unit. Each of the 40 Apps contributed one paired Baseline and Enhanced observation for each model; the two or three XML interfaces sampled within an App were aggregated at the App level and were not treated as independent replicates. Residual high-confidence error counts were compared between Baseline and Enhanced using two-sided exact Wilcoxon signed-rank tests based on sign permutations, with tied absolute ranks retained. P values for the three prespecified model-specific comparisons were adjusted using the Holm method separately for the all-error and XML-safe-error endpoint families. Effect magnitude was summarized using the paired mean residual-error difference with a percentile bootstrap 95% confidence interval (20,000 paired App-level resamples), the median paired difference, and the matched-pairs rank-biserial correlation. Zero-error completion proportions were compared using an exact McNemar test. Stability was evaluated separately on a frozen, stratified 10-App subset with three stochastic runs per model and method; these repeats were summarized as mean +/- s.d. and were not added to the primary sample size. Analyses were performed with Python "
        + manifest["software"]["python"] + " and NumPy "
        + manifest["software"]["numpy"] + ".",
        "",
        "## Reviewer-risk notes",
        "",
        "- Static detector outcomes establish detector-measured repair, not semantic correctness or runtime accessibility.",
        "- Professional and source-level manual review remains pending and must be reported separately.",
        "- Model IDs were verified against the configured APIs, but GPT and Claude were accessed through a third-party gateway and should be disclosed as such.",
        "- Four GPT rep-1 runs used SSE streaming after archived non-streaming 504 failures; model, prompt and generation limits were unchanged, and transport mode is retained in the records.",
        "- No power calculation or preregistration was supplied; avoid claiming that non-significant cross-model differences establish equivalence.",
        "",
    ])
    return "\n".join(lines)


def analyse(summary_path, subset_path, output_dir, resamples=20000):
    rows = read_csv(summary_path)
    subset = json.loads(Path(subset_path).read_text(encoding="utf-8"))
    formal, main, by_model, subset_names = validate_design(rows, subset)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    formal = sorted(
        formal,
        key=lambda row: (
            MODEL_ORDER.index(row["model_key"]),
            integer(row, "repetition"),
            row["app_name"].casefold(),
        ),
    )
    formal_path = output_dir / "formal_analysis_dataset.csv"
    write_csv(formal_path, formal, fieldnames=list(rows[0]))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    primary, paired = primary_results(by_model, rng, resamples)
    descriptive = descriptive_model_results(by_model)
    cross_model = cross_model_results(by_model)
    stability_repeat, stability_summary = stability_results(
        formal, subset_names
    )
    write_csv(output_dir / "model_main_results.csv", descriptive)
    write_csv(output_dir / "paired_app_results.csv", paired)
    write_csv(output_dir / "primary_statistical_results.csv", primary)
    write_csv(output_dir / "cross_model_results.csv", cross_model)
    write_csv(output_dir / "stability_repeat_results.csv", stability_repeat)
    write_csv(output_dir / "stability_summary.csv", stability_summary)
    manifest = {
        "schema_version": 1,
        "analysis_id": "android_xml_multimodel_primary_v1",
        "created_at": now_iso(),
        "source_summary": str(Path(summary_path).resolve()),
        "source_summary_sha256": sha256_file(summary_path),
        "formal_dataset": str(formal_path.resolve()),
        "formal_dataset_sha256": sha256_file(formal_path),
        "source_row_count": len(rows),
        "formal_row_count": len(formal),
        "main_row_count": len(main),
        "excluded_pilot_row_count": sum(
            row.get("phase") == "pilot" for row in rows
        ),
        "independent_unit": "App",
        "primary_n_per_model": 40,
        "interfaces_per_app": "2-3",
        "stability_subset_apps": len(subset_names),
        "stability_repetitions": 3,
        "bootstrap_resamples": resamples,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "multiple_comparison_correction": "Holm within endpoint family",
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "manual_review_status": dict(Counter(
            row.get("professional_review_status", "unknown")
            for row in main
        )),
        "api_streaming_main_rows": sum(
            row.get("api_streaming", "").casefold() == "true"
            for row in main
        ),
    }
    write_json(output_dir / "analysis_manifest.json", manifest)
    write_json(output_dir / "statistical_results.json", {
        "manifest": manifest,
        "model_main_results": descriptive,
        "primary_statistical_results": primary,
        "cross_model_results": cross_model,
        "stability_summary": stability_summary,
    })
    report = markdown_report(
        manifest, descriptive, primary, stability_summary
    )
    (output_dir / "statistical_report.md").write_text(
        report, encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Analyse the frozen Android XML multi-model experiment."
    )
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--subset", type=Path, default=DEFAULT_SUBSET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-resamples", type=int, default=20000)
    args = parser.parse_args()
    if args.bootstrap_resamples < 1000:
        raise SystemExit("bootstrap-resamples 必须至少为 1000。")
    manifest = analyse(
        args.summary,
        args.subset,
        args.output,
        args.bootstrap_resamples,
    )
    print(json.dumps({
        "analysis_id": manifest["analysis_id"],
        "formal_rows": manifest["formal_row_count"],
        "main_rows": manifest["main_row_count"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
