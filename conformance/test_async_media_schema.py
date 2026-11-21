"""Domain pending descriptor/codec checks; not worker, authorization or race tests."""

import base64
import json
import re
import unittest

import test_files_schema as files
from test_thumbnail_schema import THUMBNAILS


# Exact RPC additions since the pinned baseline, in owning service order.
METHODS = {
    "MessagesService": ["GetChatPhotoUpdate", "CancelChatPhotoUpdate", "GetRoomMembers",
                        "GetRoomOnlineCount", "GetSendStatus", "CancelSend"],
    "ChannelsService": ["GetPhotoUpdate", "CancelPhotoUpdate"],
    "AccountService": ["GetProfilePhotoUpdate", "CancelProfilePhotoUpdate"],
    "StickersService": ["GetAssetChange", "CancelAssetChange"],
}
# Last committed schema before domain pending/thumbnail work. It has no generic
# publication fields or RPCs: only the thumbnail fields below may be removed.
BASELINE_REVISION = "e0038da40641a39ee90e8d4b95a8c3f36e213044"
REMOVED_FIELDS = {name: {("variants", tags[0])} for name, tags in THUMBNAILS.items()}
REMOVED_FIELDS["StickerView"].add(("thumb_file_id", 3))
# Stable UUID and width boundaries used in codec fixtures, not server-valid media.
REQUEST_ID = "6c651447-0b44-4f20-b311-cfdbe00cb60f"
LARGE_ID = "9007199254740993"
MAX_U64 = "18446744073709551615"


