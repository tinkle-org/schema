"""Public naming, media policy and deletion progress conformance; no runtime claims."""

import json
import unittest

import test_files_schema as files


# Exact public method/type spelling changes; field tags remain independently checked.
RPC_NAMES = {
    "SendMultiMedia": "SendAlbum",
    "GetChatComplete": "GetChatDetails",
    "GetThreadMessage": "ListThreadMessages",
    "GetMessagesReactions": "BatchGetMessageReactions",
    "GetMessageReactionsList": "ListMessageReactions",
    "GetTargetChanges": "ListMessageChanges",
    "ReadHistory": "MarkHistoryRead",
    "SendStartBot": "StartBot",
    "EditChatAbout": "UpdateChatDescription",
    "UpdatePinnedMessage": "SetMessagePin",
}
FIELD_NAMES = {
    "random_id": "idempotency_key", "top_msg_id": "thread_root_id",
    "reply_to_msg_id": "reply_to_message_id", "reply_to_top_id": "thread_root_id",
    "no_webpage": "suppress_link_preview", "no_forward": "forwarding_restricted",
    "add_to_recent": "save_to_recents", "big": "animate", "multi_media": "items",
    "pm_oneside": "pin_scope", "unfave": "is_favorite",
}


class ContractCompletionTests(files.BufSchemaTestCase):
    """Check the complete rename surface and observable policy additions."""

    def test_bot_contract_comments_are_self_contained(self):
        """Describe bot operations directly with independent public terminology."""
        text = (files.REPO_ROOT / "tinkle/v1/bots.proto").read_text()
        for title in ("Bot Commands", "Menu Button", "Default Admin Scopes", "Bot Info & Profile",
                      "Username Management", "Messaging Permissions", "Custom Requests"):
            self.assertIn("  // " + title + "\n", text)
        self.assertIn("  // One-way grant; no revocation RPC exists.\n", text)

    def test_exact_renames_preserve_field_tags_and_types(self):
        """Compare every owned field with its explicitly named replacement."""
        baseline = json.loads(files.run_buf(
            "build", ".git#branch=origin/main", "--exclude-source-info",
            "--as-file-descriptor-set", "-o", "-#format=json",
        ).stdout)
        types = {old + suffix: new + suffix for old, new in RPC_NAMES.items()
                 for suffix in ("Request", "Response")}
        types["SingleMediaSource"] = "AlbumItem"
        types["ChatComplete"] = "ChatDetails"
        for old, new in types.items():
            self.assertNotIn("tinkle.v1." + old, self.declarations["message"])
            self.descriptor(new)
        for file in baseline["file"]:
            if not file["name"].startswith("tinkle/"):
                continue
            for service in file.get("service", []):
                methods = self.declarations["service"]["tinkle.v1." + service["name"]][1]["method"]
                expected = [RPC_NAMES.get(m["name"], m["name"]) for m in service["method"]]
                if service["name"] == "MessagesService" and "GetRecentReactions" not in expected:
                    expected.insert(expected.index("SendReaction") + 1, "GetRecentReactions")
                if service["name"] == "MessagesService":
                    for name, after in (("GetScheduledMessages", "UnpinAllMessages"),
                                        ("CancelScheduledMessages", "GetScheduledMessages"),
                                        ("ClosePoll", "GetPollResults")):
                        if name not in expected:
                            expected.insert(expected.index(after) + 1, name)
                self.assertEqual(expected, [m["name"] for m in methods], service["name"])
            for message in file.get("messageType", []):
                name = types.get(message["name"], message["name"])
                current = {f["name"]: f for f in self.descriptor(name).get("field", [])}
                for old in message.get("field", []):
                    if file["name"] == files.FILES_FILE and old["name"] == "encrypted":
                        continue
                    field_name = FIELD_NAMES.get(old["name"], old["name"])
                    if name == "GetChatDetailsResponse" and field_name == "chat_complete":
                        field_name = "chat_details"
                    if name == "UpdateChatDescriptionRequest" and field_name == "about":
                        field_name = "description"
                    with self.subTest(message=name, field=field_name):
                        self.assertIn(field_name, current)
                        field = current[field_name]
                        for key in ("number", "label", "proto3Optional"):
                            expected = old.get(key)
                            if key == "proto3Optional" and name == "Dialog" and field_name == "read_outbox_max_id":
                                expected = True
                            self.assertEqual(expected, field.get(key), key)
                        if old["name"] == "pm_oneside":
                            self.assertEqual("TYPE_ENUM", field["type"])
                            self.assertEqual(".tinkle.v1.PinScope", field["typeName"])
                        else:
                            self.assertEqual(old["type"], field["type"])
                            type_name = old.get("typeName", "")
                            for before, after in types.items():
                                if type_name == ".tinkle.v1." + before:
                                    type_name = ".tinkle.v1." + after
                            self.assertEqual(type_name, field.get("typeName", ""))
        for _, message in self.declarations["message"].values():
            self.assertFalse(set(FIELD_NAMES) & {f["name"] for f in message.get("field", [])})

    def test_pin_scope_and_private_projection(self):
        """Separate shared pins, private pins, unknown state and explicit defaults."""
        self.assert_enum_values("PinScope", ["PIN_SCOPE_UNSPECIFIED", "PIN_SCOPE_SHARED",
                                              "PIN_SCOPE_PERSONAL"], "tinkle/v1/messages.proto")
        for name, field_name, tag in (("Message", "suppress_link_preview", 19),
                                      ("Message", "personal_pin", 20)):
            field = next(f for f in self.descriptor(name)["field"] if f["name"] == field_name)
            self.assertEqual((tag, "TYPE_BOOL", True),
                             (field["number"], field["type"], field.get("proto3Optional", False)))
        for fixture in ({}, {"pinScope": "PIN_SCOPE_SHARED"},
                        {"pinScope": "PIN_SCOPE_PERSONAL"}, {"pinScope": "PIN_SCOPE_UNSPECIFIED"}):
            self.assertEqual(fixture, self.round_trip(fixture, "SetMessagePinRequest"))
        # Codec presence is not server validation: explicit UNSPECIFIED must be rejected there.
        fixture = {"suppressLinkPreview": False, "personalPin": False}
        self.assertEqual(fixture, self.round_trip(fixture, "Message"))

    def test_renamed_fields_round_trip(self):
        """Preserve full-width keys, roots, explicit booleans and desired state."""
        large = "9007199254740993"
        for name, fixture in (
            ("SendMessageRequest", {"idempotencyKey": large, "forwardingRestricted": False}),
            ("SendMediaRequest", {"idempotencyKey": large, "forwardingRestricted": True}),
            ("SendAlbumRequest", {"items": [{"idempotencyKey": large, "media": {"photo": {"fileId": "8"}}}],
                                  "forwardingRestricted": False}),
            ("StartBotRequest", {"idempotencyKey": large}),
            ("DraftMessage", {"replyToMessageId": large}),
            ("MessageReplyHeader", {"replyToMessageId": large, "threadRootId": "7"}),
            ("ReplyInput", {"replyToMessageId": large, "threadRootId": "7"}),
            ("EditMessageRequest", {"suppressLinkPreview": False}),
            ("SendReactionRequest", {"animate": False, "saveToRecents": True}),
        ):
            with self.subTest(message=name):
                self.assertEqual(fixture, self.round_trip(fixture, name))
        for name in ("TypingChanged", "SetTypingRequest", "SearchRequest", "ReadThreadRequest",
                     "UnpinAllMessagesRequest", "GetUnreadMentionsRequest", "ReadMentionsRequest",
                     "GetUnreadReactionsRequest", "ReadReactionsRequest"):
            fixture = {"threadRootId": large}
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_chat_photo_descriptor(self):
        """Expose exactly the files that a current chat-photo read context may use."""
        self.assert_fields("ChatPhoto", [
            ("photo_id", 1, "INT64", "", False, False),
            ("has_video", 2, "BOOL", "", False, False),
            ("file_id", 3, "INT64", "", False, False),
            ("metadata", 4, "MESSAGE", "ImageMetadata", False, False),
            ("variants", 5, "MESSAGE", "MediaVariant", True, False),
        ])
        fixture = {"photoId": "9", "fileId": "9007199254740993",
                   "metadata": {"width": 512, "height": 512}, "variants": [
                       {"fileId": "10", "role": "MEDIA_VARIANT_ROLE_THUMBNAIL", "width": 160, "height": 160}]}
        self.assertEqual(fixture, self.round_trip(fixture, "ChatPhoto"))

    def test_chat_details_and_description_names(self):
        """Expose complete details and description names without alternate spellings."""
        self.assertNotIn("tinkle.v1.ChatComplete", self.declarations["message"])
        self.assert_fields("ChatDetails", [
            ("chat", 1, "MESSAGE", "Chat", False, False),
            ("participants", 2, "MESSAGE", "Participant", True, False),
            ("admins", 3, "MESSAGE", "Participant", True, False),
            ("invite_links", 4, "MESSAGE", "InviteLink", True, False),
            ("restricted_users", 5, "MESSAGE", "RestrictedUser", True, False),
            ("ttl_period", 6, "INT32", "", False, False),
        ])
        self.assert_fields("GetChatDetailsResponse", [
            ("chat_details", 1, "MESSAGE", "ChatDetails", False, False),
        ])
        self.assert_fields("UpdateChatDescriptionRequest", [
            ("chat_id", 1, "INT64", "", False, False),
            ("description", 2, "STRING", "", False, False),
        ])
        for name, fixture in (
            ("GetChatDetailsResponse", {"chatDetails": {"chat": {"chatId": "9", "about": "Basic description"}}}),
            ("UpdateChatDescriptionRequest", {"chatId": "9", "description": "New description"}),
        ):
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_restriction_categories_are_lossless(self):
        """Represent each independently enforceable send restriction without grouping."""
        values = self.declarations["enum"]["tinkle.v1.ChatRestrictedScope"][1]["value"]
        expected = [("CHAT_RESTRICTED_SCOPE_SEND_" + name, tag) for name, tag in
                    (("TEXT", 13), ("PHOTO", 14), ("VIDEO", 15), ("AUDIO", 16), ("VOICE", 17), ("DOCUMENT", 18))]
        self.assertEqual(expected, [(v["name"], v["number"]) for v in values][-6:])

    def test_files_reserve_unavailable_option(self):
        """Prevent file-level encryption fields and reuse of their numeric slot."""
        for name in ("BeginUploadRequest", "FileInfo"):
            descriptor = self.descriptor(name)
            self.assertNotIn("encrypted", [f["name"] for f in descriptor["field"]])
            self.assertEqual([{"start": 6, "end": 7}], descriptor["reservedRange"])
            self.assertEqual(["encrypted"], descriptor["reservedName"])

    def test_general_validation_profiles(self):
        """Keep general media profiles versioned and separate from asset validation."""
        self.assert_enum_values("MediaValidationProfile", ["MEDIA_VALIDATION_PROFILE_" + name for name in
            ("UNSPECIFIED", "STRICT_LOSSLESS", "IMAGE", "VIDEO", "AUDIO", "VOICE")], files.MEDIA_FILE)
        for name, tag, profile in (("VideoMetadata", 7, "VIDEO"), ("AudioMetadata", 6, "AUDIO")):
            field = self.descriptor(name)["field"][-1]
            self.assertEqual(("validation", tag, ".tinkle.v1.MediaValidation"),
                             (field["name"], field["number"], field["typeName"]))
            fixture = {"validation": {"profile": "MEDIA_VALIDATION_PROFILE_" + profile, "version": 1}}
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_delete_operation_progress(self):
        """Pin stable operation identity and explicit completion on history deletion."""
        for name, additions in {
            "DeleteHistoryRequest": [("operation_id", 6, "STRING", False)],
            "DeleteHistoryResponse": [("operation_id", 3, "STRING", False),
                                      ("completed", 4, "BOOL", True), ("processed_count", 5, "UINT64", False)],
        }.items():
            fields = [f for f in self.descriptor(name)["field"] if f["number"] >= additions[0][1]]
            self.assertEqual(additions, [(f["name"], f["number"], f["type"].removeprefix("TYPE_"),
                                         f.get("proto3Optional", False)) for f in fields])
        for complete in (False, True):
            fixture = {"operationId": "5ed05390-b124-4a20-810f-5f8aa7019dd7",
                       "completed": complete, "processedCount": "9007199254740993"}
            self.assertEqual(fixture, self.round_trip(fixture, "DeleteHistoryResponse"))
        self.assertEqual({"stickerId": "8"}, self.round_trip(
            {"stickerId": "8", "isFavorite": False}, "ToggleFavoriteStickerRequest"))
        self.assertEqual({"stickerId": "8", "isFavorite": True}, self.round_trip(
            {"stickerId": "8", "isFavorite": True}, "ToggleFavoriteStickerRequest"))

    def test_delete_messages_is_independent_items_only(self):
        """Keep per-call item deletion free of operation identity and progress fields."""
        self.assert_fields("DeleteMessagesRequest", [
            ("target", 1, "MESSAGE", "Target", False, False),
            ("message_ids", 2, "INT64", "", True, False),
            ("revoke", 3, "BOOL", "", False, True),
        ])
        self.assert_fields("DeleteMessagesResponse", [
            ("deleted_count", 1, "INT32", "", False, False),
        ])
        fixture = {"target": {"chatId": "9"}, "messageIds": ["7", "8"], "revoke": False}
        self.assertEqual(fixture, self.round_trip(fixture, "DeleteMessagesRequest"))
        self.assertEqual({"deletedCount": 1}, self.round_trip({"deletedCount": 1}, "DeleteMessagesResponse"))
        messages = (files.REPO_ROOT / "tinkle/v1/messages.proto").read_text()
        section = messages.split("// DeleteMessagesRequest", 1)[1].split("// ===", 1)[0]
        self.assertIn("independently", section)
        self.assertNotIn("operation_id", section)
        self.assertNotIn("UUID", section)
        self.assertNotIn("cumulative", section.lower())

    def test_media_and_mutation_policy_is_explicit(self):
        """Check policy anchors; descriptor/codec checks cannot validate media bytes."""
        media = (files.REPO_ROOT / files.MEDIA_FILE).read_text()
        messages = (files.REPO_ROOT / "tinkle/v1/messages.proto").read_text()
        for phrase in ("10,000,000", "10,000", "H.264", "8-bit", "4:2:0", "AAC-LC",
                       "1920", "1080", "frame rate", "audio-only", "before publication",
                       "server-measured", "without upscaling", "explicit still",
                       "Automatic main-image resizing", "final resized pixels"):
            self.assertIn(phrase, media)
        for phrase in ("Message photo/video: required", "Chat/profile photo: required",
                       "Sticker: required", "custom emoji: optional", "voice: none",
                       "Raw documents are not", "1-pixel main"):
            self.assertIn(phrase, media)
        account = (files.REPO_ROOT / "tinkle/v1/account.proto").read_text()
        stickers = (files.REPO_ROOT / "tinkle/v1/stickers.proto").read_text()
        for phrase in ("4096x4096", "10,000,000 bytes", "160x160", "256 KiB"):
            self.assertIn(phrase, account)
        for phrase in ("512x512", "128x128", "1 MiB", "4 MiB", "3000 ms", "180"):
            self.assertIn(phrase, stickers)
        self.assertIn("is_favorite=true to add, false to remove", stickers)
        for phrase in ("absence selects SHARED", "explicit UNSPECIFIED", "sender's own messages",
                       "incoming messages", "same operation_id", "never restarts", "caller only"):
            self.assertIn(phrase, messages)


if __name__ == "__main__":
    unittest.main()
