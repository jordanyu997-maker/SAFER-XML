import tempfile
import unittest
import json
from pathlib import Path

from tools.android_xml_rag_prompt_contract import (
    audit_prompt_pair,
    build_prompt_pair,
    format_neutral_issues,
    neutral_issue_query,
    prompt_skeleton,
)


class AndroidXmlRagPromptContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.res = Path(self.temp.name) / "res"
        (self.res / "layout").mkdir(parents=True)
        (self.res / "values").mkdir()
        self.layout = self.res / "layout" / "sample.xml"
        self.layout.write_text(
            '<ImageButton xmlns:android="http://schemas.android.com/apk/res/android" '
            'android:id="@+id/action" android:layout_width="40dp" '
            'android:layout_height="40dp" />',
            encoding="utf-8",
        )
        (self.res / "values" / "strings.xml").write_text(
            "<resources></resources>",
            encoding="utf-8",
        )
        self.issue = {
            "code": "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
            "file": str(self.layout),
            "component": "ImageButton",
            "element": "ImageButton",
            "selector": "/ImageButton[1]",
            "severity": "error",
            "repairability": "xml_safe",
            "attributes": {"android:id": "@+id/action"},
            "message": "SECRET_SOLUTION_MESSAGE",
            "repair_query": "SECRET_REPAIR_QUERY",
            "fix_hint": "SECRET_FIX_HINT",
            "related_docs": ["secret.direct.mapping"],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_query_uses_structured_detector_fields_but_not_fix_hint(self):
        query = neutral_issue_query(self.issue)

        self.assertIn("SECRET_SOLUTION_MESSAGE", query)
        self.assertIn("SECRET_REPAIR_QUERY", query)
        self.assertNotIn("SECRET_FIX_HINT", query)

    def test_conditions_differ_only_inside_knowledge_block(self):
        pair = build_prompt_pair([self.issue], self.res, documents=[])

        self.assertEqual(
            prompt_skeleton(pair["no_rag"]),
            prompt_skeleton(pair["rag"]),
        )
        self.assertNotIn("SECRET_SOLUTION_MESSAGE", pair["no_rag"])
        self.assertNotIn("SECRET_REPAIR_QUERY", pair["rag"])
        self.assertTrue(pair["trace"]["direct_detector_mapping_enabled"])
        self.assertTrue(pair["trace"]["query_includes_message"])
        self.assertTrue(pair["trace"]["query_includes_repair_query"])
        self.assertEqual(
            pair["trace"]["dense_backend"],
            "hashed_subword_vector_v1",
        )
        self.assertFalse(pair["trace"]["app_context_retrieval_enabled"])
        self.assertTrue(audit_prompt_pair(pair, [self.issue])["passed"])

    def test_prompt_injection_supports_eight_documents(self):
        documents = []
        for index in range(8):
            documents.append({
                "doc_id": f"android.rule.example-{index}",
                "doc_type": "technique",
                "source": {
                    "title_en": f"Android XML label repair {index}",
                    "title_zh": "",
                },
                "content": {
                    "summary_en": "Android XML ImageButton contentDescription repair.",
                    "summary_zh": "",
                    "requirements_en": [],
                    "requirements_zh": [],
                },
                "tags": {
                    "keywords_en": ["Android", "ImageButton"],
                    "keywords_zh": [],
                    "applies_to": ["android_views"],
                    "issue_codes": [],
                },
                "retrieval": {"search_text_mixed": "Android XML ImageButton label"},
            })

        pair = build_prompt_pair(
            [self.issue],
            self.res,
            documents=documents,
            per_issue_limit=8,
            prompt_limit=8,
        )

        self.assertEqual(pair["trace"]["knowledge_document_count"], 8)
        self.assertEqual(pair["trace"]["effective_per_issue_limit"], 8)
        self.assertEqual(pair["trace"]["effective_prompt_limit"], 8)

    def test_shared_prompt_declares_every_operation_schema(self):
        pair = build_prompt_pair([self.issue], self.res, documents=[])

        for prompt in (pair["no_rag"], pair["rag"]):
            self.assertIn('"op": "set_attribute"', prompt)
            self.assertIn('"op": "remove_attribute"', prompt)
            self.assertIn('"op": "remove_attribute_value"', prompt)
            self.assertIn('"op": "add_string_resource"', prompt)
            self.assertIn('"name": "resource_name"', prompt)
            self.assertIn("must not contain `selector`", prompt)

    def test_nearby_text_label_is_exposed_as_a_bounded_related_target(self):
        layout = self.res / "layout" / "input.xml"
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="@string/phone" />
    <EditText
        android:id="@+id/number"
        android:hint="@string/phone_example"
        android:inputType="phone" />
</LinearLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
            "file": str(layout),
            "component": "EditText",
            "selector": "/LinearLayout[1]/EditText[1]",
            "severity": "error",
            "repairability": "xml_safe",
            "attributes": {
                "id": "@+id/number",
                "hint": "@string/phone_example",
                "inputType": "phone",
            },
        }

        records = json.loads(format_neutral_issues([issue], self.res))
        related = records[0]["related_elements"][0]
        pair = build_prompt_pair([issue], self.res, documents=[])

        self.assertEqual(
            related["selector"], "/LinearLayout[1]/TextView[1]"
        )
        self.assertEqual(related["allowed_attribute"], "android:labelFor")
        self.assertEqual(related["required_value"], "@id/number")
        self.assertIn("Never add, remove, or change android:id", pair["no_rag"])
        self.assertIn('"required_value": "@id/number"', pair["rag"])

    def test_generic_nearby_label_is_not_exposed_as_a_repair_target(self):
        layout = self.res / "layout" / "generic.xml"
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Number" />
    <EditText android:id="@+id/number" android:hint="+1-555-12345" />
</LinearLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT",
            "file": str(layout),
            "component": "EditText",
            "selector": "/LinearLayout[1]/EditText[1]",
            "severity": "error",
            "repairability": "xml_safe",
            "attributes": {"id": "@+id/number"},
        }

        records = json.loads(format_neutral_issues([issue], self.res))

        self.assertNotIn("related_elements", records[0])

    def test_stateful_control_exposes_existing_visible_label_for_label_for(self):
        layout = self.res / "layout" / "spinner.xml"
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Sort order" />
    <Spinner android:id="@+id/sort_order" />
</LinearLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
            "file": str(layout),
            "component": "SelectionControl",
            "selector": "/LinearLayout[1]/Spinner[1]",
            "severity": "error",
            "repairability": "xml_safe",
            "attributes": {"id": "@+id/sort_order"},
        }

        records = json.loads(format_neutral_issues([issue], self.res))
        related = records[0]["related_elements"][0]

        self.assertEqual(related["selector"], "/LinearLayout[1]/TextView[1]")
        self.assertEqual(related["allowed_attribute"], "android:labelFor")
        self.assertEqual(related["required_value"], "@id/sort_order")

    def test_label_one_container_above_input_is_exposed(self):
        layout = self.res / "layout" / "nested_input.xml"
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="Paste lyrics" />
    <ScrollView>
        <EditText android:id="@+id/lyrics" />
    </ScrollView>
</LinearLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            "file": str(layout),
            "component": "EditText",
            "selector": "/LinearLayout[1]/ScrollView[1]/EditText[1]",
            "severity": "error",
            "repairability": "xml_safe",
        }

        records = json.loads(format_neutral_issues([issue], self.res))
        related = records[0]["related_elements"][0]

        self.assertEqual(related["selector"], "/LinearLayout[1]/TextView[1]")
        self.assertEqual(
            related["relationship"],
            "adjacent_container_visible_label_candidate",
        )
        self.assertEqual(related["required_value"], "@id/lyrics")

    def test_unique_label_two_containers_above_input_is_exposed(self):
        layout = self.res / "layout" / "deeply_nested_input.xml"
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <LinearLayout>
        <TextView android:text="Year" />
        <TableLayout>
            <TableRow>
                <Button android:text="-" />
                <EditText android:id="@+id/year" />
                <Button android:text="+" />
            </TableRow>
        </TableLayout>
    </LinearLayout>
</LinearLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            "file": str(layout),
            "component": "EditText",
            "selector": (
                "/LinearLayout[1]/LinearLayout[1]/TableLayout[1]/"
                "TableRow[1]/EditText[1]"
            ),
            "severity": "error",
            "repairability": "xml_safe",
        }

        records = json.loads(format_neutral_issues([issue], self.res))
        related = records[0]["related_elements"][0]

        self.assertEqual(
            related["selector"],
            "/LinearLayout[1]/LinearLayout[1]/TextView[1]",
        )
        self.assertEqual(
            related["relationship"],
            "nested_container_visible_label_candidate",
        )
        self.assertEqual(related["required_value"], "@id/year")

    def test_ambiguous_labels_two_containers_above_are_not_exposed(self):
        layout = self.res / "layout" / "ambiguous_nested_input.xml"
        layout.write_text(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <LinearLayout>
        <TextView android:text="Year" />
        <TextView android:text="Month" />
        <TableLayout>
            <TableRow>
                <EditText android:id="@+id/value" />
            </TableRow>
        </TableLayout>
    </LinearLayout>
</LinearLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            "file": str(layout),
            "component": "EditText",
            "selector": (
                "/LinearLayout[1]/LinearLayout[1]/TableLayout[1]/"
                "TableRow[1]/EditText[1]"
            ),
            "severity": "error",
            "repairability": "xml_safe",
        }

        records = json.loads(format_neutral_issues([issue], self.res))

        self.assertNotIn("related_elements", records[0])

    def test_ancestor_text_input_layout_is_exposed_as_hint_target(self):
        layout = self.res / "layout" / "material_input.xml"
        layout.write_text(
            """<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android">
    <com.google.android.material.textfield.TextInputLayout
        android:id="@+id/passphrase_layout">
        <com.google.android.material.textfield.TextInputEditText
            android:id="@+id/passphrase" />
    </com.google.android.material.textfield.TextInputLayout>
</androidx.constraintlayout.widget.ConstraintLayout>
""",
            encoding="utf-8",
        )
        issue = {
            "code": "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
            "file": str(layout),
            "component": "EditText",
            "selector": "/ConstraintLayout[1]/TextInputLayout[1]/TextInputEditText[1]",
            "severity": "error",
            "repairability": "xml_safe",
        }

        records = json.loads(format_neutral_issues([issue], self.res))
        related = records[0]["related_elements"][0]

        self.assertEqual(related["selector"], "/ConstraintLayout[1]/TextInputLayout[1]")
        self.assertEqual(related["allowed_attribute"], "android:hint")
        self.assertEqual(
            related["allowed_value_kind"],
            "existing_or_added_nonweak_string_resource",
        )


if __name__ == "__main__":
    unittest.main()
