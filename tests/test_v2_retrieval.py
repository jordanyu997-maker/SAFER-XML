import tempfile
import unittest
from pathlib import Path

from tools.retrieval.app_context import (
    retrieve_app_context,
    retrieve_app_context_for_issues,
)
from tools.retrieval.search_documents import load_documents
from tools.retrieval.v2_hybrid import (
    HashedSubwordVectorBackend,
    direct_document_ids,
    eligible_for_android_xml,
    eligible_for_issue_query,
    infer_metadata,
    retrieve,
    retrieve_for_issues,
)


def document(doc_id, title, summary, url="local"):
    source = {"title_en": title, "title_zh": ""}
    if url != "local":
        source["standard_url"] = url
    return {
        "doc_id": doc_id,
        "doc_type": "technique",
        "source": source,
        "content": {
            "summary_en": summary,
            "summary_zh": "",
            "requirements_en": [],
            "requirements_zh": [],
        },
        "tags": {"keywords_en": [], "keywords_zh": [], "applies_to": []},
        "retrieval": {"search_text_mixed": f"{title} {summary}"},
    }


class FakeDenseBackend:
    def score(self, query, texts):
        return [1.0 if "special semantic match" in text else 0.0 for text in texts]


class V2RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.direct = document(
            "android.rule.content-labels",
            "Android content labels",
            "Android XML ImageButton contentDescription and TalkBack labels.",
            "https://developer.android.com/guide/topics/ui/accessibility/principles",
        )
        self.android_extra = document(
            "android.fix.image-button",
            "Image button repair",
            "Android XML ImageButton accessible name action label.",
        )
        self.semantic_extra = document(
            "android.context.semantic",
            "Context repair",
            "Android XML special semantic match for an icon action.",
        )
        self.web_only = document(
            "pattern.web-dialog",
            "ARIA dialog",
            "HTML DOM ARIA modal web page pattern.",
        )
        self.compose_only = document(
            "android.compose.only",
            "Compose semantics",
            "Android Compose Modifier semantics contentDescription.",
        )

    def test_metadata_filters_web_and_compose_only_documents(self):
        self.assertTrue(eligible_for_android_xml(self.direct))
        self.assertFalse(eligible_for_android_xml(self.web_only))
        self.assertFalse(eligible_for_android_xml(self.compose_only))
        self.assertEqual(
            infer_metadata(self.direct)["source_authority"],
            "official_android",
        )

    def test_v2_retrieval_keeps_direct_mapping_and_never_pads_to_sixteen(self):
        results = retrieve(
            "Android XML ImageButton missing accessible action label",
            [
                self.direct,
                self.android_extra,
                self.semantic_extra,
                self.web_only,
                self.compose_only,
            ],
            related_doc_ids=[self.direct["doc_id"]],
            final_limit=3,
        )

        self.assertEqual(results[0]["doc_id"], self.direct["doc_id"])
        self.assertEqual(results[0]["reason"], "direct_issue_mapping")
        self.assertLessEqual(len(results), 3)
        self.assertNotIn(self.web_only["doc_id"], [item["doc_id"] for item in results])
        self.assertNotIn(
            self.compose_only["doc_id"], [item["doc_id"] for item in results]
        )

    def test_dense_backend_is_explicit_and_recorded(self):
        results = retrieve(
            "unknown icon purpose",
            [self.android_extra, self.semantic_extra],
            dense_backend=FakeDenseBackend(),
            lexical_weight=0.2,
            final_limit=1,
        )

        self.assertEqual(results[0]["doc_id"], self.semantic_extra["doc_id"])
        self.assertEqual(results[0]["reason"], "hybrid")
        self.assertIsNotNone(results[0]["dense_score"])

    def test_local_hashed_vector_backend_prefers_matching_component(self):
        backend = HashedSubwordVectorBackend()

        scores = backend.score(
            "Android XML ImageButton contentDescription",
            [
                "Android XML ImageButton contentDescription accessible label",
                "Android RecyclerView pagination and network cache",
            ],
        )

        self.assertGreater(scores[0], scores[1])

    def test_issue_routes_precede_detector_fallback_documents(self):
        ids = direct_document_ids({
            "code": "ANDROID_XML_STATEFUL_CONTROL_MISSING_LABEL",
            "related_docs": ["android.rule.forms-errors"],
        })

        self.assertEqual(ids[0], "android.pattern.settings-controls")
        self.assertIn("android.rule.forms-errors", ids)

    def test_missing_clickable_name_routes_to_labeling_not_perform_click(self):
        ids = direct_document_ids({
            "code": "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME",
        })

        self.assertEqual(ids[0], "android.fixmap.content-labeling")
        self.assertIn("android.rule.content-labels", ids)
        self.assertNotIn("android.fixmap.clickable-view-accessibility", ids)

    def test_missing_clickable_name_excludes_perform_click_from_hybrid_results(self):
        labeling = document(
            "android.fixmap.content-labeling",
            "Content labeling",
            "Clickable Android View missing contentDescription accessible name.",
        )
        wrong = document(
            "android.fixmap.clickable-view-accessibility",
            "Clickable View accessibility",
            "Clickable Android View performClick and touch handling.",
        )
        results = retrieve_for_issues(
            [{
                "code": "ANDROID_XML_CLICKABLE_VIEW_MISSING_ACCESSIBLE_NAME",
                "component": "IconTextView",
            }],
            [wrong, labeling],
            per_issue_limit=2,
            prompt_limit=2,
        )

        self.assertEqual([item["doc_id"] for item in results], [labeling["doc_id"]])

    def test_issue_specific_documents_do_not_cross_contaminate_queries(self):
        email = document(
            "android.fix.email",
            "Email input repair",
            "Android XML textEmailAddress inputType.",
        )
        email["tags"]["issue_codes"] = ["ANDROID_XML_EMAIL_INPUTTYPE_MISSING"]
        focus = document(
            "android.fix.focus",
            "Focusable control repair",
            "Android XML focusable false keyboard control.",
        )
        focus["tags"]["issue_codes"] = [
            "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE"
        ]
        generic_input = document(
            "android.rule.input-controls",
            "Android input controls",
            "Android XML EditText input purpose and keyboard configuration.",
        )

        query = "ANDROID_XML_EMAIL_INPUTTYPE_MISSING EditText"
        results = retrieve(query, [email, focus, generic_input], final_limit=3)
        ids = [item["doc_id"] for item in results]

        self.assertTrue(eligible_for_issue_query(email, query))
        self.assertFalse(eligible_for_issue_query(focus, query))
        self.assertIn(email["doc_id"], ids)
        self.assertIn(generic_input["doc_id"], ids)
        self.assertNotIn(focus["doc_id"], ids)

    def test_v3_specialized_code_inherits_generic_document_mapping(self):
        generic_name = document(
            "android.rule.content-labels",
            "Android content labels",
            "Android XML ImageButton contentDescription and stateful labels.",
        )
        generic_name["tags"]["issue_codes"] = [
            "ANDROID_XML_MISSING_ACCESSIBLE_NAME"
        ]
        unrelated = document(
            "android.fix.email",
            "Email input repair",
            "Android XML textEmailAddress inputType.",
        )
        unrelated["tags"]["issue_codes"] = [
            "ANDROID_XML_EMAIL_INPUTTYPE_MISSING"
        ]
        query = (
            "ANDROID_XML_IMAGE_BUTTON_MISSING_ACCESSIBLE_NAME "
            "ImageButton contentDescription"
        )

        self.assertTrue(eligible_for_issue_query(generic_name, query))
        self.assertFalse(eligible_for_issue_query(unrelated, query))
        results = retrieve(query, [generic_name, unrelated], final_limit=2)
        self.assertEqual(
            [item["doc_id"] for item in results],
            [generic_name["doc_id"]],
        )

    def test_prompt_retrieval_is_bounded_and_keeps_each_issue_mapping(self):
        input_doc = document(
            "android.rule.forms-errors",
            "Android input labels",
            "Android XML EditText hint and labelFor requirements.",
        )
        results = retrieve_for_issues(
            [
                {
                    "code": "ANDROID_XML_MISSING_ACCESSIBLE_NAME",
                    "component": "ImageButton",
                    "related_docs": [self.direct["doc_id"]],
                },
                {
                    "code": "ANDROID_XML_INPUT_MISSING_LABEL_OR_HINT",
                    "component": "EditText",
                    "related_docs": [input_doc["doc_id"]],
                },
            ],
            [
                self.direct,
                input_doc,
                self.android_extra,
                self.semantic_extra,
            ],
            per_issue_limit=3,
            prompt_limit=6,
        )

        ids = [item["doc_id"] for item in results]
        self.assertIn(self.direct["doc_id"], ids)
        self.assertIn(input_doc["doc_id"], ids)
        self.assertLessEqual(len(results), 6)
        self.assertTrue(all("issue_code" in item for item in results))

    def test_prompt_budget_cannot_be_consumed_by_the_first_issue(self):
        documents = []
        issues = []
        for index in range(3):
            code = f"ANDROID_XML_TEST_{index}"
            issues.append({"code": code, "component": f"Control{index}"})
            for rank in range(3):
                item = document(
                    f"android.fix.{index}.{rank}",
                    f"Control{index} repair {rank}",
                    f"Android XML {code} Control{index} repair guidance {rank}.",
                )
                item["tags"]["issue_codes"] = [code]
                documents.append(item)

        results = retrieve_for_issues(
            issues,
            documents,
            per_issue_limit=3,
            prompt_limit=3,
            direct_limit=0,
        )

        self.assertEqual(
            {item["issue_code"] for item in results},
            {issue["code"] for issue in issues},
        )

    def test_app_context_is_limited_to_current_source_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "app/src/main/java/org/example/MainActivity.kt"
            source.parent.mkdir(parents=True)
            source.write_text(
                "fun bind() { findViewById(R.id.save_button).setOnClickListener { save() } }\n",
                encoding="utf-8",
            )
            layout = root / "app/src/main/res/layout/main.xml"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                '<ImageButton android:id="@+id/save_button" android:src="@drawable/ic_save" />\n',
                encoding="utf-8",
            )
            ignored = root / "app/build/generated.xml"
            ignored.parent.mkdir(parents=True)
            ignored.write_text("save_button", encoding="utf-8")
            issue = {
                "component": "ImageButton",
                "attributes": {
                    "android:id": "@+id/save_button",
                    "android:src": "@drawable/ic_save",
                },
            }

            results = retrieve_app_context(root, issue)

        paths = [item["path"] for item in results]
        self.assertIn(
            "app/src/main/java/org/example/MainActivity.kt", paths
        )
        self.assertIn("app/src/main/res/layout/main.xml", paths)
        self.assertFalse(any("/build/" in f"/{path}/" for path in paths))
        self.assertTrue(all(item["source_root"] == str(root.resolve()) for item in results))

    def test_app_context_prompt_limit_and_issue_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "app/src/main/java/org/example/MainActivity.kt"
            source.parent.mkdir(parents=True)
            source.write_text(
                "save_button\nopen_button\nsave_button\nopen_button\n",
                encoding="utf-8",
            )
            issues = [
                {
                    "code": "SAVE_NAME",
                    "selector": "/ImageButton[1]",
                    "attributes": {"android:id": "@+id/save_button"},
                },
                {
                    "code": "OPEN_NAME",
                    "selector": "/ImageButton[2]",
                    "attributes": {"android:id": "@+id/open_button"},
                },
            ]

            results = retrieve_app_context_for_issues(
                root,
                issues,
                per_issue_limit=2,
                prompt_limit=3,
            )

        self.assertLessEqual(len(results), 3)
        self.assertTrue(all("issue_index" in item for item in results))
        self.assertTrue(all("issue_code" in item for item in results))


