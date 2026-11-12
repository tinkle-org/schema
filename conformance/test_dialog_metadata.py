"""Descriptor/codec checks for source-owned dialog metadata, not authorization."""
import unittest

import test_files_schema as files


class DialogMetadataTests(files.BufSchemaTestCase):
    """Keep exact types/tags and distinguish known zero from unknown metadata."""

    def test_types_tags_and_presence(self):
        """Reuse NotificationSetting and retain the existing outbox wire tag."""
        fields = {field["name"]: field for field in self.descriptor("Dialog")["field"]}
        self.assertEqual(11, fields["notification_settings"]["number"])
        self.assertEqual(".tinkle.v1.NotificationSetting", fields["notification_settings"]["typeName"])
        for name, tag in (("read_outbox_max_id", 5), ("unread_mention_count", 12), ("unread_reaction_count", 13)):
            self.assertEqual(tag, fields[name]["number"])
            self.assertEqual("TYPE_INT64", fields[name]["type"])
            self.assertTrue(fields[name].get("proto3Optional"))

    def test_unknown_and_known_zero_round_trip(self):
        """Omitted source state stays absent while explicit zero survives the codec."""
        missing = self.round_trip({}, "Dialog")
        for key in ("readOutboxMaxId", "unreadMentionCount", "unreadReactionCount", "notificationSettings"):
            self.assertNotIn(key, missing)
        known = self.round_trip({"readOutboxMaxId": "0", "unreadMentionCount": "0", "unreadReactionCount": "0", "notificationSettings": {"scope": "NOTIFICATION_SCOPE_USERS", "enabled": False, "preview": True}}, "Dialog")
        self.assertEqual("0", known["readOutboxMaxId"])
        self.assertEqual("0", known["unreadMentionCount"])
        self.assertEqual("0", known["unreadReactionCount"])
        self.assertFalse(known["notificationSettings"]["enabled"])


if __name__ == "__main__":
    unittest.main()
