import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import generate_android_xml_web, web_server


class WebServerIntegrationTests(unittest.TestCase):
    def make_res(self, xml):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        package = Path(temp.name) / "package"
        layout = package / "res/layout"
        values = package / "res/values"
        layout.mkdir(parents=True)
        values.mkdir(parents=True)
        (layout / "screen.xml").write_text(xml, encoding="utf-8")
        (values / "strings.xml").write_text(
            "<resources></resources>",
            encoding="utf-8",
        )
        return package

    def test_web_report_uses_expanded_v3_and_xml_safe_gate(self):
        package = self.make_res(
            """<ImageButton xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/action"
    android:layout_width="40dp"
    android:layout_height="40dp" />
"""
        )

        report = web_server.report_for_res(package / "res")

        self.assertEqual(report["detector_profile"], "expanded_v3")
        self.assertGreaterEqual(report["error_count"], 1)
        self.assertEqual(
            report["actionable_error_count"],
            web_server.actionable_error_count(report),
        )

    def test_web_retrieval_is_deduplicated_top_two(self):
        package = self.make_res(
            """<ImageButton xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/action"
    android:layout_width="40dp"
    android:layout_height="40dp" />
"""
        )
        report = web_server.report_for_res(package / "res")

        documents = web_server.summarize_v2_documents(report)

        self.assertLessEqual(len(documents), web_server.RAG_TOP_K)
        self.assertEqual(len({item["doc_id"] for item in documents}), len(documents))
        for document in documents:
            self.assertIn("hybrid_score", document)
            self.assertIn("issue_code", document)

    def test_download_zip_preserves_package_paths(self):
        package = self.make_res(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" />"""
        )

        payload = web_server.package_zip_bytes(package)

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIn("res/layout/screen.xml", archive.namelist())
            self.assertIn("res/values/strings.xml", archive.namelist())

    def test_trace_summary_counts_accepted_and_rejected_attempts(self):
        summary = web_server.repair_trace_summary({
            "status": "completed",
            "rounds": [{
                "round": 1,
                "before_error_count": 2,
                "after_error_count": 0,
                "repairable_issue_count": 2,
                "deferred_issue_count": 1,
                "attempts": [
                    {"status": "rejected"},
                    {"status": "accepted"},
                ],
            }],
        })

        self.assertEqual(summary["accepted_rounds"], 1)
        self.assertEqual(summary["rejected_attempts"], 1)
        self.assertEqual(summary["stop_reason"], "completed")

    def test_job_id_validation_rejects_path_traversal(self):
        self.assertEqual(web_server.safe_job_id("abc123"), "abc123")
        with self.assertRaises(ValueError):
            web_server.safe_job_id("../abc")

    def test_web_runner_uses_v2_contract_without_calling_model_when_clean(self):
        package = self.make_res(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" />"""
        )
        output = package.parent / "output"

        state = generate_android_xml_web.run(SimpleNamespace(
            input=str(package),
            output=str(output),
            provider="deepseek",
            model="deepseek-v4-pro",
            api_key=None,
            max_rounds=3,
            max_model_attempts=3,
            force=True,
        ))

        self.assertIn(state["status"], {"completed", "completed_with_observations"})
        self.assertEqual(state["detector_profile"], "expanded_v3")
        self.assertEqual(state["retrieval_contract"], "v4_structured_hybrid")
        self.assertEqual(
            state["operation_contract"],
            "android_xml_operation_contract_v2_1",
        )

    def test_web_runner_executes_hybrid_rag_transactionally(self):
        package = self.make_res(
            """<ImageButton xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/action"
    android:layout_width="40dp"
    android:layout_height="40dp" />
"""
        )
        output = package.parent / "repaired"
        response = """{"operations":[
  {"op":"add_string_resource","path":"res/values/strings.xml","name":"action_description","value":"Perform action"},
  {"op":"set_attribute","path":"res/layout/screen.xml","selector":"/ImageButton[1]","attribute":"android:contentDescription","value":"@string/action_description"}
]}"""

        with patch.object(generate_android_xml_web, "validate_model_configuration"), patch.object(
            generate_android_xml_web,
            "run_model_with_metadata",
            return_value={"content": response, "metadata": {"status": "success"}},
        ):
            state = generate_android_xml_web.run(SimpleNamespace(
                input=str(package),
                output=str(output),
                provider="deepseek",
                model="deepseek-v4-pro",
                api_key=None,
                max_rounds=3,
                max_model_attempts=3,
                force=True,
            ))

        self.assertEqual(state["final_error_count"], 0)
        self.assertEqual(state["rounds"][0]["attempts"][0]["status"], "accepted")
        self.assertTrue(
            (output / "reports/retrieval_trace_round_1.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
