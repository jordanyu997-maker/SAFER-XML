import unittest
import json
import shutil
import tempfile
from pathlib import Path

from tools.generate_android_xml import (
    actionable_issues,
    apply_model_result,
    build_android_repair_prompt,
    evaluate_and_commit_candidate,
    issue_report,
    repair_rate,
    repairable_issues,
    run_xml_checker,
    save_report,
    set_attribute_text,
    should_continue_repair,
    update_no_improvement_streak,
)


class GenerateAndroidXmlTests(unittest.TestCase):
    def make_package(self, xml):
        temp = tempfile.TemporaryDirectory()
        package = Path(temp.name) / "package"
        layout = package / "res/layout"
        values = package / "res/values"
        layout.mkdir(parents=True)
        values.mkdir(parents=True)
        (layout / "screen.xml").write_text(xml, encoding="utf-8")
        (values / "strings.xml").write_text(
            "<resources><string name=\"language\">Language</string></resources>",
            encoding="utf-8",
        )
        self.addCleanup(temp.cleanup)
        return package

    def test_selector_matches_fully_qualified_android_view_class(self):
        xml = """<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android">
    <LinearLayout>
        <androidx.cardview.widget.CardView>
            <androidx.constraintlayout.widget.ConstraintLayout>
                <TextView android:id="@+id/language_label" />
                <Spinner android:id="@+id/language_spinner" />
            </androidx.constraintlayout.widget.ConstraintLayout>
        </androidx.cardview.widget.CardView>
    </LinearLayout>
</androidx.constraintlayout.widget.ConstraintLayout>
"""

        repaired = set_attribute_text(
            xml,
            "/ConstraintLayout[1]/LinearLayout[1]/CardView[1]/"
            "ConstraintLayout[1]/TextView[1]",
            "android:labelFor",
            "@id/language_spinner",
        )

        self.assertIn('android:labelFor="@id/language_spinner"', repaired)
        self.assertIn('android:id="@+id/language_label"', repaired)

    def test_prompt_protects_stateful_control_value_semantics(self):
        prompt = build_android_repair_prompt([], Path("res"), limit=1)

        self.assertIn(
            "do not add a fixed contentDescription",
            prompt,
        )
        self.assertIn(
            "prefer adding android:labelFor",
            prompt,
        )
        self.assertNotIn("/Root[1]/Child[1]", prompt)
        self.assertIn(
            "Only repair issues with Severity: error and Repairability: xml_safe",
            prompt,
        )
        self.assertIn("never hide them as decorative", prompt)

    def test_no_rag_ablation_prompt_does_not_retrieve_knowledge(self):
        prompt = build_android_repair_prompt(
            [], Path("res"), limit=1, use_rag=False
        )

        self.assertIn("RAG retrieval is disabled", prompt)
        self.assertNotIn(
            "Use the retrieved accessibility knowledge as authoritative",
            prompt,
        )

    def test_no_repairability_filter_selects_every_error(self):
        issues = [
            {"code": "A", "severity": "error", "repairability": "xml_safe"},
            {"code": "B", "severity": "error", "repairability": "manual_review"},
            {"code": "C", "severity": "warning", "repairability": "xml_safe"},
        ]

        self.assertEqual(
            [issue["code"] for issue in actionable_issues(issues, False)],
            ["A", "B"],
        )

    def test_selector_accepts_exact_android_id_predicate(self):
        xml = """<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android">
    <LinearLayout>
        <androidx.cardview.widget.CardView>
            <androidx.constraintlayout.widget.ConstraintLayout>
                <TextView android:id="@+id/language_label" />
                <Spinner android:id="@+id/language_spinner" />
            </androidx.constraintlayout.widget.ConstraintLayout>
        </androidx.cardview.widget.CardView>
    </LinearLayout>
</androidx.constraintlayout.widget.ConstraintLayout>
"""

        repaired = set_attribute_text(
            xml,
            "/ConstraintLayout[1]/LinearLayout[1]/CardView[1]/"
            "ConstraintLayout[1]/TextView[@id='@+id/language_label']",
            "android:labelFor",
            "@id/language_spinner",
        )

        self.assertIn('android:labelFor="@id/language_spinner"', repaired)

    def test_operations_are_transactional_when_one_selector_is_invalid(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:id="@+id/label" android:text="@string/language" />
    <Spinner android:id="@+id/language_spinner" />
</LinearLayout>
"""
        )
        path = package / "res/layout/screen.xml"
        before = path.read_text(encoding="utf-8")
        response = json.dumps({
            "operations": [
                {
                    "op": "set_attribute",
                    "path": "res/layout/screen.xml",
                    "selector": "/LinearLayout[1]/TextView[1]",
                    "attribute": "android:labelFor",
                    "value": "@id/language_spinner",
                },
                {
                    "op": "set_attribute",
                    "path": "res/layout/screen.xml",
                    "selector": "/LinearLayout[1]/Spinner[9]",
                    "attribute": "android:minHeight",
                    "value": "48dp",
                },
            ]
        })

        with self.assertRaisesRegex(ValueError, "无法定位"):
            apply_model_result(package, response)

        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_rejects_label_for_that_uses_id_declaration_syntax(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="@string/language" />
    <EditText android:id="@+id/language_input" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@+id/language_input",
            }]
        })

        with self.assertRaisesRegex(ValueError, "不能使用 @\\+id"):
            apply_model_result(package, response)

    def test_rejects_label_for_that_targets_a_missing_id(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="@string/language" />
    <EditText android:id="@+id/language_input" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@id/missing_input",
            }]
        })

        with self.assertRaisesRegex(ValueError, "指向不存在的 id"):
            apply_model_result(package, response)

    def test_rejects_label_for_on_a_non_text_label_source(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView android:id="@+id/icon" />
    <EditText android:id="@+id/language_input" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/ImageView[1]",
                "attribute": "android:labelFor",
                "value": "@id/language_input",
            }]
        })

        with self.assertRaisesRegex(ValueError, "只能设置在可见 TextView"):
            apply_model_result(package, response)

    def test_rejects_non_whitelisted_attribute(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:id="@+id/label" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:visibility",
                "value": "gone",
            }]
        })

        with self.assertRaisesRegex(ValueError, "不允许修改"):
            apply_model_result(package, response)

    def test_rejects_input_type_update_that_drops_existing_flags(self):
        package = self.make_package(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:inputType="text|textCapWords" />
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/EditText[1]",
                "attribute": "android:inputType",
                "value": "textEmailAddress",
            }]
        })

        with self.assertRaisesRegex(ValueError, "丢失了原有输入限制"):
            apply_model_result(package, response)

    def test_allows_input_type_update_that_preserves_existing_flags(self):
        package = self.make_package(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:inputType="text|textNoSuggestions" />
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/EditText[1]",
                "attribute": "android:inputType",
                "value": "textEmailAddress|textNoSuggestions",
            }]
        })

        apply_model_result(package, response)

        repaired = (package / "res/layout/screen.xml").read_text(encoding="utf-8")
        self.assertIn(
            'android:inputType="textEmailAddress|textNoSuggestions"',
            repaired,
        )

    def test_allows_localizing_existing_ime_action_label(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText android:imeActionLabel="Search" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/EditText[1]",
                "attribute": "android:imeActionLabel",
                "value": "@string/language",
            }]
        })

        apply_model_result(package, response)

        repaired = (package / "res/layout/screen.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'android:imeActionLabel="@string/language"', repaired
        )

    def test_rejects_fixed_content_description_on_stateful_control(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <Spinner android:id="@+id/language_spinner" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/Spinner[1]",
                "attribute": "android:contentDescription",
                "value": "@string/language",
            }]
        })

        with self.assertRaisesRegex(ValueError, "状态控件 Spinner"):
            apply_model_result(package, response)

    def test_rejects_fixed_content_description_on_appcompat_seekbar(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <androidx.appcompat.widget.AppCompatSeekBar android:id="@+id/color_value" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/AppCompatSeekBar[1]",
                "attribute": "android:contentDescription",
                "value": "@string/color_value",
            }]
        })

        with self.assertRaisesRegex(ValueError, "状态控件 AppCompatSeekBar"):
            apply_model_result(package, response)

    def test_rejects_hiding_likely_meaningful_logo(self):
        package = self.make_package(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView
        android:id="@+id/startup_logo"
        android:src="@drawable/app_logo" />
</FrameLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/FrameLayout[1]/ImageView[1]",
                "attribute": "android:importantForAccessibility",
                "value": "no",
            }]
        })

        with self.assertRaisesRegex(ValueError, "拒绝隐藏疑似有意义图片"):
            apply_model_result(package, response)

    def test_only_xml_safe_issues_are_actionable(self):
        issues = [
            {"code": "A", "severity": "error", "repairability": "xml_safe"},
            {"code": "B", "severity": "warning", "repairability": "xml_safe"},
            {"code": "C", "severity": "info", "repairability": "xml_safe"},
            {"code": "D", "severity": "error", "repairability": "manual_review"},
            {"code": "E", "repairability": "xml_safe"},
        ]

        self.assertEqual(
            [issue["code"] for issue in repairable_issues(issues)],
            ["A", "E"],
        )

    def test_warning_and_info_do_not_continue_repair_loop(self):
        issues = [
            {"severity": "warning", "repairability": "xml_safe"},
            {"severity": "info", "repairability": "xml_safe"},
        ]

        self.assertFalse(should_continue_repair(issues))
        self.assertEqual(repairable_issues(issues), [])
        self.assertEqual(issue_report(issues)["issue_count"], 0)

    def test_no_improvement_stops_after_two_consecutive_rounds(self):
        streak = update_no_improvement_streak(3, 3, 0)
        self.assertEqual(streak, 1)
        streak = update_no_improvement_streak(3, 3, streak)
        self.assertEqual(streak, 2)
        self.assertEqual(update_no_improvement_streak(3, 2, streak), 0)

    def test_repair_rate_only_uses_error_counts(self):
        self.assertEqual(repair_rate(4, 1), 0.75)
        self.assertIsNone(repair_rate(0, 0))

    def test_saved_report_contains_error_based_counts(self):
        package = self.make_package("<FrameLayout />")
        path = save_report(
            package,
            [
                {"severity": "error"},
                {"severity": "warning"},
                {"severity": "info"},
            ],
        )
        report = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["warning_count"], 1)
        self.assertEqual(report["info_count"], 1)
        self.assertEqual(report["total_issue_count"], 3)
        self.assertEqual(len(report["issues"]), 3)

    def test_candidate_is_committed_only_when_detector_result_improves(self):
        original = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:id="@+id/label" android:text="@string/language" />
    <Spinner android:id="@+id/language_spinner" />
</LinearLayout>
"""
        )
        output = original.parent / "output"
        shutil.copytree(original, output)
        current_issues = [{
            "type": "error",
            "code": "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
        }]
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@id/language_spinner",
            }]
        })

        changed, issues = evaluate_and_commit_candidate(
            output,
            original / "res",
            current_issues,
            response,
        )

        self.assertEqual(issues, [])
        self.assertEqual(
            [path.relative_to(output).as_posix() for path in changed],
            ["res/layout/screen.xml"],
        )
        self.assertIn(
            'android:labelFor="@id/language_spinner"',
            (output / "res/layout/screen.xml").read_text(encoding="utf-8"),
        )

    def test_candidate_without_strict_improvement_is_not_committed(self):
        original = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <Spinner android:id="@+id/language_spinner" />
