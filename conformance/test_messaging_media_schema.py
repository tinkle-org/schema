"""Descriptor and real Buf codec coverage for messaging/media authoring.

These tests check representation, not server validation or authorization.
No generated SDKs, external services, or third-party Python modules are used.
"""

import unittest

import test_files_schema as files


class MessagingMediaSchemaTests(files.BufSchemaTestCase):
    """Pin messaging/media authoring fields and their codec representation."""

    def assert_manifest(self, manifest):
        """Compare complete field inventories using proto-like type spellings."""
        for name, expected in manifest.items():
            actual = []
            for field in self.descriptor(name).get("field", []):
                kind = field.get("typeName", "").removeprefix(".tinkle.v1.")
                kind = kind or field["type"].removeprefix("TYPE_").lower()
                if field["label"] == "LABEL_REPEATED":
                    kind = "repeated " + kind
                elif field.get("proto3Optional", False):
                    kind = "optional " + kind
                actual.append((field["name"], field["number"], kind))
            self.assertEqual(expected, actual, name)

    def test_authoring_field_manifest(self):
        """Pin every new asset/pack request and response without generated code."""
        self.assert_manifest({
            "StickerAssetSource": [("file_id", 1, "int64"), ("metadata", 2, "StickerMetadata"),
                                   ("variants", 3, "repeated MediaVariantSource")],
            "CreateStickerAssetRequest": [("kind", 1, "StickerKind"), ("source", 2, "StickerAssetSource"),
                                          ("fallback_text", 3, "string")],
            "UpdateStickerAssetRequest": [("asset_id", 1, "int64"), ("source", 2, "StickerAssetSource"),
                                          ("fallback_text", 3, "optional string"),
                                          ("expected_version", 4, "uint64")],
            "DeleteStickerAssetRequest": [("asset_id", 1, "int64"), ("expected_version", 2, "uint64")],
            "DeleteStickerAssetResponse": [("deleted", 1, "bool")],
            "GetStickerAssetsRequest": [("asset_ids", 1, "repeated int64"), ("kind", 2, "StickerKind"),
                                        ("references", 3, "repeated AssetReference"),
                                        ("message_reference", 4, "MessageFileReference")],
            "GetStickerAssetsResponse": [("assets", 1, "repeated StickerView")],
            "GetOwnedPacksRequest": [("kind", 1, "PackKind"), ("cursor", 2, "optional string"),
                                     ("limit", 3, "int32")],
            "GetOwnedPacksResponse": [("packs", 1, "repeated StickerPackPreview"),
                                      ("next_cursor", 2, "optional string")],
            "CreatePackRequest": [("name", 1, "string"), ("short_name", 2, "string"), ("kind", 3, "PackKind")],
            "UpdatePackRequest": [("pack_id", 1, "int64"), ("name", 2, "optional string"),
                                  ("short_name", 3, "optional string"), ("expected_revision", 4, "uint64")],
            "DeletePackRequest": [("pack_id", 1, "int64"), ("expected_revision", 2, "uint64")],
            "DeletePackResponse": [("deleted", 1, "bool")],
            "AddPackAssetRequest": [("pack_id", 1, "int64"), ("asset_id", 2, "int64"),
                                    ("asset_version", 3, "uint64"), ("expected_revision", 4, "uint64")],
            "RemovePackAssetRequest": [("pack_id", 1, "int64"), ("asset_id", 2, "int64"),
                                       ("expected_revision", 3, "uint64")],
            "ReorderPackAssetsRequest": [("pack_id", 1, "int64"), ("asset_ids", 2, "repeated int64"),
                                         ("expected_revision", 3, "uint64")],
            "PublishPackRequest": [("pack_id", 1, "int64"), ("expected_revision", 2, "uint64")],
            "UnpublishPackRequest": [("pack_id", 1, "int64"), ("expected_revision", 2, "uint64")],
            "StickerPackPreview": [("id", 1, "int64"), ("name", 2, "string"), ("short_name", 3, "string"),
                                   ("sticker_count", 4, "int32"), ("covers", 5, "repeated StickerView"),
                                   ("kind", 6, "PackKind"), ("owner_id", 7, "int64"), ("published", 8, "bool"),
                                   ("pack_revision", 9, "uint64")],
            "StickerPackDetail": [("id", 1, "int64"), ("name", 2, "string"), ("short_name", 3, "string"),
                                  ("sticker_count", 4, "int32"), ("stickers", 5, "repeated StickerView"),
                                  ("is_installed", 6, "bool"), ("kind", 7, "PackKind"),
                                  ("owner_id", 8, "int64"), ("published", 9, "bool"),
                                  ("pack_revision", 10, "uint64")],
        })
        for method in ("CreateStickerAsset", "UpdateStickerAsset"):
            self.assert_manifest({method + "Response": [("asset", 1, "StickerView")]})
        for method in ("CreatePack", "UpdatePack", "AddPackAsset", "RemovePackAsset",
                       "ReorderPackAssets", "PublishPack", "UnpublishPack"):
            self.assert_manifest({method + "Response": [("pack", 1, "StickerPackDetail")]})

    def test_profile_photo_field_manifest(self):
        """Pin completed-file sources, bounded-gallery projections and selection."""
        self.assert_manifest({
            "ProfilePhotoSource": [("file_id", 1, "int64"), ("metadata", 2, "ImageMetadata"),
                                   ("variants", 3, "repeated MediaVariantSource")],
            "ProfilePhoto": [("photo_id", 1, "int64"), ("user_id", 2, "int64"), ("file_id", 3, "int64"),
                             ("metadata", 4, "ImageMetadata"), ("variants", 5, "repeated MediaVariant"),
                             ("created_at", 6, ".google.protobuf.Timestamp")],
            "SetProfilePhotoRequest": [("source", 1, "ProfilePhotoSource"), ("expected_revision", 2, "uint64")],
            "SetProfilePhotoResponse": [("photo", 1, "ProfilePhoto"), ("gallery_revision", 2, "uint64")],
            "GetProfilePhotosRequest": [("user_id", 1, "optional int64")],
            "GetProfilePhotosResponse": [("photos", 1, "repeated ProfilePhoto"),
                                         ("selected_photo_id", 2, "optional int64"),
                                         ("gallery_revision", 3, "optional uint64")],
            "SelectProfilePhotoRequest": [("photo_id", 1, "int64"), ("expected_revision", 2, "uint64")],
            "SelectProfilePhotoResponse": [("photo", 1, "ProfilePhoto"), ("gallery_revision", 2, "uint64")],
            "DeleteProfilePhotoRequest": [("photo_id", 1, "int64"), ("expected_revision", 2, "uint64")],
            "DeleteProfilePhotoResponse": [("deleted", 1, "bool"), ("selected_photo_id", 2, "int64"),
                                           ("gallery_revision", 3, "uint64")],
        })

    def test_messages_service_retains_39_unary_methods(self):
        """Preserve the entire existing messaging method surface."""
        methods = self.declarations["service"]["tinkle.v1.MessagesService"][1]["method"]
        self.assertEqual([
            "GetDialogs", "GetHistory", "GetMessages", "GetTargetChanges",
            "ReadHistory", "DeleteHistory", "DeleteMessages", "CreateChat",
            "EditChatTitle", "EditChatPhoto", "EditChatAbout", "GetChats",
            "GetChatComplete", "AddChatParticipant", "RemoveChatParticipant",
            "EditChatAdmin", "EditChatRestrictedScopes", "SetHistoryTTL",
            "UpdatePinnedMessage", "UnpinAllMessages", "SendMessage", "SendMedia",
            "SendMultiMedia", "EditMessage", "SetTyping", "SendStartBot", "Search",
            "GetMessagesReactions", "GetMessageReactionsList", "SendReaction",
            "GetUnreadMentions", "ReadMentions", "GetUnreadReactions",
            "ReadReactions", "SendVote", "GetPollVotes", "GetPollResults",
            "ReadThread", "GetThreadMessage",
        ], [m["name"] for m in methods])
        for method in methods:
            self.assertFalse(method.get("clientStreaming", False))
            self.assertFalse(method.get("serverStreaming", False))
            self.assertEqual(".tinkle.v1." + method["name"] + "Request", method["inputType"])
            self.assertEqual(".tinkle.v1." + method["name"] + "Response", method["outputType"])

    def test_reply_album_schedule_search_and_poll_tags(self):
        """Pin additive messaging fields, types, and explicit presence."""
        expected = {
            "ReplyInput": [("reply_to_top_id", 4, "INT64", "", False, True)],
            "Message": [("album_id", 15, "INT64", "", False, True),
                        ("scheduled_state", 16, "ENUM", "MessageScheduledState", False, False),
                        ("schedule_date", 17, "INT32", "", False, True),
                        ("body_revision", 18, "INT64", "", False, True)],
            "SearchRequest": [("cursor", 13, "STRING", "", False, True),
                              ("offset_message_id", 14, "INT64", "", False, True)],
            "SearchResponse": [("next_cursor", 6, "STRING", "", False, True),
                               ("more_available", 7, "BOOL", "", False, True),
                               ("source", 8, "ENUM", "SearchSource", False, False),
                               ("coverage", 9, "ENUM", "SearchCoverage", False, False)],
            "PollSource": [("correct_answers", 8, "BYTES", "", True, False)],
            "Poll": [("results", 8, "MESSAGE", "PollResults", False, False)],
            "Entity": [("fallback_text", 8, "STRING", "", False, True),
                       ("asset_version", 9, "UINT64", "", False, True)],
        }
        for name, additions in expected.items():
            fields = self.descriptor(name)["field"]
            actual = [(f["name"], f["number"], f["type"].removeprefix("TYPE_"),
                       f.get("typeName", "").removeprefix(".tinkle.v1."),
                       f["label"] == "LABEL_REPEATED", f.get("proto3Optional", False))
                      for f in fields if f["number"] >= additions[0][1]]
            self.assertEqual(additions, actual, name)
        self.assert_fields("PollResults", [
            ("total_voters", 1, "INT32", "", False, False),
            ("results", 2, "MESSAGE", "PollAnswerResult", True, False),
        ])
        self.assert_fields("PollAnswerResult", [
            ("option", 1, "BYTES", "", False, False),
            ("voters", 2, "INT32", "", False, False),
            ("chosen", 3, "BOOL", "", False, False),
            ("correct", 4, "BOOL", "", False, True),
        ])

    def test_file_context_oneof_and_request_tags(self):
        """Pin a single typed authorization context on both file read calls."""
        self.assert_oneof("FileAccessContext", "reference",
                          ["message", "profile_photo", "sticker_asset", "chat_photo"])
        self.assert_fields("FileAccessContext", [
            ("message", 1, "MESSAGE", "MessageFileReference", False, False),
            ("profile_photo", 2, "MESSAGE", "ProfilePhotoReference", False, False),
            ("sticker_asset", 3, "MESSAGE", "StickerAssetReference", False, False),
            ("chat_photo", 4, "MESSAGE", "ChatPhotoReference", False, False),
        ])
        for name, tag in (("GetFileInfoRequest", 2), ("DownloadPartRequest", 4)):
            field = self.descriptor(name)["field"][-1]
            self.assertEqual(("file_access_context", tag, ".tinkle.v1.FileAccessContext"),
                             (field["name"], field["number"], field["typeName"]))
        self.assert_fields("MessageFileReference", [
            ("target", 1, "MESSAGE", "Target", False, False),
            ("message_id", 2, "INT64", "", False, False),
        ])
        self.assert_fields("ProfilePhotoReference", [
            ("user_id", 1, "INT64", "", False, False),
            ("photo_id", 2, "INT64", "", False, False),
        ])
        self.assert_fields("StickerAssetReference", [
            ("asset_id", 1, "INT64", "", False, False),
            ("asset_version", 2, "UINT64", "", False, False),
        ])
        self.assert_fields("ChatPhotoReference", [
            ("chat_id", 1, "INT64", "", False, False),
            ("photo_id", 2, "INT64", "", False, False),
        ], files.FILES_FILE)

    def test_authoring_service_methods_and_no_emoji_service(self):
        """Expose unified assets/packs and profile-photo lifecycle operations."""
        expected = {
            "StickersService": ["CreateStickerAsset", "UpdateStickerAsset",
                                "DeleteStickerAsset", "GetStickerAssets", "GetOwnedPacks",
                                "CreatePack", "UpdatePack", "DeletePack", "AddPackAsset",
                                "RemovePackAsset", "ReorderPackAssets", "PublishPack", "UnpublishPack"],
            "AccountService": ["SetProfilePhoto", "GetProfilePhotos",
                               "SelectProfilePhoto", "DeleteProfilePhoto"],
        }
        for service, additions in expected.items():
            methods = self.declarations["service"]["tinkle.v1." + service][1]["method"]
            self.assertEqual(additions, [m["name"] for m in methods][-len(additions):])
            for method in methods:
                self.assertEqual(".tinkle.v1." + method["name"] + "Request", method["inputType"])
                self.assertEqual(".tinkle.v1." + method["name"] + "Response", method["outputType"])
                self.assertFalse(method.get("clientStreaming", False))
                self.assertFalse(method.get("serverStreaming", False))
        self.assertNotIn("tinkle.v1.EmojiService", self.declarations["service"])
        for name, tag in (("GetInstalledPacksRequest", 1), ("SearchPacksRequest", 4),
                          ("GetArchivedPacksRequest", 3), ("GetOwnedPacksRequest", 1)):
            field = next(f for f in self.descriptor(name)["field"] if f["name"] == "kind")
            self.assertEqual((tag, ".tinkle.v1.PackKind"), (field["number"], field["typeName"]))

    def test_validation_and_kind_enums(self):
        """Keep validation profile/version explicit and kinds independent of format."""
        self.assert_fields("MediaValidation", [
            ("profile", 1, "ENUM", "MediaValidationProfile", False, False),
            ("version", 2, "UINT32", "", False, False),
        ])
        for name, prefix, values, filename in (
            ("StickerKind", "STICKER_KIND_", ["UNSPECIFIED", "STICKER", "CUSTOM_EMOJI"], files.MEDIA_FILE),
            ("PackKind", "PACK_KIND_", ["UNSPECIFIED", "STICKER", "CUSTOM_EMOJI"], "tinkle/v1/stickers.proto"),
            ("MediaValidationProfile", "MEDIA_VALIDATION_PROFILE_", ["UNSPECIFIED", "STRICT_LOSSLESS"], files.MEDIA_FILE),
            ("ImageFormat", "IMAGE_FORMAT_", ["UNSPECIFIED", "PNG", "WEBP"], files.MEDIA_FILE),
            ("MessageScheduledState", "MESSAGE_SCHEDULED_STATE_", ["UNSPECIFIED", "NOT_SCHEDULED", "PENDING", "SENT"], "tinkle/v1/messages.proto"),
        ):
            self.assert_enum_values(name, [prefix + v for v in values], filename)
            descriptor = self.declarations["enum"]["tinkle.v1." + name][1]
            self.assertEqual(list(range(len(values))), [v["number"] for v in descriptor["value"]])
        for name in ("StickerAssetSource", "ProfilePhotoSource"):
            fields = self.descriptor(name)["field"]
            self.assertEqual(["file_id", "metadata", "variants"], [f["name"] for f in fields])
            self.assertFalse(any(f["name"] in ("url", "data", "path") for f in fields))

    def test_messaging_round_trips(self):
        """Round-trip large IDs, quiz bytes, thread roots, and scheduled albums."""
        fixture = {"messageId": "9007199254740993", "albumId": "9007199254740995",
                   "scheduledState": "MESSAGE_SCHEDULED_STATE_PENDING", "scheduleDate": 1800000000,
                   "replyTo": {"replyToMsgId": "9", "replyToTopId": "7"},
                   "media": {"poll": {"id": "8", "results": {"totalVoters": 2,
                       "results": [{"option": "AP8=", "voters": 2, "chosen": True, "correct": False}]}}}}
        self.assertEqual(fixture, self.round_trip(fixture, "Message"))
        quiz = {"quiz": True, "correctAnswers": ["AP8="], "answers": [{"text": "yes", "option": "AP8="}]}
        self.assertEqual(quiz, self.round_trip(quiz, "PollSource"))
        for message, fixture in (("SearchRequest", {"query": "x", "cursor": "opaque"}),
                                 ("SearchResponse", {"moreAvailable": False}),
                                 ("ReplyInput", {"replyToMsgId": "9", "replyToTopId": "7"})):
            self.assertEqual(fixture, self.round_trip(fixture, message))

    def test_contexts_round_trip_and_conflicts(self):
        """Preserve each context and reject JSON with conflicting oneof arms."""
        contexts = [{"message": {"target": {"chatId": "4"}, "messageId": "9007199254740993"}},
                    {"profilePhoto": {"userId": "2", "photoId": "3"}},
                    {"stickerAsset": {"assetId": "5", "assetVersion": "2"}},
                    {"chatPhoto": {"chatId": "9007199254740993", "photoId": "9007199254740995"}}]
        for index, context in enumerate(contexts):
            for name in ("GetFileInfoRequest", "DownloadPartRequest"):
                fixture = {"fileId": "9007199254740995", "fileAccessContext": context}
                self.assertEqual(fixture, self.round_trip(fixture, name))
            for other in contexts[index + 1:]:
                conflict = dict(context, **other)
                self.assertNotEqual(0, self.convert(conflict, "FileAccessContext", check=False).returncode)

    def test_asset_and_profile_round_trips(self):
        """Preserve animated WebP metadata, lossless policy, variants, and fallback."""
        validation = {"profile": "MEDIA_VALIDATION_PROFILE_STRICT_LOSSLESS", "version": 1}
        source = {"fileId": "9007199254740993", "metadata": {
            "width": 128, "height": 128, "format": "STICKER_FORMAT_WEBP",
            "animated": True, "durationMs": "1000", "frameCount": 30, "validation": validation}}
        fixture = {"kind": "STICKER_KIND_CUSTOM_EMOJI", "source": source, "fallbackText": ":wave:"}
        self.assertEqual(fixture, self.round_trip(fixture, "CreateStickerAssetRequest"))
        photo = {"fileId": "9007199254740993", "metadata": {"width": 512, "height": 512,
                 "format": "IMAGE_FORMAT_PNG", "validation": validation},
                 "variants": [{"fileId": "8", "role": "MEDIA_VARIANT_ROLE_THUMBNAIL", "width": 128, "height": 128}]}
        request = {"source": photo, "expectedRevision": "1"}
        self.assertEqual(request, self.round_trip(request, "SetProfilePhotoRequest"))
        assets = {"assets": [{"id": "9007199254740993", "fileId": "8",
                  "kind": "STICKER_KIND_CUSTOM_EMOJI", "ownerId": "7", "fallbackText": ":wave:",
                  "assetVersion": "1"}]}
        self.assertEqual(assets, self.round_trip(assets, "GetStickerAssetsResponse"))
        self.assertEqual({"selectedPhotoId": "0"}, self.round_trip({"selectedPhotoId": "0"}, "GetProfilePhotosResponse"))

    def test_pack_lifecycle_round_trips(self):
        """Exercise every new pack mutation through the real binary/JSON codec."""
        pack = {"id": "9007199254740993", "name": "Wave", "shortName": "wave_pack",
                "kind": "PACK_KIND_CUSTOM_EMOJI", "ownerId": "9", "published": True, "packRevision": "4",
                "stickerCount": 1, "stickers": [{"id": "7", "fileId": "8",
                    "kind": "STICKER_KIND_CUSTOM_EMOJI", "fallbackText": ":wave:", "assetVersion": "2"}]}
        for method, fixture in (
            ("CreatePack", {"name": "Wave", "shortName": "wave_pack", "kind": "PACK_KIND_CUSTOM_EMOJI"}),
            ("UpdatePack", {"packId": pack["id"], "name": "New name", "expectedRevision": "3"}),
            ("AddPackAsset", {"packId": pack["id"], "assetId": "7", "assetVersion": "2", "expectedRevision": "3"}),
            ("RemovePackAsset", {"packId": pack["id"], "assetId": "7", "expectedRevision": "3"}),
            ("ReorderPackAssets", {"packId": pack["id"], "assetIds": ["9", "7"], "expectedRevision": "3"}),
            ("PublishPack", {"packId": pack["id"], "expectedRevision": "3"}),
            ("UnpublishPack", {"packId": pack["id"], "expectedRevision": "3"}),
        ):
            with self.subTest(method=method):
                self.assertEqual(fixture, self.round_trip(fixture, method + "Request"))
                self.assertEqual({"pack": pack}, self.round_trip({"pack": pack}, method + "Response"))

    def test_explicit_defaults_and_codec_rejections(self):
        """Preserve explicit false/empty values and reject wrong known-field types."""
        for name, fixture in (
            ("StickerMetadata", {"animated": False, "durationMs": "0", "frameCount": 0}),
            ("UpdateStickerAssetRequest", {"assetId": "8", "fallbackText": ""}),
            ("GetProfilePhotosRequest", {"userId": "0"}),
            ("PollAnswerResult", {"option": "AA==", "correct": False}),
        ):
            expected = dict(fixture)
            if name == "StickerMetadata":
                del expected["animated"]  # implicit false, unlike optional numeric zero
            self.assertEqual(expected, self.round_trip(fixture, name))
        for name, fixture in (
            ("GetStickerAssetsRequest", {"assetIds": ["9223372036854775808"]}),
            ("CreateStickerAssetRequest", {"kind": []}),
            ("StickerMetadata", {"animated": "true"}),
            ("MediaValidation", {"version": -1}),
            ("PollSource", {"correctAnswers": [7]}),
            ("GetProfilePhotosResponse", {"photos": {}}),
            ("SearchResponse", {"moreAvailable": "false"}),
            ("UpdatePackRequest", {"packId": "7", "expectedRevision": -1}),
            ("AssetReference", {"assetId": "7", "assetVersion": "18446744073709551616"}),
        ):
            with self.subTest(message=name, fixture=fixture):
                self.assertNotEqual(0, self.convert(fixture, name, check=False).returncode)

    def test_codec_does_not_enforce_authoring_policy(self):
        """Do not confuse a valid wire shape with validated files or authorization."""
        # Proto3 carries unknown numeric enums and wrong policy versions. Buf's
        # converter also discards unknown JSON names; server validation must
        # fail closed on unsupported values and inspect the actual file bytes.
        for name, fixture in (
            ("MediaValidation", {"profile": 99, "version": 99}),
            ("StickerMetadata", {"format": "STICKER_FORMAT_WEBP", "animated": True}),
            ("ProfilePhotoSource", {"fileId": "-1"}),
            ("CreateStickerAssetRequest", {"kind": 99}),
        ):
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_revision_and_exact_reference_contract(self):
        """Pin exact asset identity and mandatory CAS tokens without widening old tags."""
        self.assert_manifest({"AssetReference": [("asset_id", 1, "int64"),
                                                  ("asset_version", 2, "uint64")]})
        additions = {
            "StickerView": [("asset_version", 10, "TYPE_UINT64")],
            "StickerPackPreview": [("pack_revision", 9, "TYPE_UINT64")],
            "StickerPackDetail": [("pack_revision", 10, "TYPE_UINT64")],
            "UpdateStickerAssetRequest": [("expected_version", 4, "TYPE_UINT64")],
            "DeleteStickerAssetRequest": [("expected_version", 2, "TYPE_UINT64")],
            "UpdatePackRequest": [("expected_revision", 4, "TYPE_UINT64")],
            "DeletePackRequest": [("expected_revision", 2, "TYPE_UINT64")],
            "AddPackAssetRequest": [("asset_version", 3, "TYPE_UINT64"),
                                    ("expected_revision", 4, "TYPE_UINT64")],
            "RemovePackAssetRequest": [("expected_revision", 3, "TYPE_UINT64")],
            "ReorderPackAssetsRequest": [("expected_revision", 3, "TYPE_UINT64")],
            "PublishPackRequest": [("expected_revision", 2, "TYPE_UINT64")],
            "UnpublishPackRequest": [("expected_revision", 2, "TYPE_UINT64")],
            "SetProfilePhotoRequest": [("expected_revision", 2, "TYPE_UINT64")],
            "SelectProfilePhotoRequest": [("expected_revision", 2, "TYPE_UINT64")],
            "DeleteProfilePhotoRequest": [("expected_revision", 2, "TYPE_UINT64")],
            "SetProfilePhotoResponse": [("gallery_revision", 2, "TYPE_UINT64")],
            "SelectProfilePhotoResponse": [("gallery_revision", 2, "TYPE_UINT64")],
            "DeleteProfilePhotoResponse": [("gallery_revision", 3, "TYPE_UINT64")],
            "GetProfilePhotosResponse": [("gallery_revision", 3, "TYPE_UINT64")],
            "StickerSource": [("asset_version", 5, "TYPE_UINT64")],
            "StickerAssetReference": [("asset_version", 2, "TYPE_UINT64")],
            "Entity": [("asset_version", 9, "TYPE_UINT64")],
            "Reaction": [("asset_version", 3, "TYPE_UINT64")],
            "SearchRequest": [("offset_message_id", 14, "TYPE_INT64")],
        }
        for name, expected in additions.items():
            actual = [(f["name"], f["number"], f["type"]) for f in self.descriptor(name)["field"]
                      if f["number"] >= expected[0][1]]
            self.assertEqual(expected, actual, name)

    def test_exact_resolution_and_cas_codec(self):
        """Preserve uint64 versions, scoped exact lookups and full-width search offsets."""
        large = "18446744073709551615"
        fixtures = [
            ("GetStickerAssetsRequest", {"references": [{"assetId": "7", "assetVersion": large},
                                                         {"assetId": "7", "assetVersion": "1"}],
              "messageReference": {"target": {"chatId": "8"}, "messageId": "9"}}),
            ("GetStickerAssetsRequest", {"assetIds": ["7"]}),
            ("StickerView", {"id": "7", "fileId": "8", "assetVersion": large}),
            ("UpdateStickerAssetRequest", {"assetId": "7", "fallbackText": ":new:", "expectedVersion": large}),
            ("AddPackAssetRequest", {"packId": "9", "assetId": "7", "assetVersion": large,
                                     "expectedRevision": large}),
            ("GetProfilePhotosResponse", {"galleryRevision": large, "selectedPhotoId": "0"}),
            ("GetProfilePhotosResponse", {"photos": []}),
            ("SelectProfilePhotoRequest", {"photoId": "7", "expectedRevision": large}),
            ("SearchRequest", {"target": {"chatId": "8"}, "offsetMessageId": "9007199254740993"}),
        ]
        for name, fixture in fixtures:
            expected = {} if fixture == {"photos": []} else fixture
            self.assertEqual(expected, self.round_trip(fixture, name))
        # Exact send and file identities preserve versions beyond signed int64.
        for name, fixture in (
            ("StickerSource", {"fileId": "8", "assetId": "7", "assetVersion": large}),
            ("StickerAssetReference", {"assetId": "7", "assetVersion": large}),
            ("Entity", {"type": "ENTITY_TYPE_CUSTOM_EMOJI",
                        "customEmojiId": "7", "fallbackText": ":wave:", "assetVersion": large}),
            ("Reaction", {"emoticon": ":wave:", "customEmojiId": "7", "assetVersion": large}),
        ):
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_gallery_and_pack_capacity_shapes(self):
        """Encode the documented 10/100 boundaries; protobuf itself enforces no cap."""
        account = (files.REPO_ROOT / "tinkle/v1/account.proto").read_text()
        stickers = (files.REPO_ROOT / "tinkle/v1/stickers.proto").read_text()
        self.assertIn("at most 10 photos", account)
        self.assertIn("at most 100, with no duplicates", stickers)
        photos = [{"photoId": str(i + 1), "fileId": str(i + 101)} for i in range(10)]
        gallery = {"photos": photos, "selectedPhotoId": "1", "galleryRevision": "11"}
        self.assertEqual(gallery, self.round_trip(gallery, "GetProfilePhotosResponse"))
        pack = {"id": "1", "packRevision": "101", "stickerCount": 100,
                "stickers": [{"id": str(i + 1), "assetVersion": "1"} for i in range(100)]}
        self.assertEqual(pack, self.round_trip(pack, "StickerPackDetail"))

    def test_metadata_change_revisions_and_notification_descriptors(self):
        """Pin metadata kinds, independent revisions and transport-neutral hint data."""
        for name in ("MessageChanged", "TypingChanged"):
            self.descriptor(name, "tinkle/v1/messages.proto")
        descriptor = self.declarations["enum"]["tinkle.v1.TargetChangeKind"][1]
        self.assertEqual([
            ("TARGET_CHANGE_KIND_UNSPECIFIED", 0), ("TARGET_CHANGE_KIND_EDITED", 1),
            ("TARGET_CHANGE_KIND_DELETED", 2), ("TARGET_CHANGE_KIND_REVOKED", 3),
            ("TARGET_CHANGE_KIND_PIN", 4), ("TARGET_CHANGE_KIND_REACTION", 5),
            ("TARGET_CHANGE_KIND_POLL", 6), ("TARGET_CHANGE_KIND_ACK", 7),
        ], [(value["name"], value["number"]) for value in descriptor["value"]])
        for name, field, tag in (("Message", "body_revision", 18),
                                 ("TargetChange", "message_revision", 5)):
            actual = self.descriptor(name)["field"][-1]
            self.assertEqual((field, tag, "TYPE_INT64", True),
                             (actual["name"], actual["number"], actual["type"],
                              actual.get("proto3Optional", False)))
        self.assert_manifest({
            "MessageChanged": [("target", 1, "Target"), ("message_id", 2, "int64"),
                               ("body_revision", 3, "int64"), ("change_kind", 4, "TargetChangeKind")],
            "TypingChanged": [("target", 1, "Target"), ("actor_id", 2, "int64"),
                              ("action", 3, "TypingAction"), ("expires_at", 4, ".google.protobuf.Timestamp"),
                              ("top_msg_id", 5, "optional int64")],
        })
        # Data messages do not add an RPC or extend the connectivity-only service.
        methods = self.declarations["service"]["tinkle.v1.UpdatesService"][1]["method"]
        self.assertEqual(["ObserveConnectivity"], [method["name"] for method in methods])

    def test_metadata_event_and_current_body_codec(self):
        """Preserve exact event revisions even when hydration contains a newer body."""
        body = {"messageId": "9007199254740993", "acceptSeq": "10", "bodyRevision": "9007199254740995"}
        for kind in ("PIN", "REACTION", "POLL", "ACK"):
            fixture = {"messageId": body["messageId"], "kind": "TARGET_CHANGE_KIND_" + kind,
                       "message": body, "acceptSeq": "700", "messageRevision": "12"}
            decoded = self.round_trip(fixture, "TargetChange")
            self.assertEqual(fixture, decoded)
            self.assertNotIn("editDate", decoded["message"])
        # A complete body can omit its revision; omission is not version zero.
        self.assertEqual({"messageId": "1"}, self.round_trip({"messageId": "1"}, "Message"))
        for name, fixture in (("Message", {"bodyRevision": "0"}),
                              ("TargetChange", {"messageRevision": "0"})):
            self.assertEqual(fixture, self.round_trip(fixture, name))
        # The stable processed cursor need not be the last visible mutation.
        self.assertEqual({"moreAvailable": False, "lastAcceptSeq": "701"}, self.round_trip(
            {"moreAvailable": False, "lastAcceptSeq": "701"}, "GetTargetChangesResponse"))

    def test_typed_notification_payload_codec(self):
        """Round-trip hint payloads, expiry/thread presence and all metadata kinds."""
        for kind in ("PIN", "REACTION", "POLL", "ACK"):
            fixture = {"target": {"chatId": "9007199254740993"}, "messageId": "9",
                       "bodyRevision": "9007199254740995", "changeKind": "TARGET_CHANGE_KIND_" + kind}
            self.assertEqual(fixture, self.round_trip(fixture, "MessageChanged"))
        for action in ("TYPING_ACTION_TYPING", "TYPING_ACTION_CANCEL"):
            fixture = {"target": {"chatId": "9"}, "actorId": "9007199254740993", "action": action,
                       "expiresAt": "2026-11-10T12:00:00Z", "topMsgId": "9007199254740995"}
            self.assertEqual(fixture, self.round_trip(fixture, "TypingChanged"))
        for name, fixture in (("MessageChanged", {"bodyRevision": "9223372036854775808"}),
                              ("TypingChanged", {"topMsgId": []})):
            self.assertNotEqual(0, self.convert(fixture, name, check=False).returncode)


if __name__ == "__main__":
    unittest.main()
