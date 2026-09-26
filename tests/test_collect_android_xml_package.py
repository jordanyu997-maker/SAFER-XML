import tempfile
import unittest
from pathlib import Path

from tools.evaluation.collect_android_xml_package import collect


class CollectAndroidXmlPackageTests(unittest.TestCase):
    def test_selected_layouts_include_recursive_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            res = root / "source/app/src/main/res"
            layout = res / "layout"
            values = res / "values"
            layout.mkdir(parents=True)
            values.mkdir(parents=True)
            (layout / "activity_main.xml").write_text(
                '<FrameLayout><include layout="@layout/content_main" /></FrameLayout>',
                encoding="utf-8",
            )
            (layout / "content_main.xml").write_text(
                '<FrameLayout><include layout="@layout/shared_toolbar" /></FrameLayout>',
                encoding="utf-8",
            )
            (layout / "shared_toolbar.xml").write_text(
                "<FrameLayout />",
                encoding="utf-8",
            )
            (layout / "unselected.xml").write_text("<FrameLayout />", encoding="utf-8")
            (values / "strings.xml").write_text("<resources />", encoding="utf-8")
            output = root / "output"

            _, copied = collect(
                root / "source",
                output,
                selected_layouts={"activity_main"},
            )

            relative = {
                path.relative_to(output.resolve()).as_posix()
                for path in copied
            }
            self.assertIn("res/layout/activity_main.xml", relative)
            self.assertIn("res/layout/content_main.xml", relative)
            self.assertIn("res/layout/shared_toolbar.xml", relative)
            self.assertIn("res/values/strings.xml", relative)
            self.assertNotIn("res/layout/unselected.xml", relative)

    def test_missing_selected_layout_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source/app/src/main/res/layout").mkdir(parents=True)

            with self.assertRaisesRegex(FileNotFoundError, "missing"):
                collect(
                    root / "source",
                    root / "output",
                    selected_layouts={"missing"},
                )


if __name__ == "__main__":
    unittest.main()