</LinearLayout>
"""
        )
        output = original.parent / "output_no_improvement"
        shutil.copytree(original, output)
        path = output / "res/layout/screen.xml"
        before = path.read_text(encoding="utf-8")
        current_issues = [{
            "type": "error",
            "code": "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
        }]
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/Spinner[1]",
                "attribute": "android:minHeight",
                "value": "48dp",
            }]
        })

        with self.assertRaisesRegex(ValueError, "没有严格改善"):
            evaluate_and_commit_candidate(
                output,
                original / "res",
                current_issues,
                response,
            )

        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_operation_path_without_res_prefix_is_normalized(self):
        package = self.make_package(
            '<ImageButton xmlns:android="http://schemas.android.com/apk/res/android" />'
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "layout/screen.xml",
                "selector": "/ImageButton[1]",
                "attribute": "android:contentDescription",
                "value": "Save",
            }]
        })

        changed = apply_model_result(package, response)

        self.assertEqual(
            [path.relative_to(package.resolve()).as_posix() for path in changed],
            ["res/layout/screen.xml"],
        )
        self.assertIn(
            'android:contentDescription="Save"',
            (package / "res/layout/screen.xml").read_text(encoding="utf-8"),
        )

    def test_selector_ignores_angle_brackets_inside_xml_comments(self):
        package = self.make_package(
            """<!-- Documentation: <https://example.com/accessibility> -->
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText android:id="@+id/name" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/EditText[1]",
                "attribute": "android:hint",
                "value": "Name",
            }]
        })

        apply_model_result(package, response)

        self.assertIn(
            'android:hint="Name"',
            (package / "res/layout/screen.xml").read_text(encoding="utf-8"),
        )

    def test_string_resource_uses_existing_translatable_file(self):
        package = self.make_package("<LinearLayout />")
        strings = package / "res/values/strings.xml"
        translatable = package / "res/values/translatable.xml"
        strings.rename(translatable)
        response = json.dumps({
            "operations": [{
                "op": "add_string_resource",
                "path": "res/values/strings.xml",
                "name": "save_action",
                "value": "Save",
            }]
        })

        changed = apply_model_result(package, response)

        self.assertEqual(changed, [translatable.resolve()])
        self.assertIn(
            '<string name="save_action">Save</string>',
            translatable.read_text(encoding="utf-8"),
        )
        self.assertFalse(strings.exists())

    def test_string_resource_creates_dedicated_file_when_none_exists(self):
        package = self.make_package("<LinearLayout />")
        (package / "res/values/strings.xml").unlink()
        response = json.dumps({
            "operations": [{
                "op": "add_string_resource",
                "path": "values/strings.xml",
                "name": "save_action",
                "value": "Save",
            }]
        })

        changed = apply_model_result(package, response)
        target = package / "res/values/accessibility_strings.xml"

        self.assertEqual(changed, [target.resolve()])
        self.assertTrue(target.exists())
        self.assertIn(
            '<string name="save_action">Save</string>',
            target.read_text(encoding="utf-8"),
        )

    def test_new_string_resource_file_is_removed_when_transaction_fails(self):
        package = self.make_package("<LinearLayout />")
        (package / "res/values/strings.xml").unlink()
        target = package / "res/values/accessibility_strings.xml"
        response = json.dumps({
            "operations": [{
                "op": "add_string_resource",
                "path": "res/values/strings.xml",
                "name": "invalid_value",
                "value": "A & B",
            }]
        })

        with self.assertRaisesRegex(ValueError, "XML 无法解析"):
            apply_model_result(package, response)

        self.assertFalse(target.exists())

    def test_expanded_profile_drives_detection_and_candidate_validation(self):
        original = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <Button
        android:text="Save"
        android:focusable="false" />
