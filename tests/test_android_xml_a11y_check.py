import tempfile
import unittest
from pathlib import Path

from tools.evaluation.android_xml_a11y_check import (
    build_report,
    normalize_view_type,
    scan,
)


class AndroidXmlA11yCheckTests(unittest.TestCase):
    def scan_xml(self, xml, detector_profile="conservative_v1"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        layout = Path(temp.name) / "screen.xml"
        layout.write_text(xml, encoding="utf-8")
        return scan([layout], detector_profile=detector_profile)

    def scan_package(
        self,
        xml,
        values_files=None,
        detector_profile="conservative_v1",
    ):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        res = Path(temp.name) / "res"
        layout_dir = res / "layout"
        layout_dir.mkdir(parents=True)
        (layout_dir / "screen.xml").write_text(xml, encoding="utf-8")
        for relative_path, content in (values_files or {}).items():
            target = res / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return scan([res], detector_profile=detector_profile)

    def test_view_type_normalization_supports_library_and_custom_variants(self):
        self.assertEqual(normalize_view_type("MaterialImageButton"), "ImageButton")
        self.assertEqual(normalize_view_type("com.example.MyImageButton"), "ImageButton")
        self.assertEqual(normalize_view_type("AppCompatButton"), "Button")
        self.assertEqual(normalize_view_type("com.example.MyEditText"), "EditText")
        self.assertEqual(normalize_view_type("AppCompatSpinner"), "SelectionControl")

    def test_label_for_can_name_stateful_controls(self):
        for widget in [
            "Spinner",
            "SeekBar",
            "RatingBar",
            "Switch",
            "CheckBox",
        ]:
            with self.subTest(widget=widget):
                issues = self.scan_xml(
                    f"""<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView
        android:text="@string/control_label"
        android:labelFor="@id/control" />
    <{widget}
        android:id="@+id/control"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content" />
</LinearLayout>
"""
                )

                codes = [issue["code"] for issue in issues]
                self.assertNotIn("ANDROID_XML_LABELFOR_TARGET_NOT_INPUT", codes)
                self.assertNotIn("ANDROID_XML_MISSING_ACCESSIBLE_NAME", codes)
                self.assertFalse(
                    any(issue["severity"] == "error" for issue in issues)
                )

    def test_label_for_still_warns_for_noninteractive_container(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView
        android:text="@string/section"
        android:labelFor="@id/section_container" />
    <LinearLayout
        android:id="@+id/section_container"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content" />
</LinearLayout>
"""
        )

        self.assertIn(
            "ANDROID_XML_LABELFOR_TARGET_NOT_INPUT",
            [issue["code"] for issue in issues],
        )

    def test_missing_label_for_target_is_error(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView
        android:text="@string/language"
        android:labelFor="@id/missing_spinner" />
</LinearLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_LABELFOR_TARGET_MISSING"
        )
        self.assertEqual(issue["severity"], "error")

    def test_label_for_names_edit_text_without_hint(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView
        android:text="@string/email"
        android:labelFor="@id/email" />
    <EditText android:id="@+id/email" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            [issue["code"] for issue in issues],
        )

    def test_explicitly_disabled_password_autofill_is_not_overridden(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView
        android:text="@string/password"
        android:labelFor="@id/password" />
    <EditText
        android:id="@+id/password"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:importantForAutofill="no"
        android:inputType="textPassword" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_PASSWORD_AUTOFILL_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_meaningful_logo_requires_manual_review(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView
        android:id="@+id/startup_logo"
        android:src="@drawable/app_logo" />
</FrameLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION"
        )
        self.assertEqual(issue["repairability"], "manual_review")

    def test_ambiguous_image_requires_manual_review(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView
        android:id="@+id/hero_art"
        android:src="@drawable/illustration" />
</FrameLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_IMAGE_SEMANTICS_REQUIRES_REVIEW"
        )
        self.assertEqual(issue["repairability"], "manual_review")
        self.assertEqual(issue["severity"], "warning")
        self.assertTrue(issue["requires_review"])
        self.assertIn("建议人工复核", issue["fix_hint"])

    def test_bitmap_name_does_not_match_map_semantics(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView
        android:id="@+id/bitmap_preview"
        android:src="@drawable/bitmap_placeholder" />
</FrameLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION",
            [issue["code"] for issue in issues],
        )

    def test_unlabeled_spinner_without_visible_label_is_not_xml_safe(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <Spinner android:id="@+id/community_spinner" />
</FrameLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_MISSING_ACCESSIBLE_NAME"
        )
        self.assertEqual(issue["repairability"], "requires_structure_or_code")

    def test_spinner_with_one_visible_sibling_label_is_xml_safe(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Community" />
    <Spinner android:id="@+id/community_spinner" />
</LinearLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_MISSING_ACCESSIBLE_NAME"
        )
        self.assertEqual(issue["repairability"], "xml_safe")

    def test_spinner_with_ambiguous_sibling_labels_is_not_xml_safe(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Community" />
    <TextView android:text="Sort order" />
    <Spinner android:id="@+id/community_spinner" />
</LinearLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_MISSING_ACCESSIBLE_NAME"
        )
        self.assertEqual(issue["repairability"], "requires_structure_or_code")

    def test_location_name_does_not_trigger_person_name_autofill(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText
        android:id="@+id/location_name_query"
        android:hint="Name of place" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_NAME_AUTOFILL_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_text_person_name_input_type_is_sufficient_for_static_purpose_check(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText
        android:id="@+id/contact"
        android:hint="Contact"
        android:inputType="textPersonName" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_NAME_AUTOFILL_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_field_terms_use_token_boundaries(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText android:id="@+id/askSusiMessage" android:hint="Message" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_exact_age_field_still_triggers_number_check(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText android:id="@+id/userAge" android:hint="Age" />
</LinearLayout>
"""
        )

        self.assertIn(
            "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_phone_input_does_not_trigger_generic_number_rule(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText
        android:id="@+id/phone_number"
        android:hint="Phone number"
        android:inputType="phone" />
</LinearLayout>
"""
        )

        codes = [issue["code"] for issue in issues]
        self.assertNotIn("ANDROID_XML_PHONE_INPUTTYPE_MISSING", codes)
        self.assertNotIn("ANDROID_XML_NUMBER_INPUTTYPE_MISSING", codes)

    def test_text_input_layout_hint_names_child_input(self):
        issues = self.scan_xml(
            """<com.google.android.material.textfield.TextInputLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:hint="@string/password">
    <FrameLayout>
        <com.google.android.material.textfield.TextInputEditText
            android:id="@+id/password"
            android:inputType="textPassword" />
    </FrameLayout>
</com.google.android.material.textfield.TextInputLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            [issue["code"] for issue in issues],
        )

    def test_exposed_dropdown_with_no_keyboard_input_still_uses_parent_hint(self):
        issues = self.scan_xml(
            """<com.google.android.material.textfield.TextInputLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:hint="@string/category">
    <com.google.android.material.textfield.MaterialAutoCompleteTextView
        android:id="@+id/category"
        android:inputType="none" />
</com.google.android.material.textfield.TextInputLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            [issue["code"] for issue in issues],
        )

    def test_strings_in_any_values_file_and_explicit_style_are_resolved(self):
        issues = self.scan_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText
        android:id="@+id/email"
        style="@style/AccessibleInput"
        android:inputType="textEmailAddress" />
</LinearLayout>
""",
            {
                "values/labels.xml": """<resources>
    <string name="email_label">Email address</string>
</resources>
""",
                "values/component_styles.xml": """<resources>
    <style name="BaseInput">
        <item name="android:hint">@string/email_label</item>
    </style>
    <style name="AccessibleInput" parent="@style/BaseInput" />
</resources>
""",
            },
        )

        codes = [issue["code"] for issue in issues]
        self.assertNotIn("ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT", codes)
        self.assertNotIn("ANDROID_XML_EMAIL_INPUTTYPE_MISSING", codes)

    def test_default_values_take_priority_over_localized_values(self):
        issues = self.scan_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText android:id="@+id/message" android:hint="@string/field_label" />
</LinearLayout>
""",
            {
                "values/labels.xml": "<resources><string name=\"field_label\">Message</string></resources>",
                "values-zh/strings.xml": "<resources><string name=\"field_label\">Age</string></resources>",
            },
        )

        self.assertNotIn(
            "ANDROID_XML_NUMBER_INPUTTYPE_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_appcompat_image_button_is_treated_as_interactive(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <androidx.appcompat.widget.AppCompatImageButton
        android:id="@+id/save_button"
        android:src="@drawable/ic_save" />
</FrameLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_MISSING_ACCESSIBLE_NAME"
        )
        self.assertEqual(issue["severity"], "error")
        self.assertGreaterEqual(issue["confidence"], 0.8)

    def test_appcompat_src_compat_participates_in_image_semantics(self):
        issues = self.scan_xml(
            """<FrameLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto">
    <androidx.appcompat.widget.AppCompatImageView
        android:id="@+id/brand_mark"
        app:srcCompat="@drawable/company_logo" />
</FrameLayout>
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_MEANINGFUL_IMAGE_MISSING_DESCRIPTION"
        )
        self.assertEqual(issue["repairability"], "manual_review")

    def test_read_only_edit_text_is_not_treated_as_editable_field(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <EditText
        android:id="@+id/file_content"
        android:editable="false"
        android:focusable="false" />
</FrameLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            [issue["code"] for issue in issues],
        )

    def test_clickable_container_can_use_descendant_visible_text_as_name(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:clickable="true">
    <TextView android:text="@string/open_settings" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
            [issue["code"] for issue in issues],
        )

    def test_explicit_null_and_decorative_images_do_not_create_findings(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView
        android:id="@+id/illustration"
        android:contentDescription="@null"
        android:src="@drawable/header_art" />
    <ImageView
        android:id="@+id/background"
        android:src="@drawable/screen_bg" />
</LinearLayout>
"""
        )

        image_codes = {
            issue["code"]
            for issue in issues
            if "IMAGE" in issue["code"]
        }
        self.assertEqual(image_codes, set())

    def test_important_for_accessibility_no_suppresses_image_error(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageView
        android:importantForAccessibility="no"
        android:clickable="true"
        android:src="@drawable/icon" />
</FrameLayout>
"""
        )

        self.assertFalse(
            any(issue["severity"] == "error" for issue in issues),
        )

    def test_explicit_empty_image_button_description_suppresses_error(self):
        for value in ("@null", ""):
            with self.subTest(value=value):
                issues = self.scan_xml(
                    f"""<ImageButton
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:contentDescription="{value}"
    android:src="@drawable/icon" />
"""
                )
                self.assertFalse(
                    any(issue["severity"] == "error" for issue in issues),
                )

    def test_tools_ignore_content_description_is_respected(self):
        issues = self.scan_xml(
            """<FrameLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">
    <ImageView
        android:src="@drawable/illustration"
        tools:ignore="ContentDescription" />
</FrameLayout>
"""
        )

        self.assertFalse(any("IMAGE" in issue["code"] for issue in issues))

    def test_touch_target_requires_both_static_dimensions(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <ImageButton
        android:contentDescription="@string/action"
        android:layout_width="24dp"
        android:layout_height="wrap_content" />
    <ImageButton
        android:contentDescription="@string/action"
        android:layout_width="24dp"
        android:layout_height="24dp" />
</LinearLayout>
"""
        )

        touch_issues = [
            issue for issue in issues
            if issue["code"] == "ANDROID_XML_TOUCH_TARGET_TOO_SMALL"
        ]
        self.assertEqual(len(touch_issues), 1)
        self.assertEqual(touch_issues[0]["repairability"], "manual_review")
        self.assertEqual(touch_issues[0]["severity"], "warning")

    def test_minimum_touch_dimensions_suppress_size_finding(self):
        issues = self.scan_xml(
            """<ImageButton
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:contentDescription="@string/action"
    android:layout_width="24dp"
    android:layout_height="24dp"
    android:minWidth="48dp"
    android:minHeight="48dp" />
"""
        )

        self.assertFalse(
            any(issue["code"].startswith("ANDROID_XML_TOUCH_TARGET") for issue in issues)
        )

    def test_resolved_dimen_is_used_for_touch_target_warning(self):
        issues = self.scan_package(
            """<ImageButton
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:contentDescription="@string/action"
    android:layout_width="@dimen/icon_size"
    android:layout_height="@dimen/icon_size" />
""",
            {
                "values/dimens.xml": (
                    "<resources><dimen name=\"icon_size\">24dp</dimen></resources>"
                ),
            },
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_TOUCH_TARGET_TOO_SMALL"
        )
        self.assertEqual(issue["severity"], "warning")

    def test_unresolved_dimen_is_info_and_requires_review(self):
        issues = self.scan_xml(
            """<ImageButton
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:contentDescription="@string/action"
    android:layout_width="@dimen/missing_size"
    android:layout_height="@dimen/missing_size" />
"""
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_TOUCH_TARGET_SIZE_REQUIRES_REVIEW"
        )
        self.assertEqual(issue["severity"], "info")
        self.assertTrue(issue["requires_review"])
        self.assertNotEqual(issue["type"], "error")

    def test_report_issue_count_only_counts_errors_and_supports_legacy_issues(self):
        report = build_report([
            {"type": "warning"},
            {"severity": "info", "type": "info"},
            {"code": "LEGACY_WITHOUT_SEVERITY"},
        ])

        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["warning_count"], 1)
        self.assertEqual(report["info_count"], 1)
        self.assertEqual(report["total_issue_count"], 3)

    def test_every_issue_contains_required_metadata(self):
        issues = self.scan_xml(
            """<ImageButton xmlns:android="http://schemas.android.com/apk/res/android" />
"""
        )

        required = {
            "id",
            "type",
            "severity",
            "confidence",
            "requires_review",
            "component",
            "message",
            "fix_hint",
        }
        self.assertTrue(issues)
        self.assertTrue(all(required <= set(issue) for issue in issues))

    def test_short_repeated_specific_label_is_not_treated_as_generic(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <Button android:text="GitHub" />
    <Button android:text="GitHub" />
</LinearLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_REPEATED_GENERIC_LABEL",
            [issue["code"] for issue in issues],
        )

    def test_repeated_generic_label_under_same_parent_requires_review(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <Button android:text="Delete" />
    <Button android:text="Delete" />
</LinearLayout>
"""
        )

        repeated = [
            issue for issue in issues
            if issue["code"] == "ANDROID_XML_REPEATED_GENERIC_LABEL"
        ]
        self.assertEqual(len(repeated), 2)
        self.assertTrue(all(issue["repairability"] == "manual_review" for issue in repeated))

    def test_noninteractive_custom_container_is_not_automatically_flagged(self):
        issues = self.scan_xml(
            """<com.example.BottomSheetLayout
    xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="@string/title" />
</com.example.BottomSheetLayout>
"""
        )

        self.assertNotIn(
            "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW",
            [issue["code"] for issue in issues],
        )

    def test_clickable_custom_view_still_requires_review(self):
        issues = self.scan_xml(
            """<com.example.ActionSurface
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:clickable="true"
    android:contentDescription="@string/action" />
"""
        )

        self.assertIn(
            "ANDROID_XML_CUSTOM_VIEW_REQUIRES_ACCESSIBILITY_REVIEW",
            [issue["code"] for issue in issues],
        )

    def test_expanded_profile_promotes_weak_input_with_stable_purpose(self):
        xml = """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/email"
    android:hint="Input"
    android:inputType="textEmailAddress" />
"""
        conservative = self.scan_xml(xml)
        expanded = self.scan_xml(xml, detector_profile="expanded_v2")

        conservative_issue = next(
            issue for issue in conservative
            if issue["code"] == "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT"
        )
        expanded_issue = next(
            issue for issue in expanded
            if issue["code"] == "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT"
        )
        self.assertEqual(conservative_issue["severity"], "warning")
        self.assertEqual(expanded_issue["severity"], "error")
        self.assertEqual(expanded_issue["repairability"], "xml_safe")
        self.assertFalse(expanded_issue["requires_review"])

    def test_expanded_profile_keeps_weak_input_without_purpose_as_warning(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/field"
    android:hint="Input" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT"
        )
        self.assertEqual(issue["severity"], "warning")
        self.assertTrue(issue["requires_review"])

    def test_strong_label_for_takes_precedence_over_example_hint(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Phone number" android:labelFor="@id/number" />
    <EditText
        android:id="@+id/number"
        android:hint="+1-555-12345"
        android:inputType="phone" />
</LinearLayout>
""",
            detector_profile="expanded_v2",
        )

        self.assertNotIn(
            "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
            [issue["code"] for issue in issues],
        )

    def test_generic_label_for_does_not_hide_a_weak_input_name(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Number" android:labelFor="@id/number" />
    <EditText
        android:id="@+id/number"
        android:hint="+1-555-12345"
        android:inputType="phone" />
</LinearLayout>
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT"
        )
        self.assertEqual(issue["severity"], "error")

    def test_expanded_profile_does_not_treat_generic_number_type_as_purpose(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/editTextNumber"
    android:text="1"
    android:inputType="number" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT"
        )
        self.assertEqual(issue["severity"], "warning")

    def test_expanded_profile_promotes_standard_control_focus_block(self):
        issues = self.scan_xml(
            """<Button xmlns:android="http://schemas.android.com/apk/res/android"
    android:text="Save"
    android:focusable="false" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE"
        )
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["repairability"], "xml_safe")
        self.assertGreaterEqual(issue["confidence"], 0.8)

    def test_expanded_v3_splits_missing_name_by_component_semantics(self):
        cases = [
            (
                '<ImageButton xmlns:android="http://schemas.android.com/apk/res/android" />',
                "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME",
            ),
            (
                '<Button xmlns:android="http://schemas.android.com/apk/res/android" />',
                "ANDROID_XML_BUTTON_MISSING_ACCESSIBLE_NAME",
            ),
            (
                '<ImageView xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:clickable="true" />',
                "ANDROID_XML_INTERACTIVE_IMAGE_MISSING_ACCESSIBLE_NAME",
            ),
            (
                '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:clickable="true" />',
                "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME",
            ),
        ]
        for xml, expected in cases:
            with self.subTest(expected=expected):
                issues = self.scan_xml(xml, detector_profile="expanded_v3")
                self.assertIn(expected, [issue["code"] for issue in issues])
                self.assertNotIn(
                    "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
                    [issue["code"] for issue in issues],
                )

    def test_expanded_v3_splits_xml_safe_stateful_control_label(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Sort order" />
    <Spinner android:id="@+id/sort_order" />
</LinearLayout>
""",
            detector_profile="expanded_v3",
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL"
        )
        self.assertEqual(issue["repairability"], "xml_safe")

    def test_expanded_v3_requires_existing_id_for_stateful_label_repair(self):
        issues = self.scan_xml(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Sort order" />
    <Spinner />
</LinearLayout>
""",
            detector_profile="expanded_v3",
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL"
        )
        self.assertEqual(issue["repairability"], "requires_structure_or_code")

    def test_expanded_v3_does_not_share_one_label_across_stateful_controls(self):
        issues = self.scan_xml(
            """<TableRow xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Owner" />
    <CheckBox android:id="@+id/read_owner" />
    <CheckBox android:id="@+id/write_owner" />
    <CheckBox android:id="@+id/execute_owner" />
</TableRow>
""",
            detector_profile="expanded_v3",
        )

        stateful_issues = [
            item
            for item in issues
            if item["code"] == "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL"
        ]
        self.assertEqual(len(stateful_issues), 3)
        self.assertTrue(all(
            item["repairability"] == "requires_structure_or_code"
            for item in stateful_issues
        ))
        self.assertTrue(all(item["requires_review"] for item in stateful_issues))
        self.assertTrue(all("唯一、无歧义" in item["message"] for item in stateful_issues))

    def test_expanded_v2_keeps_legacy_missing_name_code(self):
        issues = self.scan_xml(
            '<ImageButton xmlns:android="http://schemas.android.com/apk/res/android" />',
            detector_profile="expanded_v2",
        )

        self.assertIn(
            "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
            [issue["code"] for issue in issues],
        )

    def test_expanded_v3_can_safely_restore_standard_hidden_control(self):
        issues = self.scan_xml(
            """<Button xmlns:android="http://schemas.android.com/apk/res/android"
    android:text="Save"
    android:importantForAccessibility="no" />
""",
            detector_profile="expanded_v3",
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY"
        )
        self.assertEqual(issue["repairability"], "xml_safe")
        self.assertFalse(issue["requires_review"])
        self.assertIn("移除", issue["fix_hint"])

    def test_expanded_v3_does_not_auto_restore_custom_hidden_control(self):
        issues = self.scan_xml(
            """<com.example.CustomButton xmlns:android="http://schemas.android.com/apk/res/android"
    android:importantForAccessibility="no" />
""",
            detector_profile="expanded_v3",
        )

        issue = next(
            item
            for item in issues
            if item["code"] == "ANDROID_XML_INTERACTIVE_HIDDEN_FROM_ACCESSIBILITY"
        )
        self.assertEqual(issue["repairability"], "requires_structure_or_code")
        self.assertTrue(issue["requires_review"])

    def test_expanded_profile_does_not_promote_disabled_focus_block(self):
        issues = self.scan_xml(
            """<Button xmlns:android="http://schemas.android.com/apk/res/android"
    android:text="Unavailable"
    android:enabled="false"
    android:focusable="false" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE"
        )
        self.assertEqual(issue["severity"], "warning")

    def test_expanded_profile_promotes_explicit_password_field(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/account_password"
    android:hint="Password" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING"
        )
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["repairability"], "xml_safe")

    def test_expanded_profile_promotes_explicit_email_field(self):
        xml = """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/account_email"
    android:hint="Email address" />
"""
        conservative = self.scan_xml(xml)
        expanded = self.scan_xml(xml, detector_profile="expanded_v2")

        conservative_issue = next(
            issue for issue in conservative
            if issue["code"] == "ANDROID_XML_EMAIL_INPUTTYPE_MISSING"
        )
        expanded_issue = next(
            issue for issue in expanded
            if issue["code"] == "ANDROID_XML_EMAIL_INPUTTYPE_MISSING"
        )
        self.assertEqual(conservative_issue["severity"], "warning")
        self.assertEqual(expanded_issue["severity"], "error")
        self.assertEqual(expanded_issue["repairability"], "xml_safe")

    def test_expanded_profile_keeps_hint_only_email_as_warning(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/query"
    android:hint="Email address" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_EMAIL_INPUTTYPE_MISSING"
        )
        self.assertEqual(issue["severity"], "warning")

    def test_expanded_profile_promotes_explicit_phone_field(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/contact_phone"
    android:hint="Phone" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_PHONE_INPUTTYPE_MISSING"
        )
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["repairability"], "xml_safe")

    def test_expanded_profile_promotes_specific_numeric_purpose(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/user_age"
    android:hint="Age" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_NUMBER_INPUTTYPE_MISSING"
        )
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["repairability"], "xml_safe")

    def test_expanded_profile_keeps_generic_number_field_as_warning(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/number"
    android:hint="Number" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_NUMBER_INPUTTYPE_MISSING"
        )
        self.assertEqual(issue["severity"], "warning")

    def test_expanded_profile_keeps_hint_only_password_evidence_as_warning(self):
        issues = self.scan_xml(
            """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/field"
    android:hint="Password" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING"
        )
        self.assertEqual(issue["severity"], "warning")
        self.assertTrue(issue["requires_review"])

    def test_expanded_profile_does_not_promote_password_parameter_fields(self):
        for field_id in ["password_length_text", "password_separator_text"]:
            with self.subTest(field_id=field_id):
                issues = self.scan_xml(
                    f"""<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/{field_id}"
    android:hint="Password setting" />
""",
                    detector_profile="expanded_v2",
                )

                issue = next(
                    item for item in issues
                    if item["code"] == "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING"
                )
                self.assertEqual(issue["severity"], "warning")
                self.assertTrue(issue["requires_review"])

    def test_legacy_password_attribute_suppresses_missing_input_type(self):
        xml = """<EditText xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/account_password"
    android:password="true" />
"""
        conservative = self.scan_xml(xml)
        issues = self.scan_xml(
            xml,
            detector_profile="expanded_v2",
        )

        conservative_issue = next(
            issue for issue in conservative
            if issue["code"] == "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING"
        )
        self.assertEqual(conservative_issue["severity"], "warning")
        self.assertNotIn(
            "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING",
            [issue["code"] for issue in issues],
        )

    def test_expanded_profile_keeps_empty_focus_container_as_warning(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:focusable="true" />
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_UNNAMED_FOCUSABLE_CONTAINER"
        )
        self.assertEqual(issue["severity"], "warning")
        self.assertEqual(issue["repairability"], "xml_safe")

    def test_expanded_profile_keeps_focus_group_with_text_as_warning(self):
        issues = self.scan_xml(
            """<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:focusable="true">
    <TextView android:text="Summary" />
</FrameLayout>
""",
            detector_profile="expanded_v2",
        )

        issue = next(
            item for item in issues
            if item["code"] == "ANDROID_XML_UNNAMED_FOCUSABLE_CONTAINER"
        )
        self.assertEqual(issue["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
