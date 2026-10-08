import unittest

from core import bundle
from core import contract_types as ct

LINES = ("aadhaar_front", "pan_card", "resume")


def _doc(code, doc_id, extracted=None):
    return ct.Document(
        document_code=code, verification_document_id=doc_id, status="done", extracted=extracted
    )


class TestPlan(unittest.TestCase):
    def test_documents_are_matched_to_lines_by_code_in_bundle_order(self):
        documents = [_doc("pan_card", "doc-2"), _doc("aadhaar_front", "doc-1")]
        result = bundle.plan(LINES, (), documents)
        self.assertEqual([d.document_code for d in result.matched], ["pan_card", "aadhaar_front"])

    def test_a_code_not_on_any_line_is_not_matched(self):
        result = bundle.plan(LINES, (), [_doc("passport", "doc-1"), _doc("pan_card", "doc-2")])
        self.assertEqual([d.document_code for d in result.matched], ["pan_card"])

    def test_unfiled_entries_are_never_matched(self):
        result = bundle.plan(LINES, (), [_doc("unfiled", "doc-1"), _doc("pan_card", "doc-2")])
        self.assertEqual([d.document_code for d in result.matched], ["pan_card"])

    def test_documents_not_named_in_the_bundle_are_listed_for_deletion(self):
        held = (
            bundle.Held("aadhaar_front", "doc-1"),
            bundle.Held("pan_card", "doc-2"),
            bundle.Held("resume", "doc-3"),
        )
        result = bundle.plan(LINES, held, [_doc("pan_card", "doc-2")])
        self.assertEqual(result.delete_ids, ("doc-1", "doc-3"))

    def test_a_stored_document_named_as_unfiled_is_kept(self):
        held = (bundle.Held("aadhaar_front", "doc-1"),)
        result = bundle.plan(LINES, held, [_doc("unfiled", "doc-1")])
        self.assertEqual(result.delete_ids, ())

    def test_an_empty_bundle_deletes_everything_held(self):
        held = (bundle.Held("pan_card", "doc-2"),)
        result = bundle.plan(LINES, held, [])
        self.assertEqual(result.delete_ids, ("doc-2",))
        self.assertEqual(result.matched, ())


class TestDocumentStep(unittest.TestCase):
    def _step(self, step_type):
        return ct.CompletionStep(
            id=step_type,
            type=step_type,
            provider=ct.Provider(name="9thsense", session_id="s", case_status="completed"),
            documents=[],
            missing_documents=[],
        )

    def _bundle(self, steps):
        return ct.CompletionPayload(
            schema_version="2.0",
            ref="ONB-1",
            goal_key="onboarding",
            stage="Onboarding",
            catalogue_version=1,
            status=ct.Status.completed,
            completed_at="2026-09-29T10:15:02Z",
            steps=steps,
        )

    def test_picks_the_document_collection_step(self):
        steps = [self._step("other"), self._step("document_collection")]
        self.assertIs(bundle.document_step(self._bundle(steps)), steps[1])

    def test_falls_back_to_the_first_step(self):
        steps = [self._step("other"), self._step("another")]
        self.assertIs(bundle.document_step(self._bundle(steps)), steps[0])


if __name__ == "__main__":
    unittest.main()