class AndroidXmlKnowledgeRetrievalRegressionTests(unittest.TestCase):
    EXPECTED = {
        "ANDROID_XML_EMAIL_INPUTTYPE_MISSING": (
            "EditText android:id=@+id/edt_email android:hint=@string/email",
            "android.fixcase.xml-email-inputtype-missing",
        ),
        "ANDROID_XML_INPUT_WEAK_LABEL_OR_HINT": (
            "EditText android:hint=+1-555-12345 android:inputType=phone",
            "android.fixcase.xml-format-example-only-hint",
        ),
        "ANDROID_XML_INTERACTIVE_NOT_FOCUSABLE": (
            "ImageButton android:clickable=true android:focusable=false",
            "android.fixcase.xml-standard-control-focusable-false",
        ),
        "ANDROID_XML_PASSWORD_INPUTTYPE_MISSING": (
            "EditText android:id=@+id/account_password android:hint=@string/password",
            "android.fixcase.xml-password-inputtype-missing",
        ),
        "ANDROID_XML_PHONE_INPUTTYPE_MISSING": (
            "EditText android:id=@+id/contact_phone android:hint=@string/phone_number",
            "android.fixcase.xml-phone-inputtype-missing",
        ),
        "ANDROID_XML_NUMBER_INPUTTYPE_MISSING": (
            "EditText android:id=@+id/expense_amount android:hint=@string/amount",
            "android.fixcase.xml-number-inputtype-missing",
        ),
    }

    def test_specialized_documents_are_top_one_without_cross_talk(self):
        documents = load_documents()
        targeted_ids = {expected for _, expected in self.EXPECTED.values()}

        for code, (evidence, expected_id) in self.EXPECTED.items():
            with self.subTest(code=code):
                results = retrieve(
                    f"Android XML accessibility {code} {evidence}",
                    documents,
                    final_limit=3,
                    direct_limit=0,
                )
                ids = [item["doc_id"] for item in results]
                self.assertTrue(ids)
                self.assertEqual(ids[0], expected_id)
                self.assertTrue(targeted_ids.isdisjoint(set(ids[1:])))


if __name__ == "__main__":
    unittest.main()