class AsyncMediaSchemaTests(files.BufSchemaTestCase):
    """Pin direct domain lifecycles, retained identities and independent enrichment."""

    def test_existing_fields_enums_and_methods_are_preserved(self):
        """Allow exact removals and a global tag reset, not name/type/presence drift."""
        baseline = json.loads(files.run_buf(
            "build", ".git#ref=" + BASELINE_REVISION, "--exclude-source-info",
            "--as-file-descriptor-set", "-o", "-#format=json").stdout)
        old_services = {"tinkle.v1." + s["name"] for p in baseline["file"]
                        if p["name"].startswith("tinkle/") for s in p.get("service", [])}
        self.assertEqual(old_services, set(self.declarations["service"]))

        def compare_enums(items, current, prefix):
            """Preserve enum names/values, including enums inside nested messages."""
            for old in items:
                if prefix == "tinkle.v1." and old["name"] == "MediaVariantRole":
                    self.assertNotIn(old["name"], current)
                    continue
                new = current[old["name"]]
                self.assertEqual(old["value"], new["value"][:len(old["value"])], prefix + old["name"])

        def compare_messages(items, prefix, current):
            """Keep all prior field descriptors except numbers and exact retirements."""
            for old in items:
                if prefix == "tinkle.v1." and old["name"] in ("MediaVariant", "MediaVariantSource"):
                    continue
                new = current[old["name"]]
                identity = prefix + old["name"]
                new_fields = {f["name"]: f for f in new.get("field", [])}
                removed = {(f["name"], f["number"]) for f in old.get("field", [])
                           if f["name"] not in new_fields}
                self.assertEqual(REMOVED_FIELDS.get(old["name"], set()), removed, identity)
                for field in old.get("field", []):
                    if (field["name"], field["number"]) in removed:
                        continue
                    self.assertEqual({k: v for k, v in field.items() if k != "number"},
                                     {k: v for k, v in new_fields[field["name"]].items()
                                      if k != "number"}, identity + "." + field["name"])
                old_oneofs = old.get("oneofDecl", [])
                self.assertEqual(old_oneofs, new.get("oneofDecl", [])[:len(old_oneofs)], identity)
                # Empty messages stay empty, rather than acquiring reset placeholders.
                if not old.get("field"):
                    self.assertFalse(new.get("field"), identity)
                compare_enums(old.get("enumType", []),
                              {e["name"]: e for e in new.get("enumType", [])}, identity + ".")
                compare_messages(old.get("nestedType", []), identity + ".",
                                 {m["name"]: m for m in new.get("nestedType", [])})

        for proto in baseline["file"]:
            if not proto["name"].startswith("tinkle/"):
                continue
            current = {name.removeprefix("tinkle.v1."): declaration
                       for name, (path, declaration) in self.declarations["message"].items()
                       if path == proto["name"]}
            compare_messages(proto.get("messageType", []), "tinkle.v1.", current)
            compare_enums(proto.get("enumType", []),
                          {name.removeprefix("tinkle.v1."): declaration
                           for name, (path, declaration) in self.declarations["enum"].items()
                           if path == proto["name"]}, "tinkle.v1.")
            for service in proto.get("service", []):
                new = self.declarations["service"]["tinkle.v1." + service["name"]][1]
                old_names = {m["name"] for m in service["method"]}
                self.assertEqual(service["method"], [m for m in new["method"] if m["name"] in old_names])
                self.assertEqual(METHODS.get(service["name"], []),
                                 [m["name"] for m in new["method"] if m["name"] not in old_names])

    def test_removed_contract_and_fields(self):
        """Remove generic publication and retired fields, without reserved placeholders."""
        for kind in self.declarations.values():
            self.assertFalse(any("MediaPublication" in name for name in kind))
        for path in files.REPO_ROOT.glob("tinkle/v1/media_publication*.proto"):
            self.fail("Deleted contract still exists: " + str(path))
        for name, removed in REMOVED_FIELDS.items():
            descriptor = self.descriptor(name)
            self.assertFalse({field for field, _ in removed} &
                             {f["name"] for f in descriptor["field"]}, name)
        for _, descriptor in self.declarations["message"].values():
            names = {f["name"] for f in descriptor.get("field", [])}
            self.assertFalse({"publication", "publication_operation", "request_sha256", "locator"} & names)

    def test_direct_request_ids_and_response_statuses(self):
        """Keep request IDs direct, send keys unchanged, responses outside a union."""
        for name, tag in (("SetProfilePhoto", 3), ("EditPhoto", 3),
                          ("CreateStickerAsset", 4), ("UpdateStickerAsset", 5)):
            field = self.descriptor(name + "Request")["field"][-1]
            self.assertEqual(("request_id", tag, "TYPE_STRING"),
                             (field["name"], field["number"], field["type"]))
        for name in ("SendMediaRequest", "SendAlbumRequest", "EditChatPhotoRequest"):
            self.assertNotIn("request_id", [f["name"] for f in self.descriptor(name)["field"]])
        for method, tag, field_name, kind in (
            ("SendMedia", 4, "send_status", "SendStatus"), ("SendAlbum", 4, "send_status", "SendStatus"),
            ("EditChatPhoto", 2, "photo_update", "ChatPhotoUpdate"),
            ("EditPhoto", 2, "photo_update", "ChannelPhotoUpdate"),
            ("SetProfilePhoto", 3, "photo_update", "ProfilePhotoUpdate"),
            ("CreateStickerAsset", 2, "asset_change", "AssetChange"),
            ("UpdateStickerAsset", 2, "asset_change", "AssetChange"),
        ):
            field = self.descriptor(method + "Response")["field"][-1]
            self.assertEqual((field_name, tag, ".tinkle.v1." + kind),
                             (field["name"], field["number"], field["typeName"]))
            self.assertNotIn("oneofIndex", field)
        self.assert_oneof("Media", "media", ["photo", "document", "geo", "contact", "poll"])
        self.assert_oneof("ChatPhotoSource", "input", ["file_id", "empty", "photo"])

    def test_family_status_shapes_and_enums(self):
        """Pin every field/tag/type/presence and each family's own state/failure enum."""
        def field(name, tag, kind, reference="", repeated=False, optional=False):
            """Spell the shared descriptor assertion tuple without changing semantics."""
            return (name, tag, kind, reference, repeated, optional)

        terminal = field("retain_until", 8, "MESSAGE", ".google.protobuf.Timestamp")
        for family in ("ChatPhotoUpdate", "ChannelPhotoUpdate"):
            channel = family.startswith("Channel")
            self.assert_fields(family, [
                field("channel_id" if channel else "chat_id", 1, "INT64"),
                field("request_id" if channel else "operation_id", 2, "STRING" if channel else "INT64"),
                field("state", 3, "ENUM", family + "State"), field("revision", 4, "UINT64"),
                field("failure", 5, "ENUM", family + "Failure"), field("photo_id", 6, "INT64", optional=True),
                field("reference_withheld", 7, "BOOL", optional=True), terminal,
            ])
        self.assert_fields("ProfilePhotoUpdate", [field("request_id", 1, "STRING"),
            field("state", 2, "ENUM", "ProfilePhotoUpdateState"), field("revision", 3, "UINT64"),
            field("failure", 4, "ENUM", "ProfilePhotoUpdateFailure"), field("photo_id", 5, "INT64", optional=True),
            field("reference_withheld", 6, "BOOL", optional=True), field("gallery_revision", 7, "UINT64"), terminal])
        self.assert_fields("AssetChange", [field("request_id", 1, "STRING"),
            field("asset_id", 2, "INT64", optional=True), field("state", 3, "ENUM", "AssetChangeState"),
            field("revision", 4, "UINT64"), field("failure", 5, "ENUM", "AssetChangeFailure"),
            field("accepted", 6, "MESSAGE", "AssetReference"), field("reference_withheld", 7, "BOOL", optional=True), terminal])
        self.assert_fields("SendStatus", [field("target", 1, "MESSAGE", "Target"),
            field("idempotency_key", 2, "INT64"), field("state", 3, "ENUM", "SendState"),
            field("revision", 4, "UINT64"), field("failure", 5, "ENUM", "SendFailure"),
            field("accepted", 6, "MESSAGE", "SendReceipt", repeated=True),
            field("retain_until", 7, "MESSAGE", ".google.protobuf.Timestamp")])
        self.assert_fields("SendReceipt", [field("idempotency_key", 1, "INT64"),
            field("message_id", 2, "INT64", optional=True), field("album_id", 3, "INT64", optional=True),
            field("reference_withheld", 4, "BOOL", optional=True)])
        for family in ("Send", "ChatPhotoUpdate", "ChannelPhotoUpdate", "ProfilePhotoUpdate", "AssetChange"):
            for suffix, values in (("State", ("UNSPECIFIED", "PENDING", "PROCESSING", "SUCCEEDED", "FAILED", "CANCELED")),
                                   ("Failure", ("UNSPECIFIED", "INVALID_MEDIA", "NOT_AUTHORIZED", "PRECONDITION",
                                                "RESOURCE_LIMIT", "PROCESSING"))):
                name = family + suffix
                prefix = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper() + "_"
                actual = self.declarations["enum"]["tinkle.v1." + name][1]["value"]
                self.assertEqual([(prefix + v, i) for i, v in enumerate(values)],
                                 [(v["name"], v["number"]) for v in actual])

    def test_owner_rpc_shapes(self):
        """Expose only owner unary recovery with ordinary domain selectors."""
        for service, additions in METHODS.items():
            methods = self.declarations["service"]["tinkle.v1." + service][1]["method"]
            for name in additions:
                method = next(m for m in methods if m["name"] == name)
                self.assertEqual(".tinkle.v1." + name + "Request", method["inputType"])
                self.assertEqual(".tinkle.v1." + name + "Response", method["outputType"])
                self.assertFalse(method.get("clientStreaming", False))
                self.assertFalse(method.get("serverStreaming", False))
        for get, cancel, status, status_field, selectors, bodies in (
            ("GetSendStatus", "CancelSend", "SendStatus", "send_status",
             [("target", 1, "MESSAGE", "Target", False, False), ("idempotency_key", 2, "INT64", "", False, False)],
             [("messages", 2, "MESSAGE", "Message", True, False), ("users", 3, "MESSAGE", "User", True, False),
              ("chats", 4, "MESSAGE", "Chat", True, False)]),
            ("GetChatPhotoUpdate", "CancelChatPhotoUpdate", "ChatPhotoUpdate", "photo_update",
             [("chat_id", 1, "INT64", "", False, False), ("operation_id", 2, "INT64", "", False, False)],
             [("photo", 2, "MESSAGE", "ChatPhoto", False, False)]),
            ("GetPhotoUpdate", "CancelPhotoUpdate", "ChannelPhotoUpdate", "photo_update",
             [("channel_id", 1, "INT64", "", False, False), ("request_id", 2, "STRING", "", False, False)],
             [("photo", 2, "MESSAGE", "ChatPhoto", False, False)]),
            ("GetProfilePhotoUpdate", "CancelProfilePhotoUpdate", "ProfilePhotoUpdate", "photo_update",
             [("request_id", 1, "STRING", "", False, False)], [("photo", 2, "MESSAGE", "ProfilePhoto", False, False)]),
            ("GetAssetChange", "CancelAssetChange", "AssetChange", "asset_change",
             [("request_id", 1, "STRING", "", False, False), ("asset_id", 2, "INT64", "", False, True)],
             [("asset", 2, "MESSAGE", "StickerView", False, False)]),
        ):
            self.assert_fields(get + "Request", selectors)
            self.assert_fields(cancel + "Request", selectors)
            header = [(status_field, 1, "MESSAGE", status, False, False)]
            self.assert_fields(get + "Response", header + bodies)
            self.assert_fields(cancel + "Response", header)
            self.assertFalse(self.descriptor(get + "Response").get("oneofDecl"))

    def test_all_states_and_failure_categories_round_trip(self):
        """Distinguish claimed work from durable cancellation, with uint64 revisions."""
        for name, family in (("SendStatus", "Send"), ("ChatPhotoUpdate", "ChatPhotoUpdate"),
                             ("ChannelPhotoUpdate", "ChannelPhotoUpdate"),
                             ("ProfilePhotoUpdate", "ProfilePhotoUpdate"), ("AssetChange", "AssetChange")):
            prefix = re.sub(r"(?<!^)(?=[A-Z])", "_", family).upper()
            for state in ("PENDING", "PROCESSING", "SUCCEEDED", "FAILED", "CANCELED"):
                fixture = {"state": prefix + "_STATE_" + state, "revision": MAX_U64}
                if state == "FAILED":
                    fixture["failure"] = prefix + "_FAILURE_INVALID_MEDIA"
                if state in ("SUCCEEDED", "FAILED", "CANCELED"):
                    fixture["retainUntil"] = "2027-01-01T00:00:00Z"
                self.assertEqual(fixture, self.round_trip(fixture, name))
            for failure in ("INVALID_MEDIA", "NOT_AUTHORIZED", "PRECONDITION", "RESOURCE_LIMIT", "PROCESSING"):
                fixture = {"state": prefix + "_STATE_FAILED", "failure": prefix + "_FAILURE_" + failure}
                self.assertEqual(fixture, self.round_trip(fixture, name))
            self.assertNotEqual(0, self.convert({"revision": "18446744073709551616"}, name, check=False).returncode)

    def test_lost_send_response_and_removed_album_identity_mapping(self):
        """Receipt codec keeps all ordered keys without any obsolete bodies."""
        for count in (1, 2, 10):
            keys = ["-9223372036854775808"] + [str(-i) for i in range(1, count)]
            accepted = [{"idempotencyKey": key, "messageId": str(100 + i), "referenceWithheld": False}
                        for i, key in enumerate(keys)]
            if count > 1:
                for receipt in accepted:
                    receipt["albumId"] = LARGE_ID
            status = {"target": {"chatId": LARGE_ID}, "idempotencyKey": keys[0],
                      "state": "SEND_STATE_SUCCEEDED", "revision": "3", "accepted": accepted}
            fixture = {"sendStatus": status}
            recovered = self.round_trip(fixture, "GetSendStatusResponse")
            self.assertNotIn("messages", recovered)
            self.assertEqual(fixture, recovered)
            selector = {"target": status["target"], "messageIds": [r["messageId"] for r in accepted]}
            self.assertEqual(selector, self.round_trip(selector, "GetMessagesRequest"))
            for key in keys:
                query = {"target": status["target"], "idempotencyKey": key}
                for name in ("GetSendStatusRequest", "CancelSendRequest"):
                    self.assertEqual(query, self.round_trip(query, name))
            accepted[0] = {"idempotencyKey": keys[0], "referenceWithheld": True}
            self.assertEqual(fixture, self.round_trip(fixture, "GetSendStatusResponse"))
            self.assertEqual(fixture, self.round_trip(fixture, "CancelSendResponse"))
            self.assertEqual(keys, [r["idempotencyKey"] for r in status["accepted"]])
        for fixture in ({}, {"referenceWithheld": False}, {"referenceWithheld": True}):
            self.assertEqual(fixture, self.round_trip(fixture, "SendReceipt"))

    def test_photo_and_asset_identities_without_current_bodies(self):
        """Recover accepted identities after deletion; never encode stale source data."""
        for response, field, status in (
            ("GetChatPhotoUpdateResponse", "photoUpdate", {"chatId": "9", "operationId": LARGE_ID,
             "state": "CHAT_PHOTO_UPDATE_STATE_SUCCEEDED", "photoId": "17", "referenceWithheld": False}),
            ("GetPhotoUpdateResponse", "photoUpdate", {"channelId": "9", "requestId": REQUEST_ID,
             "state": "CHANNEL_PHOTO_UPDATE_STATE_SUCCEEDED", "photoId": "18", "referenceWithheld": False}),
            ("GetProfilePhotoUpdateResponse", "photoUpdate", {"requestId": REQUEST_ID,
             "state": "PROFILE_PHOTO_UPDATE_STATE_SUCCEEDED", "photoId": "19", "galleryRevision": MAX_U64,
             "referenceWithheld": False}),
            ("GetAssetChangeResponse", "assetChange", {"requestId": REQUEST_ID, "assetId": "20",
             "state": "ASSET_CHANGE_STATE_SUCCEEDED", "accepted": {"assetId": "20", "assetVersion": MAX_U64},
             "referenceWithheld": False}),
        ):
            fixture = {field: status}
            self.assertEqual(fixture, self.round_trip(fixture, response))
            status.pop("photoId", None)
            status.pop("accepted", None)
            status["referenceWithheld"] = True
            self.assertEqual(fixture, self.round_trip(fixture, response))
        for name in ("GetAssetChangeRequest", "CancelAssetChangeRequest"):
            for fixture in ({"requestId": REQUEST_ID}, {"requestId": REQUEST_ID, "assetId": LARGE_ID}):
                self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_previews_processing_intent_and_representation_wiring(self):
        """Keep bounded hints distinct from thumbnails; no voice/worker expansion."""
        self.assert_fields("InlinePreview", [("width", 1, "UINT32", "", False, False),
            ("height", 2, "UINT32", "", False, False), ("jpeg", 3, "BYTES", "", False, False)])
        self.assert_enum_values("MediaProcessingIntent", ["MEDIA_PROCESSING_INTENT_" + v
            for v in ("UNSPECIFIED", "IMAGE", "VIDEO")], files.MEDIA_FILE)
        for size in (4096, 4097):
            fixture = {"width": 40, "height": 40, "jpeg": base64.b64encode(b"x" * size).decode()}
            # Codec permits arbitrary bytes; runtime validation must reject bad JPEGs/limits.
            self.assertEqual(fixture, self.round_trip(fixture, "InlinePreview"))
        for name, tag in (("PhotoSource", 3), ("VideoSource", 3), ("DocumentSource", 3),
                          ("AudioSource", 3), ("StickerSource", 5), ("ProfilePhotoSource", 3), ("StickerAssetSource", 3)):
            field = next(f for f in self.descriptor(name)["field"] if f["name"] == "inline_preview")
            self.assertEqual(("inline_preview", tag, ".tinkle.v1.InlinePreview"),
                             (field["name"], field["number"], field["typeName"]))
        for name, tag in (("Photo", 7), ("Document", 8), ("UserPhoto", 3),
                          ("ChatPhoto", 5), ("ProfilePhoto", 6), ("StickerView", 9)):
            fields = [f for f in self.descriptor(name)["field"]
                      if f["name"] in ("inline_preview", "representation_revision")]
            self.assertEqual([("inline_preview", tag), ("representation_revision", tag + 1)],
                             [(f["name"], f["number"]) for f in fields])
            self.assertTrue(fields[-1]["proto3Optional"])
            fixture = {"inlinePreview": {"width": 40, "height": 20, "jpeg": "/9j/2Q=="}, "representationRevision": MAX_U64}
            self.assertEqual(fixture, self.round_trip(fixture, name))
        self.assertNotIn("inline_preview", [f["name"] for f in self.descriptor("VoiceSource")["field"]])
        intent_field = next(f for f in self.descriptor("BeginUploadRequest")["field"]
                            if f["name"] == "processing_intent")
        self.assertTrue(intent_field["proto3Optional"])
        self.assertEqual({}, self.round_trip({}, "BeginUploadRequest"))
        for intent in ("IMAGE", "VIDEO", "UNSPECIFIED"):
            fixture = {"processingIntent": "MEDIA_PROCESSING_INTENT_" + intent}
            # Explicit optional enum presence preserves even zero; codec acceptance
            # does not make UNSPECIFIED a server-valid processing intent.
            self.assertTrue(self.encode(fixture, "BeginUploadRequest"))
            self.assertEqual(fixture, self.round_trip(fixture, "BeginUploadRequest"))

    def test_authored_send_album_and_direct_ids_round_trip(self):
        """Retain existing send options/draft/CAS without a nested opt-in."""
        photo = {"fileId": LARGE_ID, "inlinePreview": {"width": 40, "height": 20, "jpeg": "/9j/2Q=="},
                 "thumbnail": {"fileId": "9007199254740995", "width": 320, "height": 160}}
        send = {"target": {"chatId": "9"}, "media": {"photo": photo}, "message": "caption",
                "idempotencyKey": "-9223372036854775808", "silent": False,
                "clearDraft": True, "clearDraftDialogId": "7", "clearDraftRevision": "0"}
        self.assertEqual(send, self.round_trip(send, "SendMediaRequest"))
        album = {"target": send["target"], "items": [
            {"media": send["media"], "message": "caption", "idempotencyKey": send["idempotencyKey"]},
            {"media": {"video": {"fileId": "11"}}, "idempotencyKey": "12"}]}
        self.assertEqual(album, self.round_trip(album, "SendAlbumRequest"))
        for name, extra in (("SetProfilePhotoRequest", {"expectedRevision": MAX_U64}),
                            ("EditPhotoRequest", {"channelId": LARGE_ID}),
                            ("CreateStickerAssetRequest", {}),
                            ("UpdateStickerAssetRequest", {"assetId": LARGE_ID, "expectedVersion": MAX_U64})):
            fixture = dict(extra, requestId=REQUEST_ID)
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_domain_hint_shapes(self):
        """Hints carry exact domain identities/revisions, no generic kind or file grant."""
        manifests = {
            "SendStatusChanged": [("target", 1, "MESSAGE", "Target", False, False),
                ("idempotency_key", 2, "INT64", "", False, False), ("revision", 3, "UINT64", "", False, False)],
            "ChatPhotoUpdateChanged": [("chat_id", 1, "INT64", "", False, False),
                ("operation_id", 2, "INT64", "", False, False), ("revision", 3, "UINT64", "", False, False)],
            "ChannelPhotoUpdateChanged": [("channel_id", 1, "INT64", "", False, False),
                ("request_id", 2, "STRING", "", False, False), ("revision", 3, "UINT64", "", False, False)],
            "ProfilePhotoUpdateChanged": [("request_id", 1, "STRING", "", False, False),
                ("revision", 2, "UINT64", "", False, False)],
            "AssetChangeChanged": [("request_id", 1, "STRING", "", False, False),
                ("asset_id", 2, "INT64", "", False, True), ("revision", 3, "UINT64", "", False, False)],
            "StickerAssetRepresentationChanged": [("asset", 1, "MESSAGE", "AssetReference", False, False),
                ("main_file_id", 2, "INT64", "", False, False), ("representation_revision", 3, "UINT64", "", False, False)],
        }
        for name, owner in (("ChatPhotoRepresentationChanged", "chat_id"),
                            ("ProfilePhotoRepresentationChanged", "user_id")):
            manifests[name] = [(owner, 1, "INT64", "", False, False), ("photo_id", 2, "INT64", "", False, False),
                ("main_file_id", 3, "INT64", "", False, False), ("representation_revision", 4, "UINT64", "", False, False)]
        for name, manifest in manifests.items():
            self.assert_fields(name, manifest)
            fixture = {}
            for field, _, kind, reference, _, _ in manifest:
                key = field.split("_")[0] + "".join(s.title() for s in field.split("_")[1:])
                fixture[key] = ({"chatId": LARGE_ID} if reference == "Target" else
                                {"assetId": LARGE_ID, "assetVersion": MAX_U64} if reference == "AssetReference" else
                                REQUEST_ID if kind == "STRING" else LARGE_ID)
            self.assertEqual(fixture, self.round_trip(fixture, name))
        for name in ("TargetChange", "MessageChanged"):
            field = self.descriptor(name)["field"][-1]
            self.assertEqual(("representation_revision", 7, "TYPE_UINT64", True),
                             (field["name"], field["number"], field["type"], field["proto3Optional"]))
        methods = self.declarations["service"]["tinkle.v1.UpdatesService"][1]["method"]
        self.assertEqual(["ObserveConnectivity"], [m["name"] for m in methods])

    def test_policy_and_import_boundaries(self):
        """Pin lifecycle safety and one thumbnail policy, without claiming runtime proof."""
        media = (files.REPO_ROOT / files.MEDIA_FILE).read_text()
        self.assertNotIn('import "tinkle/v1/files.proto"', media)
        text = " ".join(re.sub(r"//|[*`]", "", media).split())
        for phrase in ("every thumbnail is optional", "exact original request bytes", "current authorization",
                       "no recipient-visible", "all-or-nothing", "commit atomically", "captured draft pair",
                       "30 days", "indefinitely", "reference_withheld", "absence is unknown",
                       "never resurrect", "never a public field", "PROCESSING", "never audio/voice",
                       "no video output", "exact per-output membership", "never all children"):
            self.assertIn(phrase, text)
        for path in (files.REPO_ROOT / "tinkle/v1").glob("*.proto"):
            self.assertNotRegex(path.read_text(), r"publication version|publication v2|\bV2\b")
        files_text = (files.REPO_ROOT / files.FILES_FILE).read_text()
        self.assertIn("64, 128, 256 or 512 KiB", files_text)
        self.assertIn("65536, 131072, 262144 or 524288", files_text)
        self.assertIn("uniformly for all media types", files_text)
        self.assertIn("Zero-byte uploads", files_text)
        self.assertIn("rpc CompleteUpload", files_text)


if __name__ == "__main__":
    unittest.main()
