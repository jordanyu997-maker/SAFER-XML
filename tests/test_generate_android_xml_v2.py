import json
import tempfile
import unittest
from pathlib import Path

from tools.generate_android_xml_v2 import (
    GROUP_MAX_ROUNDS,
    build_v2_prompt,
    group_prompt,
    run_group,
    v2_actionable_issues,
)
from tools.generate_android_xml import run_xml_checker


LAYOUT = """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent">
    <ImageButton
        android:id="@+id/save_button"
        android:layout_width="40dp"
        android:layout_height="40dp"
        android:src="@drawable/ic_save" />
</LinearLayout>
"""


class GenerateAndroidXmlV2Tests(unittest.TestCase):
    def make_package(self, root):
        package = root / "input"
        layout = package / "res/layout/main.xml"
        layout.parent.mkdir(parents=True)
        layout.write_text(LAYOUT, encoding="utf-8")
        strings = package / "res/values/strings.xml"
        strings.parent.mkdir(parents=True)
        strings.write_text("<resources></resources>\n", encoding="utf-8")
        drawable = package / "res/drawable/ic_save.xml"
        drawable.parent.mkdir(parents=True)
        drawable.write_text("<shape></shape>\n", encoding="utf-8")
        source = root / "source"
        code = source / "app/src/main/java/org/example/MainActivity.kt"
        code.parent.mkdir(parents=True)
        code.write_text(
            "fun bind() { findViewById(R.id.save_button).setOnClickListener { save() } }\n",
            encoding="utf-8",
        )
        return package, source

    def test_group_round_budgets_are_explicit(self):
        self.assertEqual(GROUP_MAX_ROUNDS["one_shot_baseline"], 1)
        self.assertEqual(GROUP_MAX_ROUNDS["v2_no_rag"], 2)
        self.assertEqual(GROUP_MAX_ROUNDS["v2_full"], 2)

    def test_actionable_scope_keeps_only_validated_xml_safe_errors(self):
        issues = [
            {
                "code": "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
                "severity": "error",
                "repairability": "xml_safe",
            },
            {
                "code": "ANDROID_XML_TOUCH_TARGET_TOO_SMALL",
                "severity": "warning",
                "repairability": "xml_safe",
            },
            {
                "code": "ANDROID_XML_NON_SEMANTIC_CLICKABLE",
                "severity": "error",
                "repairability": "requires_structure_or_code",
            },
        ]
        selected = v2_actionable_issues(issues)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["code"], "ANDROID_XML_MISSING_ACCESSIBLE_NAME")

    def test_no_rag_prompt_contains_findings_but_no_retrieved_context(self):
        with tempfile.TemporaryDirectory() as temp:
            package, source = self.make_package(Path(temp))
            issues = run_xml_checker(package / "res")
            prompt, trace = group_prompt(
                "v2_no_rag", issues, package / "res", source
            )

        self.assertIn("ANDROID_XML_MISSING_ACCESSIBLE_NAME", prompt)
        self.assertIn("Normative RAG is disabled", prompt)
        self.assertIn("App-context retrieval is disabled", prompt)
        self.assertEqual(trace["knowledge_document_count"], 0)
        self.assertEqual(trace["app_context_count"], 0)

    def test_full_prompt_records_bounded_current_app_context(self):
        with tempfile.TemporaryDirectory() as temp:
            package, source = self.make_package(Path(temp))
            issues = v2_actionable_issues(run_xml_checker(package / "res"))
            prompt, trace = build_v2_prompt(
                issues,
                package / "res",
                source,
                use_normative_rag=True,
                use_app_context=True,
            )

        self.assertIn("MainActivity.kt", prompt)
        self.assertLessEqual(trace["knowledge_document_count"], 6)
        self.assertLessEqual(trace["app_context_count"], 12)
        self.assertTrue(trace["knowledge_documents"])
        self.assertTrue(trace["app_context"])
        self.assertTrue(
            all(item["source_root"] == str(source.resolve()) for item in trace["app_context"])
        )

    def test_baseline_prompt_hides_detector_findings_and_retrieval(self):
        with tempfile.TemporaryDirectory() as temp:
            package, source = self.make_package(Path(temp))
            issues = run_xml_checker(package / "res")
            prompt, trace = group_prompt(
                "one_shot_baseline", issues, package / "res", source
            )

        self.assertNotIn("ANDROID_XML_MISSING_ACCESSIBLE_NAME", prompt)
        self.assertNotIn("Retrieved Android accessibility knowledge", prompt)
        self.assertFalse(trace["uses_normative_rag"])
        self.assertFalse(trace["uses_app_context_rag"])

    def test_dry_run_never_calls_model_and_writes_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, source = self.make_package(root)
            output = root / "output"
            state = run_group(
                package,
                output,
                source,
                "v2_full",
                "deepseek",
                "deepseek-v4-pro",
                dry_run=True,
            )
            recorded = json.loads(
                (output / "reports/v2_repair_run.json").read_text(encoding="utf-8")
            )
            trace_exists = (
                output / "reports/retrieval_trace_round_1.json"
            ).exists()

        self.assertEqual(state["status"], "dry_run")
        self.assertEqual(state["model_calls"], 0)
        self.assertEqual(recorded["model_calls"], 0)
        self.assertTrue(trace_exists)


if __name__ == "__main__":
    unittest.main()
