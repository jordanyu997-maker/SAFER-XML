import json
import tempfile
import unittest
from pathlib import Path

from tools.android_xml_contract_v2_1 import apply_model_result


class AndroidXmlContractV21Tests(unittest.TestCase):
    def make_package(self, xml):
        temp = tempfile.TemporaryDirectory()
        package = Path(temp.name) / "package"
        layout = package / "res/layout"
        values = package / "res/values"
        layout.mkdir(parents=True)
        values.mkdir(parents=True)
        (layout / "screen.xml").write_text(xml, encoding="utf-8")
        (values / "strings.xml").write_text(
            '<resources><string name="choice">Choice</string></resources>',
            encoding="utf-8",
        )
        self.addCleanup(temp.cleanup)
        return package

    def test_allows_visible_text_label_for_existing_radio_button(self):
        package = self.make_package(
            """<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:text="@string/choice" />
    <RadioButton android:id="@+id/choice" />
</LinearLayout>
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/LinearLayout[1]/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@id/choice",
            }]
        })

        apply_model_result(package, response)

        repaired = (package / "res/layout/screen.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn('android:labelFor="@id/choice"', repaired)

    def test_still_rejects_fixed_radio_button_content_description(self):
        package = self.make_package(
            """<RadioButton
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/choice" />
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/RadioButton[1]",
                "attribute": "android:contentDescription",
                "value": "@string/choice",
            }]
        })

        with self.assertRaisesRegex(ValueError, "状态控件 RadioButton"):
            apply_model_result(package, response)

    def test_still_rejects_label_for_missing_target(self):
        package = self.make_package(
            """<TextView
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:text="@string/choice" />
"""
        )
        response = json.dumps({
            "operations": [{
                "op": "set_attribute",
                "path": "res/layout/screen.xml",
                "selector": "/TextView[1]",
                "attribute": "android:labelFor",
                "value": "@id/missing",
            }]
        })

        with self.assertRaisesRegex(ValueError, "指向不存在的 id"):
            apply_model_result(package, response)


if __name__ == "__main__":
    unittest.main()
