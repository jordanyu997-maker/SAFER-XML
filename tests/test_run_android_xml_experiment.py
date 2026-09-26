import json
import tempfile
import unittest
from pathlib import Path

from tools.run_android_xml_experiment import (
    FORMAL_APP_SUMMARY_FIELDS,
    FORMAL_RECORD_FIELDS,
    build_baseline_prompt,
    build_manual_review,
    experiment_status,
    formal_app_summary_row,
    formal_record_rows,
    model_call_summary,
    normalize_manual_review,
    repair_attempt_count,
    result_metrics,
)


class AndroidXmlExperimentTests(unittest.TestCase):
    def test_model_call_summary_aggregates_usage_without_keys(self):
        summary = model_call_summary([
            {
                "resolved_model": "resolved-model",
                "request_id": "req-1",
                "provider_attempts": 1,
                "duration_ms": 100.5,
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 5,
                    "total_tokens": 25,
                },
            },
            {
                "resolved_model": "resolved-model",
                "request_id": "req-2",
                "provider_attempts": 2,
                "duration_ms": 200,
                "usage": {
                    "input_tokens": 30,
                    "output_tokens": 10,
                    "total_tokens": 40,
                },
            },
        ])

        self.assertEqual(summary["model_calls"], 2)
        self.assertEqual(summary["provider_attempts"], 3)
        self.assertEqual(summary["duration_ms"], 300.5)
        self.assertEqual(summary["usage"]["total_tokens"], 65)
        self.assertEqual(summary["resolved_models"], ["resolved-model"])

    def test_model_call_summary_records_failed_provider_call(self):
        summary = model_call_summary([{
            "status": "failed",
            "provider_attempts": 3,
            "duration_ms": 180000,
            "http_status": 504,
            "error_type": "ModelServiceError",
            "usage": {},
        }])

        self.assertEqual(summary["model_calls"], 1)
        self.assertEqual(summary["successful_model_calls"], 0)
        self.assertEqual(summary["failed_model_calls"], 1)
        self.assertEqual(summary["provider_attempts"], 3)
        self.assertEqual(summary["network_retries"], 2)
        self.assertEqual(summary["http_statuses"], [504])
        self.assertEqual(summary["error_types"], ["ModelServiceError"])

    def test_baseline_prompt_contains_xml_but_no_rag_or_detector_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            res = Path(temp) / "res"
            (res / "layout").mkdir(parents=True)
            (res / "values").mkdir()
            (res / "layout" / "screen.xml").write_text(
                "<LinearLayout />",
                encoding="utf-8",
            )
            (res / "values" / "strings.xml").write_text(
                "<resources />",
                encoding="utf-8",
            )

            prompt = build_baseline_prompt(res)

        self.assertIn("res/layout/screen.xml", prompt)
        self.assertIn("Mechanical selector reference", prompt)
        self.assertNotIn("/Root[1]/Child[1]", prompt)
        self.assertNotIn("Retrieved knowledge", prompt)
        self.assertNotIn("Detected Android XML accessibility issues", prompt)

    def test_result_metrics_records_reduction_and_safety(self):
        initial = [
            {"type": "error", "code": "A", "repairability": "xml_safe"},
            {"type": "warning", "code": "B", "repairability": "manual_review"},
        ]
        final = [
            {"type": "warning", "code": "B", "repairability": "manual_review"}
        ]

        metrics = result_metrics(initial, final, [{"code": "SAFETY"}])

        self.assertEqual(metrics["issues_reduced"], 1)
        self.assertEqual(metrics["issue_reduction_rate"], 1.0)
        self.assertEqual(metrics["repair_rate"], 1.0)
        self.assertEqual(metrics["repairable_issues_reduced"], 1)
        self.assertEqual(metrics["repairable_issue_reduction_rate"], 1.0)
        self.assertEqual(metrics["safety_findings"], 1)

    def test_experiment_status_only_marks_zero_error_completion_successful(self):
        self.assertEqual(
            experiment_status("completed_with_observations", 0),
            "success",
        )
        self.assertEqual(
            experiment_status("stopped_non_repairable_errors", 2),
            "stopped_non_repairable_errors",
        )

    def test_repair_attempt_count_uses_recorded_attempt_status(self):
        repair_run = {
            "rounds": [
                {
                    "attempts": [
                        {"status": "rejected"},
                        {"status": "accepted"},
                        {"status": "rejected"},
                    ]
                },
                {"attempts": [{"status": "rejected"}]},
            ]
        }

        self.assertEqual(repair_attempt_count(repair_run), 4)
        self.assertEqual(repair_attempt_count(repair_run, "rejected"), 3)

    def test_manual_review_defaults_static_repairs_to_semantic_pending(self):
        review = normalize_manual_review(
            {
                "experiment_id": "example:run_01",
                "status": "pending",
                "baseline": {"notes": "preserved"},
                "proposed": {"notes": ""},
            },
            "example:run_01",
            {"layout/main.xml": {"baseline": 1, "proposed": 2}},
        )

        self.assertEqual(review["schema_version"], 2)
        self.assertEqual(
            review["files"]["layout/main.xml"]["baseline"][
                "semantic_pending_count"
            ],
            1,
        )
        self.assertEqual(
            review["files"]["layout/main.xml"]["proposed"][
                "semantic_pending_count"
            ],
            2,
        )
        self.assertEqual(review["baseline"]["notes"], "preserved")

    def test_formal_records_include_static_and_semantic_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            for group in ("original", "baseline", "proposed"):
                (run_dir / group / "res/layout").mkdir(parents=True)
                (run_dir / group / "res/layout/main.xml").write_text(
                    "<LinearLayout />",
                    encoding="utf-8",
                )
                (run_dir / group / "reports").mkdir()
            config = {
                "experiment_id": "example:run_01",
                "app_name": "Example",
                "category": "Utility",
                "run_id": "run_01",
                "layouts": ["main"],
            }
            comparison = {
                "original": {"error_count": 1},
                "groups": {
                    "baseline": {
                        "status": "completed",
                        "model_calls": 1,
                        "metrics": {
                            "final": {
                                "error_count": 0,
                                "warning_count": 1,
                                "info_count": 0,
                            },
                            "safety_findings": 0,
                        },
                    },
                    "proposed": {
                        "status": "completed_with_observations",
                        "model_calls": 1,
                        "metrics": {
                            "final": {
                                "error_count": 0,
                                "warning_count": 0,
                                "info_count": 0,
                            },
                            "safety_findings": 0,
                        },
                    },
                },
            }
            original_issue = {
                "file": str(run_dir / "original/res/layout/main.xml"),
                "severity": "error",
                "code": "MISSING_NAME",
            }
            reports = (
                (
                    run_dir / "original/reports/android_xml_a11y_report.json",
                    [original_issue],
                ),
                (
                    run_dir / "baseline/reports/android_xml_a11y_report.json",
                    [{
                        "file": str(run_dir / "baseline/res/layout/main.xml"),
                        "severity": "warning",
                        "code": "REVIEW",
                    }],
                ),
                (
                    run_dir / "proposed/reports/android_xml_a11y_report.json",
                    [],
                ),
            )
            for path, issues in reports:
                path.write_text(
                    json.dumps({"issues": issues}),
                    encoding="utf-8",
                )
            for group in ("baseline", "proposed"):
                (
                    run_dir
                    / group
                    / "reports/android_xml_repair_safety_report.json"
                ).write_text("[]", encoding="utf-8")
            (run_dir / "experiment_config.json").write_text(
                json.dumps(config),
                encoding="utf-8",
            )
            (run_dir / "comparison_result.json").write_text(
                json.dumps(comparison),
                encoding="utf-8",
            )
            review = build_manual_review(
                "example:run_01",
                {"layout/main.xml": {"baseline": 1, "proposed": 1}},
            )
            review["source_review_status"] = "partial"
            review["files"]["layout/main.xml"]["source_review_status"] = "completed"
            review["files"]["layout/main.xml"]["proposed"].update({
                "semantic_correct_count": 1,
                "semantic_pending_count": 0,
                "unrelated_change_count": 0,
                "dynamic_semantics_risk_count": 0,
            })
            (run_dir / "manual_review.json").write_text(
                json.dumps(review),
                encoding="utf-8",
            )

            rows = formal_record_rows(run_dir)
            app_row = formal_app_summary_row(run_dir)

        self.assertEqual(set(rows[0]), set(FORMAL_RECORD_FIELDS))
        self.assertEqual(rows[0]["interface_role"], "entry")
        self.assertEqual(rows[0]["baseline_repair_rate"], 1.0)
        self.assertEqual(rows[0]["baseline_warning_count"], 1)
        self.assertEqual(rows[0]["enhanced_semantic_correct_count"], 1)
        self.assertEqual(set(app_row), set(FORMAL_APP_SUMMARY_FIELDS))
        self.assertEqual(app_row["enhanced_semantic_correct_count"], 1)
        self.assertEqual(app_row["source_review_status"], "partial")


if __name__ == "__main__":
    unittest.main()
