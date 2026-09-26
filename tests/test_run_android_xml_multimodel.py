import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.run_android_xml_multimodel import (
    RESULT_FIELDS,
    build_tasks,
    completed_task,
    infrastructure_failure_reason,
    preflight_one,
    result_row,
    task_command,
    task_environment,
)
from tests.test_model_provider import FakeResponse


class AndroidXmlMultiModelTests(unittest.TestCase):
    def setUp(self):
        self.protocol = {
            "protocol_id": "test_protocol",
            "runner_protocol_version": 5,
            "output_root": "experiments/test/runs",
            "settings": {
                "max_rounds": 3,
                "max_model_attempts_per_round": 3,
                "rag_limit": 16,
                "max_output_tokens": 1024,
            },
        }
        self.model = {
            "key": "model_a",
            "display_name": "Model A",
            "provider": "openai",
            "model": "model-a",
            "api_key_env": "ANDROID_XML_GPT_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
            "base_url": "https://example.test/v1",
            "models_url": "https://example.test/v1/models",
            "api_style": "responses",
        }
        self.subject = {
            "app_id": "example.app",
            "app_name": "Example App",
            "category": "Utility",
            "layouts": ["main", "settings"],
            "source_path": "/tmp/example-source",
        }
        self.protocol["models"] = [self.model]

    def test_build_tasks_creates_model_repetition_app_products(self):
        tasks = build_tasks(
            self.protocol,
            [self.model, dict(self.model, key="model_b")],
            [self.subject, dict(self.subject, app_id="second.app")],
            [1, 2, 3],
            "formal",
        )

        self.assertEqual(len(tasks), 12)
        self.assertIn("formal/model_a/rep_01", tasks[0]["output"].as_posix())

    def test_task_command_contains_no_api_key(self):
        task = build_tasks(
            self.protocol,
            [self.model],
            [self.subject],
            [1],
            "pilot",
        )[0]
        command = task_command(self.protocol, task)

        self.assertNotIn("secret-key", " ".join(command))
        self.assertIn("--skip-manifest-update", command)
        self.assertIn("model-a", command)
        phase_index = command.index("--experiment-phase")
        self.assertEqual(command[phase_index + 1], "pilot")

    def test_task_command_records_optional_detector_profile(self):
        self.protocol["settings"]["detector_profile"] = "expanded_v2"
        task = build_tasks(
            self.protocol,
            [self.model],
            [self.subject],
            [1],
            "pilot",
        )[0]

        command = task_command(self.protocol, task)

        profile_index = command.index("--detector-profile")
        self.assertEqual(command[profile_index + 1], "expanded_v2")

    def test_task_environment_maps_project_key_only_for_child(self):
        with patch.dict(
            os.environ,
            {"ANDROID_XML_GPT_API_KEY": "secret-key"},
            clear=True,
        ):
            environment = task_environment(self.protocol, self.model)

        self.assertEqual(environment["OPENAI_API_KEY"], "secret-key")
        self.assertEqual(environment["OPENAI_BASE_URL"], self.model["base_url"])

    def test_preflight_requires_exact_model_id(self):
        payload = {
            "data": [
                {"id": "model-a"},
                {"id": "model-a-mini"},
            ]
        }
        with patch.dict(
            os.environ,
            {"ANDROID_XML_GPT_API_KEY": "secret-key"},
            clear=True,
        ), patch(
            "tools.run_android_xml_multimodel.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        ):
            result = preflight_one(self.model)

        self.assertEqual(result["status"], "available")
        self.assertTrue(result["exact_model_id_available"])
        self.assertNotIn("secret-key", str(result))

    def test_preflight_identifies_api_client(self):
        payload = {"data": [{"id": "model-a"}]}

        def fake_urlopen(request, timeout):
            self.assertEqual(
                request.get_header("User-agent"),
                "android-xml-a11y-research/1.0",
            )
            return FakeResponse(payload)

        with patch.dict(
            os.environ,
            {"ANDROID_XML_GPT_API_KEY": "secret-key"},
            clear=True,
        ), patch(
            "tools.run_android_xml_multimodel.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            result = preflight_one(self.model)

        self.assertEqual(result["status"], "available")

    def test_model_provider_failure_is_not_a_completed_task(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "proposed/reports").mkdir(parents=True)
            (output / "comparison_result.json").write_text(json.dumps({
                "groups": {
                    "baseline": {"status": "model_error"},
                    "proposed": {"status": "failed"},
                }
            }), encoding="utf-8")
            task = {"output": output}

            self.assertEqual(
                infrastructure_failure_reason(output),
                "baseline_model_provider_error",
            )
            self.assertFalse(completed_task(task))

    def test_invalid_model_output_remains_a_completed_method_result(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "comparison_result.json").write_text(json.dumps({
                "groups": {
                    "baseline": {"status": "invalid_model_output"},
                    "proposed": {"status": "no_improvement"},
                }
            }), encoding="utf-8")

            self.assertIsNone(infrastructure_failure_reason(output))
            self.assertTrue(completed_task({"output": output}))

    def test_result_row_includes_quality_iterations_review_and_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "baseline/reports").mkdir(parents=True)
            (run / "proposed/reports").mkdir(parents=True)
            (run / "experiment_config.json").write_text(json.dumps({
                "protocol_id": "test_protocol",
                "provider": "openai",
                "model": "model-a",
                "api_streaming": True,
                "app_id": "example.app",
                "app_name": "Example App",
                "category": "Utility",
                "layouts": ["main", "settings"],
                "input_resource_sha256": "abc123",
            }), encoding="utf-8")
            (run / "batch_run.json").write_text(json.dumps({
                "phase": "pilot",
                "model_key": "model_a",
                "repetition": 1,
            }), encoding="utf-8")
            summary = {
                "model_calls": 1,
                "provider_attempts": 2,
                "duration_ms": 100,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
                "resolved_models": ["model-a"],
                "request_ids": ["req-1"],
            }
            final_baseline = {
                "error_count": 1,
                "warning_count": 2,
                "info_count": 3,
                "total_issue_count": 6,
                "repairable_error_count": 1,
            }
            final_enhanced = {
                "error_count": 0,
                "warning_count": 1,
                "info_count": 1,
                "total_issue_count": 2,
                "repairable_error_count": 0,
            }
            (run / "comparison_result.json").write_text(json.dumps({
                "completed_at": "2026-01-01T00:00:00+00:00",
                "original": {
                    "error_count": 2,
                    "warning_count": 3,
                    "info_count": 4,
                    "total_issue_count": 9,
                    "repairable_error_count": 2,
                },
                "groups": {
                    "baseline": {
                        "status": "invalid_model_output",
                        "model_calls": 1,
                        "model_call_summary": summary,
                        "metrics": {
                            "final": final_baseline,
                            "safety_findings": 0,
                        },
                    },
                    "proposed": {
                        "status": "completed_with_observations",
                        "model_calls": 2,
                        "model_call_summary": summary,
                        "metrics": {
                            "final": final_enhanced,
                            "safety_findings": 0,
                        },
                    },
                },
            }), encoding="utf-8")
            (run / "proposed/reports/repair_run.json").write_text(
                json.dumps({
                    "rounds": [
                        {"attempts": [
                            {"status": "rejected"},
                            {"status": "accepted"},
                        ]},
                        {"attempts": []},
                    ]
                }),
                encoding="utf-8",
            )
            (run / "baseline/reports/operation_error.txt").write_text(
                "unsafe operation\n",
                encoding="utf-8",
            )
            (run / "manual_review.json").write_text(json.dumps({
                "source_review_status": "partial",
                "professional_review_status": "pending",
                "baseline": {"notes": "baseline note"},
                "proposed": {"notes": "enhanced note"},
                "files": {
                    "layout/main.xml": {
                        "baseline": {
                            "semantic_correct_count": 0,
                            "semantic_incorrect_count": 0,
                            "semantic_pending_count": 1,
                        },
                        "proposed": {
                            "semantic_correct_count": 1,
                            "semantic_incorrect_count": 0,
                            "semantic_pending_count": 0,
                        },
                    }
                },
            }), encoding="utf-8")

            row = result_row(self.protocol, run)

        self.assertEqual(set(row), set(RESULT_FIELDS))
        self.assertEqual(row["before_warning_count"], 3)
        self.assertTrue(row["api_streaming"])
        self.assertEqual(row["enhanced_after_info_count"], 1)
        self.assertEqual(row["baseline_error_repair_rate"], 0.5)
        self.assertEqual(row["enhanced_iterations"], 1)
        self.assertEqual(row["enhanced_rejected_attempts"], 1)
        self.assertEqual(row["baseline_network_retries"], 1)
        self.assertEqual(row["source_review_status"], "partial")
        self.assertEqual(row["enhanced_semantic_correct_count"], 1)
        self.assertIn("baseline_operation_error=unsafe operation", row["notes"])


if __name__ == "__main__":
    unittest.main()
