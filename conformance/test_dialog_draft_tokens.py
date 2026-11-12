"""Descriptor/codec checks for source-fenced empty drafts, not runtime authorization."""
import unittest

import test_files_schema as files


class DialogDraftTokenTests(files.BufSchemaTestCase):
    """Pin the owned pair on Dialog without extending the DraftMessage envelope."""

    def test_dialog_token_tags_and_presence(self):
        """Both tokens are optional int64 at free tags 9/10; draft stays tag 8."""
        fields = {field["name"]: field for field in self.descriptor("Dialog")["field"]}
        self.assertEqual(8, fields["draft"]["number"])
        for name, number in (("draft_dialog_id", 9), ("draft_revision", 10)):
            self.assertEqual(number, fields[name]["number"])
            self.assertEqual("TYPE_INT64", fields[name]["type"])
            self.assertTrue(fields[name].get("proto3Optional"))
        self.assertEqual(
            [("message", 1), ("entities", 2), ("reply_to_message_id", 3), ("date", 4)],
            [(field["name"], field["number"]) for field in self.descriptor("DraftMessage")["field"]],
        )

    def test_absent_draft_retains_zero_revision_and_large_generation(self):
        """A real empty source keeps presence; omitted tokens stay omitted on wire."""
        value = self.round_trip({"draftDialogId": "9007199254740993", "draftRevision": "0"}, "Dialog")
        self.assertEqual("9007199254740993", value["draftDialogId"])
        self.assertEqual("0", value["draftRevision"])
        self.assertNotIn("draft", value)
        absent = self.round_trip({"spaceId": "1"}, "Dialog")
        self.assertNotIn("draftDialogId", absent)
        self.assertNotIn("draftRevision", absent)


if __name__ == "__main__":
    unittest.main()
