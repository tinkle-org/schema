"""FilesService and media contract checks; no generated SDKs.

Requires Buf only. The tests pin the public surface of files.proto and
media.proto (service methods, message shapes, enums), the additive changes
to Photo/Document/UserPhoto/StickerView and the send requests, and the
*Source union conventions. Codec round trips exercise binary/JSON encoding
for large int64 identifiers, byte payloads, ranges, and snapshot status;
malformed input must be rejected. Runtime upload semantics (resumability,
authorization, expiry, garbage collection) are not observable here.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES_FILE = "tinkle/v1/files.proto"
MEDIA_FILE = "tinkle/v1/media.proto"

# base64("x" * 32) — a syntactically valid 32-byte digest for fixtures.
DIGEST_32 = "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4"


def run_buf(*arguments, input_bytes=None, check=True):
    """Run Buf with a deadline and binary-safe input/output."""
    result = subprocess.run(
        ["buf", *arguments], cwd=REPO_ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


class FilesSchemaTests(unittest.TestCase):
    """Pin the files/media surface, additive preservation, and codec behavior."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="tinkle-files-conformance-")
        cls.addClassCleanup(temporary.cleanup)
        result = run_buf(
            "build", ".", "--exclude-source-info",
            "--as-file-descriptor-set", "-o", "-#format=json",
        )
        image = json.loads(result.stdout)
        cls.declarations = {"message": {}, "enum": {}, "service": {}}
        for file in image["file"]:
            if not file["name"].startswith("tinkle/"):
                continue
            prefix = file["package"] + "."
            for message in file.get("messageType", []):
                cls.declarations["message"][prefix + message["name"]] = (
                    file["name"], message,
                )
            for kind, key in (("enum", "enumType"), ("service", "service")):
                for item in file.get(key, []):
                    cls.declarations[kind][prefix + item["name"]] = (
                        file["name"], item,
                    )
        cls.image_path = Path(temporary.name) / "image.json"
        cls.image_path.write_bytes(result.stdout)

    def descriptor(self, name, filename=None):
        actual_filename, descriptor = self.declarations["message"]["tinkle.v1." + name]
        if filename is not None:
            self.assertEqual(filename, actual_filename, name)
        return descriptor

    def convert(self, payload, message_type, source="json", target="binpb", check=True):
        encoded_payload = (
            payload if source == "binpb" else json.dumps(payload).encode()
        )
        return run_buf(
            "convert", f"{self.image_path}#format=json",
            f"--type=tinkle.v1.{message_type}",
            f"--from=-#format={source}", f"--to=-#format={target}",
            input_bytes=encoded_payload, check=check,
        )

    def encode(self, fixture, message_type):
        return self.convert(fixture, message_type).stdout

    def decode(self, encoded, message_type):
        return json.loads(
            self.convert(encoded, message_type, "binpb", "json").stdout
        )

    def round_trip(self, fixture, message_type):
        encoded = self.encode(fixture, message_type)
        if not encoded:
            # All-defaults messages encode to zero bytes, and newer Buf
            # versions reject zero-length binary payloads on stdin. An
            # empty wire form decodes to an empty message by definition,
            # so the empty case asserts the encoding alone.
            return {}
        decoded = self.decode(encoded, message_type)
        self.assertEqual(
            encoded,
            self.convert(decoded, message_type).stdout,
            message_type,
        )
        return decoded

    def assert_fields(self, name, expected, filename=None):
        """Compare all field names, tags, types, references, repetition, presence."""
        descriptor = self.descriptor(name, filename)
        actual = [
            (f["name"], f["number"], f["type"].removeprefix("TYPE_"),
             f.get("typeName", "").removeprefix(".tinkle.v1."),
             f["label"] == "LABEL_REPEATED", f.get("proto3Optional", False))
            for f in descriptor.get("field", [])
        ]
        self.assertEqual(expected, actual, name)

    def assert_oneof(self, name, oneof_name, member_names, filename=None):
        """Assert one declared oneof's member list, in declaration order."""
        descriptor = self.descriptor(name, filename)
        declared = [o["name"] for o in descriptor.get("oneofDecl", [])]
        members = {}
        for field in descriptor.get("field", []):
            if "oneofIndex" in field:
                members.setdefault(declared[field["oneofIndex"]], []).append(
                    field["name"]
                )
        self.assertEqual(member_names, members.get(oneof_name), name)

    def assert_enum_values(self, name, expected, filename=None):
        self.assertEqual(filename, self.declarations["enum"]["tinkle.v1." + name][0])
        values = self.declarations["enum"]["tinkle.v1." + name][1]["value"]
        self.assertEqual(expected, [v["name"] for v in values], name)

    # ------------------------------------------------------------------
    # FilesService surface
    # ------------------------------------------------------------------

    def test_files_service_methods(self):
        service = self.declarations["service"]["tinkle.v1.FilesService"]
        self.assertEqual(FILES_FILE, service[0])
        self.assertEqual("FilesService", service[1]["name"])
        self.assertEqual([
            "BeginUpload", "UploadPart", "GetUploadStatus", "CompleteUpload",
            "AbortUpload", "GetFileInfo", "DownloadPart",
        ], [m["name"] for m in service[1]["method"]])
        for method in service[1]["method"]:
            self.assertEqual(".tinkle.v1." + method["name"] + "Request",
                             method["inputType"])
            self.assertEqual(".tinkle.v1." + method["name"] + "Response",
                             method["outputType"])
            self.assertFalse(method.get("clientStreaming", False))
            self.assertFalse(method.get("serverStreaming", False))

    def test_files_message_inventory(self):
        names = {
            n.removeprefix("tinkle.v1.")
            for n, (f, _) in self.declarations["message"].items()
            if f == FILES_FILE
        }
        self.assertEqual({
            "BeginUploadRequest", "BeginUploadResponse",
            "UploadPartRequest", "UploadPartResponse", "UploadPartRange",
            "GetUploadStatusRequest", "GetUploadStatusResponse",
            "CompleteUploadRequest", "CompleteUploadResponse",
            "IncompleteUploadError",
            "AbortUploadRequest", "AbortUploadResponse",
            "FileInfo", "GetFileInfoRequest", "GetFileInfoResponse",
            "DownloadPartRequest", "DownloadPartResponse",
        }, names)

    def test_upload_status_enum(self):
        self.assert_enum_values("UploadStatus", [
            "UPLOAD_STATUS_UNSPECIFIED",
            "UPLOAD_STATUS_ACTIVE",
            "UPLOAD_STATUS_COMPLETED",
            "UPLOAD_STATUS_ABORTED",
            "UPLOAD_STATUS_EXPIRED",
        ], FILES_FILE)

    # ------------------------------------------------------------------
    # files.proto shapes
    # ------------------------------------------------------------------

    def test_session_shapes(self):
        self.assert_fields("BeginUploadRequest", [
            ("idempotency_key", 1, "STRING", "", False, False),
            ("size_bytes", 2, "INT64", "", False, False),
            ("file_name", 3, "STRING", "", False, True),
            ("mime_type", 4, "STRING", "", False, True),
            ("sha256", 5, "BYTES", "", False, True),
            ("encrypted", 6, "BOOL", "", False, False),
        ], FILES_FILE)
        self.assert_fields("BeginUploadResponse", [
            ("upload_id", 1, "STRING", "", False, False),
            ("part_size_bytes", 2, "INT64", "", False, False),
            ("max_parallel_parts", 3, "INT32", "", False, False),
            ("expires_at", 4, "MESSAGE", ".google.protobuf.Timestamp",
             False, False),
        ], FILES_FILE)

    def test_part_shapes(self):
        self.assert_fields("UploadPartRequest", [
            ("upload_id", 1, "STRING", "", False, False),
            ("part_index", 2, "INT64", "", False, False),
            ("data", 3, "BYTES", "", False, False),
            ("sha256", 4, "BYTES", "", False, True),
        ], FILES_FILE)
        self.assert_fields("UploadPartResponse", [
            ("part_index", 1, "INT64", "", False, False),
            ("already_present", 2, "BOOL", "", False, False),
        ], FILES_FILE)
        self.assert_fields("UploadPartRange", [
            ("start_index", 1, "INT64", "", False, False),
            ("end_index", 2, "INT64", "", False, False),
        ], FILES_FILE)

    def test_status_shapes(self):
        self.assert_fields("GetUploadStatusRequest", [
            ("upload_id", 1, "STRING", "", False, False),
            ("page_token", 2, "STRING", "", False, True),
            ("page_size", 3, "INT32", "", False, True),
        ], FILES_FILE)
        self.assert_fields("GetUploadStatusResponse", [
            ("status", 1, "ENUM", "UploadStatus", False, False),
            ("received_ranges", 2, "MESSAGE", "UploadPartRange", True, False),
            ("next_page_token", 3, "STRING", "", False, True),
            ("expires_at", 4, "MESSAGE", ".google.protobuf.Timestamp",
             False, True),
            ("part_size_bytes", 5, "INT64", "", False, True),
            ("size_bytes", 6, "INT64", "", False, False),
            ("file", 7, "MESSAGE", "FileInfo", False, True),
        ], FILES_FILE)

    def test_completion_shapes(self):
        self.assert_fields("CompleteUploadRequest", [
            ("upload_id", 1, "STRING", "", False, False),
            ("sha256", 2, "BYTES", "", False, True),
        ], FILES_FILE)
        self.assert_fields("CompleteUploadResponse", [
            ("file", 1, "MESSAGE", "FileInfo", False, False),
        ], FILES_FILE)
        self.assert_fields("IncompleteUploadError", [
            ("missing_ranges", 1, "MESSAGE", "UploadPartRange", True, False),
            ("truncated", 2, "BOOL", "", False, False),
        ], FILES_FILE)
        self.assert_fields("AbortUploadRequest", [
            ("upload_id", 1, "STRING", "", False, False),
        ], FILES_FILE)
        self.assert_fields("AbortUploadResponse", [
            ("aborted", 1, "BOOL", "", False, False),
        ], FILES_FILE)

    def test_file_and_download_shapes(self):
        self.assert_fields("FileInfo", [
            ("file_id", 1, "INT64", "", False, False),
            ("size_bytes", 2, "INT64", "", False, False),
            ("sha256", 3, "BYTES", "", False, False),
            ("mime_type", 4, "STRING", "", False, True),
            ("file_name", 5, "STRING", "", False, True),
            ("encrypted", 6, "BOOL", "", False, False),
            ("created_at", 7, "MESSAGE", ".google.protobuf.Timestamp",
             False, False),
        ], FILES_FILE)
        self.assert_fields("GetFileInfoRequest", [
            ("file_id", 1, "INT64", "", False, False),
        ], FILES_FILE)
        self.assert_fields("GetFileInfoResponse", [
            ("file", 1, "MESSAGE", "FileInfo", False, False),
        ], FILES_FILE)
        self.assert_fields("DownloadPartRequest", [
            ("file_id", 1, "INT64", "", False, False),
            ("offset", 2, "INT64", "", False, False),
            ("limit", 3, "INT32", "", False, False),
        ], FILES_FILE)
        self.assert_fields("DownloadPartResponse", [
            ("data", 1, "BYTES", "", False, False),
            ("offset", 2, "INT64", "", False, False),
            ("eof", 3, "BOOL", "", False, False),
        ], FILES_FILE)

    # ------------------------------------------------------------------
    # media.proto shapes
    # ------------------------------------------------------------------

    def test_media_message_inventory(self):
        names = {
            n.removeprefix("tinkle.v1.")
            for n, (f, _) in self.declarations["message"].items()
            if f == MEDIA_FILE
        }
        self.assertEqual({
            "ImageMetadata", "VideoMetadata", "AudioMetadata",
            "StickerMetadata", "MediaAttribute", "AnimatedAttribute",
            "MediaVariant", "MediaVariantSource",
        }, names)

    def test_media_enums(self):
        self.assert_enum_values("MediaVariantRole", [
            "MEDIA_VARIANT_ROLE_UNSPECIFIED",
            "MEDIA_VARIANT_ROLE_THUMBNAIL",
            "MEDIA_VARIANT_ROLE_PREVIEW",
            "MEDIA_VARIANT_ROLE_FULL",
        ], MEDIA_FILE)
        self.assert_enum_values("StickerFormat", [
            "STICKER_FORMAT_UNSPECIFIED",
            "STICKER_FORMAT_WEBP",
            "STICKER_FORMAT_TGS",
            "STICKER_FORMAT_WEBM",
        ], MEDIA_FILE)

    def test_metadata_shapes(self):
        self.assert_fields("ImageMetadata", [
            ("width", 1, "UINT32", "", False, False),
            ("height", 2, "UINT32", "", False, False),
            ("animated", 3, "BOOL", "", False, False),
        ], MEDIA_FILE)
        self.assert_fields("VideoMetadata", [
            ("width", 1, "UINT32", "", False, False),
            ("height", 2, "UINT32", "", False, False),
            ("duration_ms", 3, "UINT64", "", False, False),
            ("codec", 4, "STRING", "", False, True),
            ("supports_streaming", 5, "BOOL", "", False, False),
            ("round_video", 6, "BOOL", "", False, False),
        ], MEDIA_FILE)
        self.assert_fields("AudioMetadata", [
            ("duration_ms", 1, "UINT64", "", False, False),
            ("title", 2, "STRING", "", False, True),
            ("performer", 3, "STRING", "", False, True),
            ("voice_message", 4, "BOOL", "", False, False),
            ("waveform", 5, "BYTES", "", False, True),
        ], MEDIA_FILE)
        self.assert_fields("StickerMetadata", [
            ("emoji", 1, "STRING", "", False, False),
            ("width", 2, "UINT32", "", False, False),
            ("height", 3, "UINT32", "", False, False),
            ("animated", 4, "BOOL", "", False, False),
            ("format", 5, "ENUM", "StickerFormat", False, False),
        ], MEDIA_FILE)

    def test_attribute_and_variant_shapes(self):
        self.assert_fields("MediaAttribute", [
            ("image", 1, "MESSAGE", "ImageMetadata", False, False),
            ("video", 2, "MESSAGE", "VideoMetadata", False, False),
            ("audio", 3, "MESSAGE", "AudioMetadata", False, False),
            ("sticker", 4, "MESSAGE", "StickerMetadata", False, False),
            ("animated", 5, "MESSAGE", "AnimatedAttribute", False, False),
        ], MEDIA_FILE)
        self.assert_oneof("MediaAttribute", "kind",
                          ["image", "video", "audio", "sticker", "animated"],
                          MEDIA_FILE)
        self.assert_fields("AnimatedAttribute", [], MEDIA_FILE)
        self.assert_fields("MediaVariant", [
            ("role", 1, "ENUM", "MediaVariantRole", False, False),
            ("file_id", 2, "INT64", "", False, False),
            ("width", 3, "UINT32", "", False, True),
            ("height", 4, "UINT32", "", False, True),
        ], MEDIA_FILE)
        self.assert_fields("MediaVariantSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("role", 2, "ENUM", "MediaVariantRole", False, False),
            ("width", 3, "UINT32", "", False, True),
            ("height", 4, "UINT32", "", False, True),
        ], MEDIA_FILE)

    # ------------------------------------------------------------------
    # Source union and additive preservation
    # ------------------------------------------------------------------

    def test_media_source_union(self):
        self.assert_fields("MediaSource", [
            ("photo", 1, "MESSAGE", "PhotoSource", False, False),
            ("document", 2, "MESSAGE", "DocumentSource", False, False),
            ("geo", 3, "MESSAGE", "GeoPointSource", False, False),
            ("contact", 4, "MESSAGE", "ContactSource", False, False),
            ("poll", 5, "MESSAGE", "PollSource", False, False),
            ("video", 6, "MESSAGE", "VideoSource", False, False),
            ("audio", 7, "MESSAGE", "AudioSource", False, False),
            ("voice", 8, "MESSAGE", "VoiceSource", False, False),
            ("sticker", 9, "MESSAGE", "StickerSource", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_oneof("MediaSource", "media", [
            "photo", "document", "geo", "contact", "poll",
            "video", "audio", "voice", "sticker",
        ], "tinkle/v1/messages.proto")

    def test_source_shapes(self):
        self.assert_fields("PhotoSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "ImageMetadata", False, True),
            ("variants", 3, "MESSAGE", "MediaVariantSource", True, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("DocumentSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("attributes", 2, "MESSAGE", "MediaAttribute", True, False),
            ("variants", 3, "MESSAGE", "MediaVariantSource", True, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("VideoSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "VideoMetadata", False, True),
            ("variants", 3, "MESSAGE", "MediaVariantSource", True, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("AudioSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "AudioMetadata", False, True),
            ("variants", 3, "MESSAGE", "MediaVariantSource", True, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("VoiceSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("duration_ms", 2, "UINT64", "", False, False),
            ("waveform", 3, "BYTES", "", False, True),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("StickerSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "StickerMetadata", False, True),
            ("variants", 3, "MESSAGE", "MediaVariantSource", True, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("GeoPointSource", [
            ("lat", 1, "DOUBLE", "", False, False),
            ("long", 2, "DOUBLE", "", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("ContactSource", [
            ("phone_number", 1, "STRING", "", False, False),
            ("first_name", 2, "STRING", "", False, False),
            ("last_name", 3, "STRING", "", False, False),
            ("user_id", 4, "INT64", "", False, False),
        ], "tinkle/v1/messages.proto")

    def test_chat_photo_source_union(self):
        self.assert_fields("ChatPhotoSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("empty", 2, "BOOL", "", False, False),
            ("photo", 3, "MESSAGE", "PhotoSource", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_oneof("ChatPhotoSource", "input",
                          ["file_id", "empty", "photo"],
                          "tinkle/v1/messages.proto")

    def test_additive_media_attachment_fields(self):
        # Legacy wire fields (tags 1-4 / 1-5) are unchanged; new canonical
        # references, metadata, and variants extend the messages additively.
        self.assert_fields("Photo", [
            ("id", 1, "INT64", "", False, False),
            ("access_hash", 2, "INT64", "", False, False),
            ("width", 3, "INT32", "", False, False),
            ("height", 4, "INT32", "", False, False),
            ("file_id", 5, "INT64", "", False, False),
            ("metadata", 6, "MESSAGE", "ImageMetadata", False, True),
            ("variants", 7, "MESSAGE", "MediaVariant", True, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("Document", [
            ("id", 1, "INT64", "", False, False),
            ("access_hash", 2, "INT64", "", False, False),
            ("mime_type", 3, "STRING", "", False, False),
            ("size", 4, "INT64", "", False, False),
            ("file_name", 5, "STRING", "", False, False),
            ("file_id", 6, "INT64", "", False, False),
            ("attributes", 7, "MESSAGE", "MediaAttribute", True, False),
            ("variants", 8, "MESSAGE", "MediaVariant", True, False),
        ], "tinkle/v1/messages.proto")

    def test_additive_user_photo_and_sticker_fields(self):
        self.assert_fields("UserPhoto", [
            ("file_id", 1, "INT64", "", False, False),
            ("variants", 2, "MESSAGE", "MediaVariant", True, False),
        ], "tinkle/v1/common.proto")
        self.assert_fields("StickerView", [
            ("id", 1, "INT64", "", False, False),
            ("file_id", 2, "INT64", "", False, False),
            ("thumb_file_id", 3, "INT64", "", False, False),
            ("is_premium", 4, "BOOL", "", False, False),
            ("metadata", 5, "MESSAGE", "StickerMetadata", False, True),
        ], "tinkle/v1/stickers.proto")

    def test_send_requests_use_source_types(self):
        expected_type = {
            "SendMediaRequest": ("media", "MediaSource"),
            "SendMultiMediaRequest": ("multi_media", "SingleMediaSource"),
            "EditMessageRequest": ("media", "MediaSource"),
            "EditChatPhotoRequest": ("photo", "ChatPhotoSource"),
            "EditPhotoRequest": ("photo", "ChatPhotoSource"),
            "SendPhotoRequest": ("photo_source", "PhotoSource"),
            "SendDocumentRequest": ("document_source", "DocumentSource"),
            "SendVideoRequest": ("video_source", "VideoSource"),
            "SendAudioRequest": ("audio_source", "AudioSource"),
            "SendVoiceRequest": ("voice_source", "VoiceSource"),
            "SendStickerRequest": ("sticker_source", "StickerSource"),
            "EditMessageMediaRequest": ("source", "MediaSource"),
        }
        for message_name, (field_name, type_name) in expected_type.items():
            descriptor = self.descriptor(message_name)
            field = next(f for f in descriptor["field"] if f["name"] == field_name)
            self.assertEqual(".tinkle.v1." + type_name,
                             field.get("typeName", ""), message_name)

    def test_bot_media_source_and_alternatives(self):
        self.assert_fields("BotMediaSource", [
            ("type", 1, "STRING", "", False, False),
            ("media", 2, "INT64", "", False, False),
            ("caption", 3, "STRING", "", False, True),
            ("parse_mode", 4, "STRING", "", False, True),
        ], "tinkle/v1/bot_api.proto")
        # Legacy scalars stay untouched on their original tags.
        self.assert_fields("SendPhotoRequest", [
            ("chat_id", 1, "INT64", "", False, False),
            ("photo", 2, "INT64", "", False, False),
            ("caption", 3, "STRING", "", False, True),
            ("parse_mode", 4, "STRING", "", False, True),
            ("reply_to_message_id", 5, "INT64", "", False, True),
            ("reply_markup", 6, "MESSAGE", "InlineKeyboardMarkup",
             False, True),
            ("disable_notification", 7, "BOOL", "", False, True),
            ("photo_source", 8, "MESSAGE", "PhotoSource", False, True),
        ], "tinkle/v1/bot_api.proto")
        descriptor = self.descriptor("EditMessageMediaRequest")
        types = {f["name"]: f.get("typeName", "") for f in descriptor["field"]}
        self.assertEqual(".tinkle.v1.BotMediaSource", types["media"])
        self.assertEqual(".tinkle.v1.MediaSource", types["source"])

    def test_source_union_has_no_legacy_input_members(self):
        # The union only carries *Source types; no Telegram-style Input types.
        self.assertNotIn("InputPhoto", self.declarations["message"])
        self.assertNotIn("InputDocument", self.declarations["message"])
        self.assertNotIn("MediaInput", self.declarations["message"])
        self.assertNotIn("InputMedia", self.declarations["message"])

    # ------------------------------------------------------------------
    # Codec round trips
    # ------------------------------------------------------------------

    def test_begin_upload_response_round_trip(self):
        # Buf emits standard protojson JSON: camelCase json names.
        fixture = {
            "uploadId": "up-123",
            "partSizeBytes": "262144",
            "maxParallelParts": 4,
            "expiresAt": "2026-10-25T12:00:00Z",
        }
        self.assertEqual(fixture, self.round_trip(fixture, "BeginUploadResponse"))

    def test_upload_part_round_trip(self):
        fixture = {"partIndex": "7", "alreadyPresent": True}
        self.assertEqual(fixture, self.round_trip(fixture, "UploadPartResponse"))

    def test_status_active_snapshot_round_trip(self):
        fixture = {
            "status": "UPLOAD_STATUS_ACTIVE",
            "receivedRanges": [
                {"startIndex": "0", "endIndex": "2"},
                {"startIndex": "3", "endIndex": "5"},
            ],
            "partSizeBytes": "262144",
            "sizeBytes": "786432",
            "expiresAt": "2026-10-25T12:00:00Z",
        }
        decoded = self.round_trip(fixture, "GetUploadStatusResponse")
        # start_index zero serializes as absent (implicit presence).
        self.assertEqual(
            [{"endIndex": "2"}, {"startIndex": "3", "endIndex": "5"}],
            decoded["receivedRanges"],
        )
        self.assertEqual("UPLOAD_STATUS_ACTIVE", decoded["status"])
        self.assertNotIn("file", decoded)
        self.assertNotIn("nextPageToken", decoded)

    def test_status_completed_round_trip(self):
        fixture = {
            "status": "UPLOAD_STATUS_COMPLETED",
            "sizeBytes": "1048576",
            "file": {
                "fileId": "9007199254740993",
                "sizeBytes": "1048576",
                "sha256": DIGEST_32,
                "encrypted": True,
                "createdAt": "2026-10-25T12:00:00Z",
            },
        }
        decoded = self.round_trip(fixture, "GetUploadStatusResponse")
        self.assertEqual("UPLOAD_STATUS_COMPLETED", decoded["status"])
        self.assertEqual("9007199254740993", decoded["file"]["fileId"])
        self.assertTrue(decoded["file"]["encrypted"])
        self.assertNotIn("partSizeBytes", decoded)
        self.assertNotIn("expiresAt", decoded)

    def test_complete_and_incomplete_round_trips(self):
        file_fixture = {
            "file": {
                "fileId": "9007199254740993",
                "sizeBytes": "3",
                "sha256": DIGEST_32,
                "mimeType": "application/pdf",
                "fileName": "notes.pdf",
                "createdAt": "2026-10-25T12:00:00Z",
            }
        }
        self.assertEqual(file_fixture,
                         self.round_trip(file_fixture, "CompleteUploadResponse"))
        incomplete_fixture = {
            "missingRanges": [{"startIndex": "2", "endIndex": "4"}],
            "truncated": True,
        }
        self.assertEqual(incomplete_fixture,
                         self.round_trip(incomplete_fixture, "IncompleteUploadError"))

    def test_download_round_trips(self):
        empty = {"offset": "1048576", "eof": True}
        self.assertEqual(empty, self.round_trip(empty, "DownloadPartResponse"))
        data = {"data": "AAEC", "offset": "0", "eof": False}
        self.assertEqual({"data": "AAEC"},
                         self.round_trip(data, "DownloadPartResponse"))

    def test_abort_round_trip(self):
        self.assertEqual({"aborted": True},
                         self.round_trip({"aborted": True}, "AbortUploadResponse"))
        self.assertEqual({}, self.round_trip({}, "AbortUploadResponse"))

    def test_source_round_trips(self):
        photo = {
            "fileId": "9007199254740993",
            "metadata": {"width": 1920, "height": 1080},
            "variants": [{
                "fileId": "7",
                "role": "MEDIA_VARIANT_ROLE_THUMBNAIL",
                "width": 160,
                "height": 90,
            }],
        }
        decoded = self.round_trip(photo, "PhotoSource")
        self.assertEqual("9007199254740993", decoded["fileId"])
        self.assertEqual({"width": 1920, "height": 1080}, decoded["metadata"])
        self.assertEqual([{
            "fileId": "7",
            "role": "MEDIA_VARIANT_ROLE_THUMBNAIL",
            "width": 160,
            "height": 90,
        }], decoded["variants"])

        document = {
            "fileId": "5",
            "attributes": [
                {"video": {"width": 640, "height": 480,
                           "durationMs": "30000"}},
                {"sticker": {"emoji": "\U0001F431", "width": 512,
                             "height": 512,
                             "format": "STICKER_FORMAT_WEBM"}},
            ],
        }
        decoded = self.round_trip(document, "DocumentSource")
        self.assertEqual(["video"],
                         list(decoded["attributes"][0].keys()))
        self.assertEqual("STICKER_FORMAT_WEBM",
                         decoded["attributes"][1]["sticker"]["format"])

        voice = {"fileId": "9", "durationMs": "4300", "waveform": "AAECAwQ="}
        self.assertEqual(voice, self.round_trip(voice, "VoiceSource"))

    def test_large_ids_survive_json_round_trip(self):
        fixture = {"fileId": "9007199254740993", "sha256": DIGEST_32}
        decoded = self.round_trip(fixture, "GetFileInfoRequest")
        self.assertEqual("9007199254740993", decoded["fileId"])

    # ------------------------------------------------------------------
    # Rejection by codec
    # ------------------------------------------------------------------

    def test_conflicting_oneof_alternatives_are_rejected(self):
        for message_type, fixture in (
            ("MediaSource", {"photo": {"fileId": "1"},
                             "document": {"fileId": "2"}}),
            ("MediaSource", {"photo": {"fileId": "1"}, "voice": {}}),
            ("MediaAttribute", {"image": {"width": 1}, "animated": {}}),
            ("ChatPhotoSource", {"fileId": "5", "empty": False}),
        ):
            self.assertNotEqual(
                0, self.convert(fixture, message_type, check=False).returncode,
                message_type,
            )

    def test_wrong_field_types_are_rejected_by_codec(self):
        for message_type, fixture in (
            ("BeginUploadRequest", {"idempotency_key": 7, "sizeBytes": "100"}),
            ("BeginUploadRequest", {"sizeBytes": 1.5}),
            ("UploadPartRequest", {"uploadId": 5, "data": "AAEC"}),
            ("DownloadPartRequest", {"fileId": "5", "offset": "0",
                                     "limit": {"bytes": 32}}),
            ("GetUploadStatusResponse", {"status": "UPLOAD_STATUS_ACTIVE",
                                         "receivedRanges": "0-2"}),
        ):
            self.assertNotEqual(
                0, self.convert(fixture, message_type, check=False).returncode,
                message_type,
            )

    # ------------------------------------------------------------------
    # Encoding hygiene
    # ------------------------------------------------------------------

    def test_sequential_tags_and_json_names(self):
        for name, (file_name, message) in sorted(
                self.declarations["message"].items()):
            if file_name not in (FILES_FILE, MEDIA_FILE):
                continue
            fields = message.get("field", [])
            self.assertEqual(
                list(range(1, len(fields) + 1)),
                [f["number"] for f in fields], name,
            )
            self.assertFalse(message.get("reservedRange"), name)
            for field in fields:
                # Standard protojson canonical name (camelCase) is computed
                # for every field, keeping JSON round trips deterministic.
                self.assertIn("jsonName", field, name)
                self.assertEqual(
                    "".join(part.title() if i else part for i, part in
                            enumerate(field["name"].split("_"))),
                    field["jsonName"], name,
                )


if __name__ == "__main__":
    unittest.main()
