"""Exact messaging option shapes and codec presence, not runtime enforcement."""

import unittest

import test_files_schema as files


class MessagingOptionsSchemaTests(files.BufSchemaTestCase):
    """Pin implemented reaction effects, caller collections and source-fenced sends."""

    def test_reaction_option_and_effect_shapes(self):
        """Keep presentation metadata typed and distinct from durable message bodies."""
        self.assert_fields("SendReactionRequest", [
            ("target", 1, "MESSAGE", "Target", False, False),
            ("message_id", 2, "INT64", "", False, False),
            ("reactions", 3, "MESSAGE", "Reaction", True, False),
            ("animate", 4, "BOOL", "", False, True),
            ("save_to_recents", 5, "BOOL", "", False, True),
            ("operation_id", 6, "STRING", "", False, False),
        ])
        self.assert_fields("ReactionEffect", [
            ("operation_id", 1, "STRING", "", False, False),
            ("actor_id", 2, "INT64", "", False, False),
            ("expires_at", 3, "MESSAGE", ".google.protobuf.Timestamp", False, False),
            ("reactions", 4, "MESSAGE", "Reaction", True, False),
        ])
        self.assert_fields("MessageChanged", [
            ("target", 1, "MESSAGE", "Target", False, False),
            ("message_id", 2, "INT64", "", False, False),
            ("body_revision", 3, "INT64", "", False, False),
            ("change_kind", 4, "ENUM", "TargetChangeKind", False, False),
            ("reaction_effect", 5, "MESSAGE", "ReactionEffect", False, False),
            ("body_invalidated", 6, "BOOL", "", False, False),
        ])
        for name in ("Message", "TargetChange"):
            self.assertNotIn("reaction_effect", [f["name"] for f in self.descriptor(name)["field"]])

    def test_recent_reactions_are_caller_selected(self):
        """The empty request cannot select a different account or follow asset heads."""
        services = self.declarations["service"]
        self.assertEqual(13, len(services))
        self.assertEqual(207, sum(len(service[1]["method"]) for service in services.values()))
        self.assertEqual(43, len(services["tinkle.v1.MessagesService"][1]["method"]))
        self.assert_fields("GetRecentReactionsRequest", [])
        self.assert_fields("GetRecentReactionsResponse", [
            ("reactions", 1, "MESSAGE", "Reaction", True, False),
        ])
        method = next(m for m in self.declarations["service"]["tinkle.v1.MessagesService"][1]["method"]
                      if m["name"] == "GetRecentReactions")
        self.assertEqual(".tinkle.v1.GetRecentReactionsRequest", method["inputType"])
        self.assertEqual(".tinkle.v1.GetRecentReactionsResponse", method["outputType"])
        self.assertFalse(method.get("clientStreaming", False))
        self.assertFalse(method.get("serverStreaming", False))
        fixture = {"reactions": [{"emoticon": ":wave:", "customEmojiId": "9007199254740993",
                                  "assetVersion": "18446744073709551615"}]}
        self.assertEqual(fixture, self.round_trip(fixture, "GetRecentReactionsResponse"))

    def test_explicit_schedule_and_poll_close_shapes(self):
        """Pin explicit bounded job lookups separately from accepted-history bodies."""
        target = ("target", 1, "MESSAGE", "Target", False, False)
        ids = ("message_ids", 2, "INT64", "", True, False)
        self.assert_fields("GetScheduledMessagesRequest", [
            target, ids, ("idempotency_keys", 3, "INT64", "", True, False),
        ])
        self.assert_fields("CancelScheduledMessagesRequest", [target, ids])
        self.assert_fields("ScheduledMessage", [
            ("message_id", 1, "INT64", "", False, False),
            ("idempotency_key", 2, "INT64", "", False, False),
            ("target", 3, "MESSAGE", "Target", False, False),
            ("scheduled_at", 4, "MESSAGE", ".google.protobuf.Timestamp", False, False),
            ("state", 5, "ENUM", "ScheduleState", False, False),
            ("album_id", 6, "INT64", "", False, True),
            ("message", 7, "MESSAGE", "Message", False, False),
        ])
        for name in ("GetScheduledMessagesResponse", "CancelScheduledMessagesResponse"):
            self.assert_fields(name, [("messages", 1, "MESSAGE", "ScheduledMessage", True, False)])
        self.assert_fields("ClosePollRequest", [target, ("message_id", 2, "INT64", "", False, False)])
        self.assert_fields("ClosePollResponse", [("message", 1, "MESSAGE", "Message", False, False)])
        self.assertEqual({"idempotencyKeys": ["-7", "9007199254740993"]}, self.round_trip(
            {"idempotencyKeys": ["-7", "9007199254740993"]}, "GetScheduledMessagesRequest"))
        for state in ("PENDING", "PROCESSING", "DELIVERED", "CANCELED", "FAILED"):
            fixture = {"messages": [{"messageId": "11", "state": "SCHEDULE_STATE_" + state}]}
            self.assertEqual(fixture, self.round_trip(fixture, "GetScheduledMessagesResponse"))

    def test_schedule_states_and_explicit_selector_boundaries(self):
        """Pin lifecycle values and encode bounded explicit selectors without discovery."""
        enum = self.declarations["enum"]["tinkle.v1.ScheduleState"][1]
        self.assertEqual([("SCHEDULE_STATE_" + name, number) for number, name in enumerate(
            ("UNSPECIFIED", "PENDING", "PROCESSING", "DELIVERED", "CANCELED", "FAILED"))],
            [(value["name"], value["number"]) for value in enum["value"]])
        self.assertFalse(enum.get("options", {}).get("allowAlias", False))
        ids = [str(9007199254740993 + index) for index in range(100)]
        for name in ("GetScheduledMessagesRequest", "CancelScheduledMessagesRequest"):
            fixture = {"target": {"chatId": "9"}, "messageIds": ids}
            self.assertEqual(fixture, self.round_trip(fixture, name))
            # Empty or conflicting selectors encode; validation is not a codec feature.
            self.assertEqual({}, self.round_trip({}, name))
        fixture = {"target": {"chatId": "9"}, "idempotencyKeys": [str(-index) for index in range(1, 101)]}
        self.assertEqual(fixture, self.round_trip(fixture, "GetScheduledMessagesRequest"))
        snapshot = {"messageId": ids[0], "idempotencyKey": "-7", "target": {"chatId": "9"},
                    "scheduledAt": "2030-01-01T00:00:00Z", "state": "SCHEDULE_STATE_PENDING",
                    "albumId": "9007199254740995", "message": {"messageId": ids[0]}}
        self.assertEqual(snapshot, self.round_trip(snapshot, "ScheduledMessage"))
        self.assertNotIn("acceptSeq", self.round_trip(snapshot, "ScheduledMessage")["message"])

    def test_close_poll_correctness_projection_codec(self):
        """Hidden correctness differs from disclosed false in the shared poll projection."""
        result = {"option": "AA==", "voters": 1}
        fixture = {"message": {"messageId": "9007199254740993", "media": {"poll": {
            "id": "9", "quiz": True, "results": {"totalVoters": 1, "results": [result]}}}}}
        self.assertEqual(fixture, self.round_trip(fixture, "GetPollResultsResponse"))
        self.assertNotIn("correct", self.round_trip(fixture, "GetPollResultsResponse")[
            "message"]["media"]["poll"]["results"]["results"][0])
        fixture["message"]["media"]["poll"]["closed"] = True
        result["correct"] = False
        self.assertEqual(fixture, self.round_trip(fixture, "ClosePollResponse"))

    def test_schedule_and_poll_policy_comments(self):
        """Document source-enforced ownership, bounds and status/disclosure limits."""
        text = (files.REPO_ROOT / "tinkle/v1/messages.proto").read_text()
        lookup = text.split("// GetScheduledMessagesRequest", 1)[1].split("// GetScheduledMessagesResponse", 1)[0]
        for phrase in ("authenticated actor", "No implicit discovery", "1..100", "nonempty"):
            self.assertIn(phrase, lookup)
        descriptor = text.split("// ScheduledMessage is", 1)[1].split("// GetScheduledMessagesRequest", 1)[0]
        self.assertIn("not acceptance proof", descriptor)
        cancel = text.split("// CancelScheduledMessagesRequest", 1)[1].split("// ClosePollRequest", 1)[0]
        for phrase in ("authenticated actor", "1..100", "not rollback", "never revoked or removed"):
            self.assertIn(phrase, cancel)
        close = text.split("// ClosePollRequest", 1)[1].split("// MessagesFilter", 1)[0]
        self.assertIn("caller-relative", close)
        self.assertIn("caller votes or the poll closes", close)

    def test_option_absence_is_distinct_from_explicit_false(self):
        """Optional sender choices retain false without manufacturing omitted choices."""
        for name, options in (
            ("SendReactionRequest", ("animate", "saveToRecents")),
            ("SendMessageRequest", ("silent", "forwardingRestricted", "clearDraft")),
            ("SendMediaRequest", ("silent", "forwardingRestricted", "clearDraft")),
            ("SendAlbumRequest", ("silent", "forwardingRestricted", "clearDraft")),
        ):
            with self.subTest(message=name):
                self.assertEqual({}, self.round_trip({}, name))
                explicit = dict.fromkeys(options, False)
                self.assertEqual(explicit, self.round_trip(explicit, name))
        for name in ("SendReactionRequest", "SendMessageRequest", "SendMediaRequest", "SendAlbumRequest"):
            field = "animate" if name == "SendReactionRequest" else "silent"
            self.assertNotEqual(0, self.convert({field: "false"}, name, check=False).returncode)

    def test_effect_actor_and_fixed_expiry_round_trip(self):
        """Keep actor/operation dedup identity and absolute expiry, even for expired hints."""
        operation = "5ed05390-b124-4a20-810f-5f8aa7019dd7"
        for actor in ("7", "9007199254740993"):
            for expiry in ("2000-01-01T00:00:00Z", "2030-01-01T00:00:00Z"):
                effect = {"operationId": operation, "actorId": actor, "expiresAt": expiry,
                          "reactions": [{"emoticon": ":wave:", "customEmojiId": "8", "assetVersion": "2"}]}
                hint = {"target": {"chatId": "9"}, "messageId": "10", "bodyRevision": "11",
                        "changeKind": "TARGET_CHANGE_KIND_REACTION", "reactionEffect": effect}
                self.assertEqual(hint, self.round_trip(hint, "MessageChanged"))
                self.assertEqual(hint, self.round_trip(hint, "MessageChanged"))
        # Encoding cannot enforce visibility, expiry or at-most-once animation.
        self.assertEqual({"reactionEffect": {}}, self.round_trip({"reactionEffect": {}}, "MessageChanged"))

    def test_source_fenced_send_shapes(self):
        """Pin all send fields so option additions cannot renumber existing content."""
        target = ("target", 1, "MESSAGE", "Target", False, False)
        entity = ("entities", 8, "MESSAGE", "Entity", True, False)
        reply = ("reply_to", 4, "MESSAGE", "ReplyInput", False, True)
        self.assert_fields("SendMessageRequest", [
            target, ("message", 2, "STRING", "", False, False),
            ("idempotency_key", 3, "INT64", "", False, False), reply,
            ("silent", 5, "BOOL", "", False, True),
            ("forwarding_restricted", 6, "BOOL", "", False, True),
            ("clear_draft", 7, "BOOL", "", False, True), entity,
            ("schedule_date", 9, "INT32", "", False, True),
            ("clear_draft_dialog_id", 10, "INT64", "", False, True),
            ("clear_draft_revision", 11, "INT64", "", False, True),
        ])
        self.assert_fields("SendMediaRequest", [
            target, ("media", 2, "MESSAGE", "MediaSource", False, False),
            ("message", 3, "STRING", "", False, True),
            ("idempotency_key", 4, "INT64", "", False, False),
            ("reply_to", 5, "MESSAGE", "ReplyInput", False, True),
            ("silent", 6, "BOOL", "", False, True),
            ("forwarding_restricted", 7, "BOOL", "", False, True),
            ("clear_draft", 8, "BOOL", "", False, True),
            ("entities", 9, "MESSAGE", "Entity", True, False),
            ("schedule_date", 10, "INT32", "", False, True),
            ("clear_draft_dialog_id", 11, "INT64", "", False, True),
            ("clear_draft_revision", 12, "INT64", "", False, True),
        ])
        self.assert_fields("SendAlbumRequest", [
            target, ("items", 2, "MESSAGE", "AlbumItem", True, False),
            ("reply_to", 3, "MESSAGE", "ReplyInput", False, True),
            ("silent", 4, "BOOL", "", False, True),
            ("forwarding_restricted", 5, "BOOL", "", False, True),
            ("clear_draft", 6, "BOOL", "", False, True),
            ("schedule_date", 7, "INT32", "", False, True),
            ("clear_draft_dialog_id", 8, "INT64", "", False, True),
            ("clear_draft_revision", 9, "INT64", "", False, True),
        ])
        fixture = {"clearDraft": True, "clearDraftDialogId": "9007199254740993", "clearDraftRevision": "0"}
        for name in ("SendMessageRequest", "SendMediaRequest", "SendAlbumRequest"):
            self.assertEqual(fixture, self.round_trip(fixture, name))
            for kind in ("userId", "chatId"):
                scoped = dict(fixture, target={kind: "9007199254740995"})
                self.assertEqual(scoped, self.round_trip(scoped, name))

    def test_room_draft_tokens_on_immediate_and_scheduled_sends(self):
        """Room-target wire shapes retain the same sender source pair for both modes."""
        for name in ("SendMessageRequest", "SendMediaRequest", "SendAlbumRequest"):
            fixture = {"target": {"chatId": "9"}, "clearDraft": True,
                       "clearDraftDialogId": "9007199254740993", "clearDraftRevision": "0"}
            self.assertEqual(fixture, self.round_trip(fixture, name))
            fixture["scheduleDate"] = 1893456000
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_creation_retry_key_shapes(self):
        """Keep room mutation keys int64, not reaction/history UUID strings."""
        self.assert_fields("CreateChatRequest", [
            ("title", 1, "STRING", "", False, False),
            ("user_ids", 2, "INT64", "", True, False),
            ("ttl_period", 3, "INT32", "", False, True),
            ("operation_id", 4, "INT64", "", False, False),
        ])
        self.assert_fields("AddChatParticipantRequest", [
            ("chat_id", 1, "INT64", "", False, False),
            ("user_id", 2, "INT64", "", False, False),
            ("forward_limit", 3, "INT32", "", False, False),
            ("operation_id", 4, "INT64", "", False, False),
        ])
        self.assert_fields("EditChatPhotoRequest", [
            ("chat_id", 1, "INT64", "", False, False),
            ("photo", 2, "MESSAGE", "ChatPhotoSource", False, False),
            ("operation_id", 3, "INT64", "", False, False),
        ])
        for name in ("CreateChatRequest", "AddChatParticipantRequest", "EditChatPhotoRequest"):
            fixture = {"operationId": "9007199254740993"}
            self.assertEqual(fixture, self.round_trip(fixture, name))
            self.assertEqual({}, self.round_trip({"operationId": "0"}, name))

    def test_conditional_creation_key_requirements(self):
        """Pin conditional key requirements without mistaking codec shape for validation."""
        text = (files.REPO_ROOT / "tinkle/v1/messages.proto").read_text()
        for name, option, condition in (
            ("CreateChatRequest", "ttlPeriod", "ttl_period > 0"),
            ("AddChatParticipantRequest", "forwardLimit", "forward_limit > 0"),
        ):
            section = text.split("message " + name + " {", 1)[1].split("\n}", 1)[0]
            for phrase in ("Required when " + condition, "positive int64", "Zero permits", "unkeyed"):
                self.assertIn(phrase, section)
            fixture = {option: 30, "operationId": "9007199254740993"}
            self.assertEqual(fixture, self.round_trip(fixture, name))
            # Protobuf permits a missing key even when policy requires it; servers
            # and adapters must validate the condition before applying side effects.
            self.assertEqual({option: 30}, self.round_trip({option: 30}, name))
            self.assertNotEqual(0, self.convert({"operationId": "5ed05390-b124-4a20-810f-5f8aa7019dd7"},
                                               name, check=False).returncode)
        for name in ("SendReactionRequest", "DeleteHistoryRequest"):
            field = next(f for f in self.descriptor(name)["field"] if f["name"] == "operation_id")
            self.assertEqual("TYPE_STRING", field["type"])

    def test_nonterminal_invalidation_shape_and_codec(self):
        """Represent body withholding explicitly without manufacturing a deletion kind."""
        self.assert_fields("TargetChange", [
            ("message_id", 1, "INT64", "", False, False),
            ("kind", 2, "ENUM", "TargetChangeKind", False, False),
            ("message", 3, "MESSAGE", "Message", False, False),
            ("accept_seq", 4, "INT64", "", False, False),
            ("message_revision", 5, "INT64", "", False, True),
            ("body_invalidated", 6, "BOOL", "", False, False),
        ])
        for name, fixture in (
            ("TargetChange", {"messageId": "9007199254740993", "kind": "TARGET_CHANGE_KIND_REACTION",
                              "acceptSeq": "9", "messageRevision": "7"}),
            ("MessageChanged", {"target": {"chatId": "8"}, "messageId": "9007199254740993",
                                "changeKind": "TARGET_CHANGE_KIND_REACTION", "bodyRevision": "7"}),
        ):
            invalidation = dict(fixture, bodyInvalidated=True)
            self.assertEqual(invalidation, self.round_trip(invalidation, name))
            self.assertNotIn("message", self.round_trip(invalidation, name))
            self.assertNotIn("reactionEffect", self.round_trip(invalidation, name))
            self.assertEqual(fixture, self.round_trip(dict(fixture, bodyInvalidated=False), name))
            self.assertEqual(self.encode(fixture, name), self.encode(dict(fixture, bodyInvalidated=False), name))

    def test_nonterminal_invalidation_policy_comments(self):
        """Require source authorization and nonterminal cache handling in public guidance."""
        text = (files.REPO_ROOT / "tinkle/v1/messages.proto").read_text()
        change = text.split("message TargetChange {", 1)[1].split("\n}", 1)[0]
        for phrase in ("canonical identity", "Retain a nonterminal revision floor", "cached bodies",
                       "file references", "not a viewer deletion", "not permission proof"):
            self.assertIn(phrase, change)
        hint = text.split("message MessageChanged {", 1)[1].split("\n}", 1)[0]
        for phrase in ("non-authoritative hint", "current source", "not permission proof"):
            self.assertIn(phrase, hint)

    def test_owned_dialog_projection_shape(self):
        """Keep initialized empty-draft tokens present without inventing draft content."""
        self.assert_fields("Dialog", [
            ("target", 1, "MESSAGE", "Target", False, False),
            ("top_message", 2, "INT64", "", False, False),
            ("unread_count", 3, "INT32", "", False, False),
            ("read_inbox_max_id", 4, "INT64", "", False, False),
            ("read_outbox_max_id", 5, "INT64", "", False, True),
            ("pinned", 6, "BOOL", "", False, False),
            ("space_id", 7, "INT64", "", False, False),
            ("draft", 8, "MESSAGE", "DraftMessage", False, False),
            ("draft_dialog_id", 9, "INT64", "", False, True),
            ("draft_revision", 10, "INT64", "", False, True),
            ("notification_settings", 11, "MESSAGE", "NotificationSetting", False, False),
            ("unread_mention_count", 12, "INT64", "", False, True),
            ("unread_reaction_count", 13, "INT64", "", False, True),
        ])
        fixture = {"target": {"chatId": "9"}, "draftDialogId": "9007199254740993", "draftRevision": "0"}
        self.assertEqual(fixture, self.round_trip(fixture, "Dialog"))
        self.assertEqual({"target": fixture["target"]}, self.round_trip({"target": fixture["target"]}, "Dialog"))

    def test_owned_dialog_unknown_zero_and_false_are_distinct(self):
        """Unknown counters/preferences do not become known zero or enabled defaults."""
        fixture = {"readOutboxMaxId": "0", "unreadMentionCount": "0", "unreadReactionCount": "0",
                   "notificationSettings": {"enabled": False, "preview": False}}
        self.assertEqual(fixture, self.round_trip(fixture, "Dialog"))
        self.assertEqual({}, self.round_trip({}, "Dialog"))
        self.assertEqual({"notificationSettings": {}}, self.round_trip({"notificationSettings": {}}, "Dialog"))
        for field in ("readOutboxMaxId", "unreadMentionCount", "unreadReactionCount"):
            fixture = {field: "9007199254740993"}
            self.assertEqual(fixture, self.round_trip(fixture, "Dialog"))

    def test_caller_scope_and_recovery_comments(self):
        """Pin authorization/recovery rules as documentation, not server-test evidence."""
        text = (files.REPO_ROOT / "tinkle/v1/messages.proto").read_text()
        reaction = text.split("// SendReactionRequest", 1)[1].split("// GetRecentReactionsRequest", 1)[0]
        for phrase in ("authenticated caller only", "Absence or false", "caller-scoped"):
            self.assertIn(phrase, reaction)
        effect = text.split("// ReactionEffect is", 1)[1].split("// TypingChanged", 1)[0]
        for phrase in ("current recipient visibility", "never extended", "discard expired"):
            self.assertIn(phrase, effect)
        deletion = text.split("// DeleteHistoryRequest", 1)[1].split("// DeleteHistoryResponse", 1)[0]
        for phrase in ("peer's history is unchanged", "original filters", "caller only"):
            self.assertIn(phrase, deletion)
        cursor = text.split("message SearchRequest", 1)[1].split("// SearchResponse", 1)[0]
        self.assertIn("Recovery preserves the selected source and original filters", cursor)


if __name__ == "__main__":
    unittest.main()