</LinearLayout>
"""
        )
        output = original.parent / "expanded_output"
        shutil.copytree(original, output)

        conservative = run_xml_checker(original / "res")
        expanded = run_xml_checker(
            original / "res",
            detector_profile="expanded_v2",
        )
        self.assertEqual(issue_report(conservative)["error_count"], 0)
        self.assertEqual(issue_report(expanded)["error_count"], 1)
        self.assertEqual(
            [issue["code"] for issue in repairable_issues(expanded)],
            ["ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE"],
        )

        response = json.dumps({
            "operations": [{
                "op": "remove_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/Button[1]",
                "attribute": "android:focusable",
            }]
        })
        changed, remaining = evaluate_and_commit_candidate(
            output,
            original / "res",
            expanded,
            response,
            detector_profile="expanded_v2",
        )

        self.assertEqual(remaining, [])
        self.assertEqual(
            [path.relative_to(output).as_posix() for path in changed],
            ["res/layout/screen.xml"],
        )

    def test_expanded_profile_accepts_email_input_type_repair(self):
        original = self.make_package(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/account_email"
    android:hint="Email address" />
"""
        )
        output = original.parent / "expanded_email_output"
        shutil.copytree(original, output)
        current = run_xml_checker(
            original / "res",
            detector_profile="expanded_v2",
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/EditText[1]",
                "attribute": "android:inputType",
                "value": "textEmailAddress",
            }]
        })

        _, remaining = evaluate_and_commit_candidate(
            output,
            original / "res",
            current,
            response,
            detector_profile="expanded_v2",
        )

        self.assertEqual(issue_report(remaining)["error_count"], 0)

    def test_expanded_v3_accepts_restoring_hidden_standard_control(self):
        original = self.make_package(
            """<Button xmlns:android="http://schemas.android.com/apk/res/android"
    android:text="Save"
    android:importantForAccessibility="no" />
"""
        )
        output = original.parent / "expanded_v3_hidden_output"
        shutil.copytree(original, output)
        current = run_xml_checker(
            original / "res",
            detector_profile="expanded_v3",
        )
        response = json.dumps({
            "operations": [{
                "op": "remove_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/Button[1]",
                "attribute": "android:importantForAccessibility",
            }]
        })

        _, remaining = evaluate_and_commit_candidate(
            output,
            original / "res",
            current,
            response,
            detector_profile="expanded_v3",
        )

        self.assertEqual(issue_report(remaining)["error_count"], 0)

    def test_expanded_v3_accepts_stateful_label_for_repair(self):
        original = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Sort order" />
    <Spinner android:id="@+id/sort_order" />
</LinearLayout>
"""
        )
        output = original.parent / "expanded_v3_stateful_output"
        shutil.copytree(original, output)
        current = run_xml_checker(
            original / "res",
            detector_profile="expanded_v3",
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@id/sort_order",
            }]
        })

        _, remaining = evaluate_and_commit_candidate(
            output,
            original / "res",
            current,
            response,
            detector_profile="expanded_v3",
        )

        self.assertEqual(issue_report(remaining)["error_count"], 0)

    def test_expanded_v3_accepts_switch_compat_label_for_repair(self):
        original = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Keep screen on" />
    <androidx.appcompat.widget.SwitchCompat
        android:id="@+id/keep_screen_on" />
</LinearLayout>
"""
        )
        output = original.parent / "expanded_v3_switch_compat_output"
        shutil.copytree(original, output)
        current = run_xml_checker(
            original / "res",
            detector_profile="expanded_v3",
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@id/keep_screen_on",
            }]
        })

        _, remaining = evaluate_and_commit_candidate(
            output,
            original / "res",
            current,
            response,
            detector_profile="expanded_v3",
        )

        self.assertEqual(issue_report(remaining)["error_count"], 0)


if __name__ == "__main__":
    unittest.main()
