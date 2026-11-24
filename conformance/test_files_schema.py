"""FilesService and media contract checks; no generated SDKs.

Requires Buf only. The tests pin the public surface of files.proto and
media.proto (service methods, message shapes, enums), the additive changes
to Photo/Document/UserPhoto/StickerView and the send requests, and the
*Source union conventions. Codec round trips exercise binary/JSON encoding
for large int64 identifiers, byte payloads, ranges, snapshot status,
terminal BeginUpload outcomes, zero-byte files, download limits, and
boundary shapes; malformed input must be rejected. These are codec and
descriptor checks only: they prove nothing about runtime semantics —
durable part commits, authorization, terminal-state races, snapshot
isolation, or garbage collection live in the server implementations.
"""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES_FILE = "tinkle/v1/files.proto"
MEDIA_FILE = "tinkle/v1/media.proto"
MESSAGES_FILE = "tinkle/v1/messages.proto"
MESSAGE_TYPES_FILE = "tinkle/v1/message_types.proto"

# base64("x" * 32) — a syntactically valid 32-byte digest for fixtures.
DIGEST_32 = "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg="


def run_buf(*arguments, input_bytes=None, check=True):
    """Run Buf with a deadline and binary-safe input/output."""
    result = subprocess.run(
        ["buf", *arguments], cwd=REPO_ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def reset_descriptor_numbers(descriptor):
    """Normalize only the authorized tag/reservation reset in an old descriptor.

    Names, types, oneof membership, presence, options and methods stay intact.
    Nested/map messages and enum reservations receive the same reset.
    """
    result = copy.deepcopy(descriptor)

    def reset(value):
        """Walk descriptor dictionaries, not source text or generated bindings."""
        if isinstance(value, dict):
            value.pop("reservedRange", None)
            value.pop("reservedName", None)
            for number, field in enumerate(value.get("field", []), 1):
                field["number"] = number
            for child in value.values():
                reset(child)
        elif isinstance(value, list):
            for child in value:
                reset(child)

    reset(result)
    return result


class BufSchemaTestCase(unittest.TestCase):
    """Shared descriptor and real-codec harness, with no test scenarios."""

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

    def convert(self, payload, message_type, source="json", target="binpb", check=True, *, image_path=None):
        encoded_payload = (
            payload if source == "binpb" else json.dumps(payload).encode()
        )
        return run_buf(
            "convert", f"{image_path or self.image_path}#format=json",
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


class FilesSchemaTests(BufSchemaTestCase):
    """Pin the files/media surface, additive preservation, and codec behavior."""

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
            "UploadPartRequest", "UploadPartResponse", "PartIndexRange",
            "GetUploadStatusRequest", "GetUploadStatusResponse",
            "CompleteUploadRequest", "CompleteUploadResponse",
            "IncompleteUploadError",
            "AbortUploadRequest", "AbortUploadResponse",
            "FileInfo", "GetFileInfoRequest", "GetFileInfoResponse",
            "DownloadPartRequest", "DownloadPartResponse",
            "FileAccessContext", "MessageFileReference", "ProfilePhotoReference",
            "StickerAssetReference", "ChatPhotoReference",
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
            ("processing_intent", 6, "ENUM", "MediaProcessingIntent", False, True),
        ], FILES_FILE)
        self.assert_fields("BeginUploadResponse", [
            ("upload_id", 1, "STRING", "", False, False),
            # Configuration fields are explicit presence: they apply only
            # to ACTIVE sessions and are omitted for terminal outcomes.
            ("part_size_bytes", 2, "INT64", "", False, True),
            ("max_parallel_parts", 3, "INT32", "", False, True),
            ("expires_at", 4, "MESSAGE", ".google.protobuf.Timestamp",
             False, False),
            ("status", 5, "ENUM", "UploadStatus", False, False),
            ("file", 6, "MESSAGE", "FileInfo", False, True),
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
        self.assert_fields("PartIndexRange", [
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
            ("received_ranges", 2, "MESSAGE", "PartIndexRange", True, False),
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
            ("missing_ranges", 1, "MESSAGE", "PartIndexRange", True, False),
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
            ("created_at", 6, "MESSAGE", ".google.protobuf.Timestamp",
             False, False),
        ], FILES_FILE)
        self.assert_fields("GetFileInfoRequest", [
            ("file_id", 1, "INT64", "", False, False),
            ("file_access_context", 2, "MESSAGE", "FileAccessContext", False, False),
        ], FILES_FILE)
        self.assert_fields("GetFileInfoResponse", [
            ("file", 1, "MESSAGE", "FileInfo", False, False),
            # Transport/response information, not a FileInfo fact; the
            # type matches DownloadPartRequest.limit so an advertised
            # bound is always requestable.
            ("max_download_part_bytes", 2, "INT32", "", False, True),
        ], FILES_FILE)
        self.assert_fields("DownloadPartRequest", [
            ("file_id", 1, "INT64", "", False, False),
            ("offset", 2, "INT64", "", False, False),
            ("limit", 3, "INT32", "", False, False),
            ("file_access_context", 4, "MESSAGE", "FileAccessContext", False, False),
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
            "StickerMetadata", "MediaAttribute",
            "Thumbnail", "ThumbnailSource",
            "MediaValidation",
            "AssetReference", "InlinePreview",
        }, names)

    def test_media_enums(self):
        self.assert_enum_values("StickerFormat", [
            "STICKER_FORMAT_UNSPECIFIED",
            "STICKER_FORMAT_WEBP",
            "STICKER_FORMAT_TGS",
            "STICKER_FORMAT_WEBM",
            "STICKER_FORMAT_PNG",
        ], MEDIA_FILE)

    def test_metadata_shapes(self):
        self.assert_fields("ImageMetadata", [
            ("width", 1, "UINT32", "", False, False),
            ("height", 2, "UINT32", "", False, False),
            ("animated", 3, "BOOL", "", False, False),
            ("format", 4, "ENUM", "ImageFormat", False, False),
            ("validation", 5, "MESSAGE", "MediaValidation", False, False),
        ], MEDIA_FILE)
        self.assert_fields("VideoMetadata", [
            ("width", 1, "UINT32", "", False, False),
            ("height", 2, "UINT32", "", False, False),
            ("duration_ms", 3, "UINT64", "", False, False),
            ("codec", 4, "STRING", "", False, True),
            ("supports_streaming", 5, "BOOL", "", False, False),
            ("round_video", 6, "BOOL", "", False, False),
            ("validation", 7, "MESSAGE", "MediaValidation", False, False),
        ], MEDIA_FILE)
        self.assert_fields("AudioMetadata", [
            ("duration_ms", 1, "UINT64", "", False, False),
            ("title", 2, "STRING", "", False, True),
            ("performer", 3, "STRING", "", False, True),
            ("voice_message", 4, "BOOL", "", False, False),
            ("waveform", 5, "BYTES", "", False, True),
            ("validation", 6, "MESSAGE", "MediaValidation", False, False),
        ], MEDIA_FILE)
        self.assert_fields("StickerMetadata", [
            ("emoji", 1, "STRING", "", False, False),
            ("width", 2, "UINT32", "", False, False),
            ("height", 3, "UINT32", "", False, False),
            ("format", 4, "ENUM", "StickerFormat", False, False),
            ("animated", 5, "BOOL", "", False, False),
            ("duration_ms", 6, "UINT64", "", False, True),
            ("frame_count", 7, "UINT32", "", False, True),
            ("validation", 8, "MESSAGE", "MediaValidation", False, False),
        ], MEDIA_FILE)

    def test_attribute_and_thumbnail_shapes(self):
        """Keep typed purpose attributes and the singular thumbnail value shapes."""
        self.assert_fields("MediaAttribute", [
            ("image", 1, "MESSAGE", "ImageMetadata", False, False),
            ("video", 2, "MESSAGE", "VideoMetadata", False, False),
            ("audio", 3, "MESSAGE", "AudioMetadata", False, False),
            ("sticker", 4, "MESSAGE", "StickerMetadata", False, False),
        ], MEDIA_FILE)
        self.assert_oneof("MediaAttribute", "kind",
                          ["image", "video", "audio", "sticker"], MEDIA_FILE)
        self.assert_fields("Thumbnail", [
            ("file_id", 1, "INT64", "", False, False),
            ("width", 2, "UINT32", "", False, False),
            ("height", 3, "UINT32", "", False, False),
        ], MEDIA_FILE)
        self.assert_fields("ThumbnailSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("width", 2, "UINT32", "", False, False),
            ("height", 3, "UINT32", "", False, False),
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
        """Pin file-backed source fields after retiring thumbnail collections."""
        self.assert_fields("PhotoSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "ImageMetadata", False, True),
            ("inline_preview", 3, "MESSAGE", "InlinePreview", False, False),
            ("thumbnail", 4, "MESSAGE", "ThumbnailSource", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("DocumentSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("attributes", 2, "MESSAGE", "MediaAttribute", True, False),
            ("inline_preview", 3, "MESSAGE", "InlinePreview", False, False),
            ("thumbnail", 4, "MESSAGE", "ThumbnailSource", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("VideoSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "VideoMetadata", False, True),
            ("inline_preview", 3, "MESSAGE", "InlinePreview", False, False),
            ("thumbnail", 4, "MESSAGE", "ThumbnailSource", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("AudioSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "AudioMetadata", False, True),
            ("inline_preview", 3, "MESSAGE", "InlinePreview", False, False),
            ("thumbnail", 4, "MESSAGE", "ThumbnailSource", False, False),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("VoiceSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("duration_ms", 2, "UINT64", "", False, False),
            ("waveform", 3, "BYTES", "", False, True),
        ], "tinkle/v1/messages.proto")
        self.assert_fields("StickerSource", [
            ("file_id", 1, "INT64", "", False, False),
            ("metadata", 2, "MESSAGE", "StickerMetadata", False, True),
            ("asset_id", 3, "INT64", "", False, True),
            ("asset_version", 4, "UINT64", "", False, True),
            ("inline_preview", 5, "MESSAGE", "InlinePreview", False, False),
            ("thumbnail", 6, "MESSAGE", "ThumbnailSource", False, False),
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

    def test_media_attachment_fields(self):
        """Preserve main/preview/revision shapes and pin compact thumbnail slots."""
        self.assert_fields("Photo", [
            ("id", 1, "INT64", "", False, False),
            ("access_hash", 2, "INT64", "", False, False),
            ("width", 3, "INT32", "", False, False),
            ("height", 4, "INT32", "", False, False),
            ("file_id", 5, "INT64", "", False, False),
            ("metadata", 6, "MESSAGE", "ImageMetadata", False, True),
            ("inline_preview", 7, "MESSAGE", "InlinePreview", False, False),
            ("representation_revision", 8, "UINT64", "", False, True),
            ("thumbnail", 9, "MESSAGE", "Thumbnail", False, False),
        ], MESSAGE_TYPES_FILE)
        self.assert_fields("Document", [
            ("id", 1, "INT64", "", False, False),
            ("access_hash", 2, "INT64", "", False, False),
            ("mime_type", 3, "STRING", "", False, False),
            ("size", 4, "INT64", "", False, False),
            ("file_name", 5, "STRING", "", False, False),
            ("file_id", 6, "INT64", "", False, False),
            ("attributes", 7, "MESSAGE", "MediaAttribute", True, False),
            ("inline_preview", 8, "MESSAGE", "InlinePreview", False, False),
            ("representation_revision", 9, "UINT64", "", False, True),
            ("thumbnail", 10, "MESSAGE", "Thumbnail", False, False),
        ], MESSAGE_TYPES_FILE)

    def test_user_photo_and_sticker_fields(self):
        """Expose exactly one thumbnail, never a duplicate sticker thumbnail ID."""
        self.assert_fields("UserPhoto", [
            ("file_id", 1, "INT64", "", False, False),
            ("photo_id", 2, "INT64", "", False, False),
            ("inline_preview", 3, "MESSAGE", "InlinePreview", False, False),
            ("representation_revision", 4, "UINT64", "", False, True),
            ("thumbnail", 5, "MESSAGE", "Thumbnail", False, False),
        ], "tinkle/v1/common.proto")
        self.assert_fields("StickerView", [
            ("id", 1, "INT64", "", False, False),
            ("file_id", 2, "INT64", "", False, False),
            ("is_premium", 3, "BOOL", "", False, False),
            ("metadata", 4, "MESSAGE", "StickerMetadata", False, True),
            ("kind", 5, "ENUM", "StickerKind", False, False),
            ("owner_id", 6, "INT64", "", False, False),
            ("fallback_text", 7, "STRING", "", False, False),
            ("asset_version", 8, "UINT64", "", False, False),
            ("inline_preview", 9, "MESSAGE", "InlinePreview", False, False),
            ("representation_revision", 10, "UINT64", "", False, True),
            ("thumbnail", 11, "MESSAGE", "Thumbnail", False, False),
        ], "tinkle/v1/stickers.proto")

    def test_send_requests_use_source_types(self):
        expected_type = {
            "SendMediaRequest": ("media", "MediaSource"),
            "SendAlbumRequest": ("items", "AlbumItem"),
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
        # Scalars and typed sources remain mutually exclusive. Tags follow
        # declaration order through the oneof and then the caption fields.
        self.assert_fields("SendPhotoRequest", [
            ("chat_id", 1, "INT64", "", False, False),
            ("photo", 2, "INT64", "", False, False),
            ("photo_source", 3, "MESSAGE", "PhotoSource", False, False),
            ("caption", 4, "STRING", "", False, True),
            ("parse_mode", 5, "STRING", "", False, True),
            ("reply_to_message_id", 6, "INT64", "", False, True),
            ("reply_markup", 7, "MESSAGE", "InlineKeyboardMarkup",
             False, True),
            ("disable_notification", 8, "BOOL", "", False, True),
        ], "tinkle/v1/bot_api.proto")
        self.assert_oneof("SendPhotoRequest", "photo_form",
                          ["photo", "photo_source"], "tinkle/v1/bot_api.proto")
        descriptor = self.descriptor("EditMessageMediaRequest")
        types = {f["name"]: f.get("typeName", "") for f in descriptor["field"]}
        self.assertEqual(".tinkle.v1.BotMediaSource", types["media"])
        self.assertEqual(".tinkle.v1.MediaSource", types["source"])
        self.assert_oneof("EditMessageMediaRequest", "media_form",
                          ["media", "source"], "tinkle/v1/bot_api.proto")

    def test_source_union_has_no_legacy_input_members(self):
        # The union carries content sources, not result objects.
        # Lookups use the fully qualified keys of the declaration index.
        for name in ("InputPhoto", "InputDocument", "MediaInput", "InputMedia"):
            self.assertNotIn("tinkle.v1." + name, self.declarations["message"],
                             name)

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
            "status": "UPLOAD_STATUS_ACTIVE",
        }
        self.assertEqual(fixture, self.round_trip(fixture, "BeginUploadResponse"))

    def test_begin_upload_terminal_outcomes_round_trip(self):
        # A completed retained outcome carries the committed FileInfo and
        # omits the active-session configuration entirely.
        completed = {
            "uploadId": "up-123",
            "status": "UPLOAD_STATUS_COMPLETED",
            "file": {
                "fileId": "9007199254740993",
                "sha256": DIGEST_32,
                "createdAt": "2026-10-25T12:00:00Z",
            },
        }
        decoded = self.round_trip(completed, "BeginUploadResponse")
        self.assertEqual("UPLOAD_STATUS_COMPLETED", decoded["status"])
        self.assertIn("file", decoded)
        for absent in ("partSizeBytes", "maxParallelParts", "expiresAt"):
            self.assertNotIn(absent, decoded)
        # Aborted and expired retained outcomes carry neither configuration
        # nor file; the client must start over with a fresh key.
        for status in ("UPLOAD_STATUS_ABORTED", "UPLOAD_STATUS_EXPIRED"):
            fixture = {"uploadId": "up-123", "status": status}
            decoded = self.round_trip(fixture, "BeginUploadResponse")
            self.assertEqual(status, decoded["status"])
            self.assertNotIn("file", decoded)
            for absent in ("partSizeBytes", "maxParallelParts", "expiresAt"):
                self.assertNotIn(absent, decoded)

    def test_begin_upload_request_optional_presence_round_trip(self):
        # Optional fields keep explicit presence: an explicitly empty value
        # serializes as present, distinct from an omitted field.
        explicit_empty = {
            "idempotencyKey": "k",
            "sizeBytes": "10",
            "fileName": "",
        }
        decoded = self.round_trip(explicit_empty, "BeginUploadRequest")
        self.assertEqual("", decoded["fileName"])
        self.assertNotIn("mimeType", decoded)
        self.assertNotIn("sha256", decoded)
        present = {
            "idempotencyKey": "k",
            "sizeBytes": "10",
            "sha256": DIGEST_32,
        }
        decoded = self.round_trip(present, "BeginUploadRequest")
        self.assertEqual(DIGEST_32, decoded["sha256"])
        self.assertNotIn("fileName", decoded)

    def test_upload_part_round_trip(self):
        fixture = {"partIndex": "7", "alreadyPresent": True}
        self.assertEqual(fixture, self.round_trip(fixture, "UploadPartResponse"))

    def test_allowed_part_sizes_and_final_short_part_shapes(self):
        """Encode every allowed negotiation and a final short part; no runtime validation."""
        for size in (65536, 131072, 262144, 524288):
            begin = {"uploadId": "up-123", "status": "UPLOAD_STATUS_ACTIVE",
                     "partSizeBytes": str(size), "maxParallelParts": 1}
            self.assertEqual(begin, self.round_trip(begin, "BeginUploadResponse"))
            status = {"status": "UPLOAD_STATUS_ACTIVE", "partSizeBytes": str(size),
                      "sizeBytes": str(size + 1), "receivedRanges": [{"endIndex": "1"}]}
            self.assertEqual(status, self.round_trip(status, "GetUploadStatusResponse"))
            final = {"uploadId": "up-123", "partIndex": "1", "data": "eA=="}
            self.assertEqual(final, self.round_trip(final, "UploadPartRequest"))

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
                "createdAt": "2026-10-25T12:00:00Z",
            },
        }
        decoded = self.round_trip(fixture, "GetUploadStatusResponse")
        self.assertEqual("UPLOAD_STATUS_COMPLETED", decoded["status"])
        self.assertEqual("9007199254740993", decoded["file"]["fileId"])
        self.assertNotIn("partSizeBytes", decoded)
        self.assertNotIn("expiresAt", decoded)

    def test_status_request_pagination_round_trip(self):
        fixture = {
            "uploadId": "up-123",
            "pageToken": "snap-7-page-2",
            "pageSize": 50,
        }
        self.assertEqual(fixture,
                         self.round_trip(fixture, "GetUploadStatusRequest"))
        first_page = {"uploadId": "up-123"}
        decoded = self.round_trip(first_page, "GetUploadStatusRequest")
        self.assertNotIn("pageToken", decoded)
        self.assertNotIn("pageSize", decoded)

    def test_zero_byte_file_round_trip(self):
        # A zero-byte completed file: size_bytes zero serializes as absent
        # under the implicit-presence convention, and the digest is the
        # server-computed SHA-256 of the empty byte sequence.
        empty_sha256 = "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
        fixture = {
            "fileId": "9007199254740993",
            "sha256": empty_sha256,
            "createdAt": "2026-10-25T12:00:00Z",
        }
        decoded = self.round_trip(fixture, "FileInfo")
        self.assertEqual(empty_sha256, decoded["sha256"])
        self.assertNotIn("sizeBytes", decoded)
        self.assertNotIn("encrypted", decoded)

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

    def test_download_boundary_examples_round_trip(self):
        # Progress guarantee shape: a nonempty remainder with a positive
        # limit returns data and echoes the offset; eof marks the exact
        # end of the returned range, not the requested limit. False serializes
        # as absent under the implicit-presence convention.
        progress = {"data": "AAEC", "offset": "1024", "eof": False}
        decoded = self.round_trip(progress, "DownloadPartResponse")
        self.assertEqual("1024", decoded["offset"])
        self.assertIs(False, decoded.get("eof", False))
        # End-of-file boundary: offset == size returns empty data with
        # eof true; offset zero serializes as absent.
        final = {"offset": "4096", "eof": True}
        decoded = self.round_trip(final, "DownloadPartResponse")
        self.assertNotIn("data", decoded)
        self.assertTrue(decoded["eof"])

    def test_get_file_info_response_download_limit_round_trip(self):
        # The download limit is response/transport information carried
        # beside the file, never inside FileInfo. Its type matches the
        # request limit, so an advertised bound is always requestable.
        fixture = {
            "file": {
                "fileId": "9007199254740993",
                "sizeBytes": "1048576",
                "sha256": DIGEST_32,
                "createdAt": "2026-10-25T12:00:00Z",
            },
            "maxDownloadPartBytes": 262144,
        }
        decoded = self.round_trip(fixture, "GetFileInfoResponse")
        self.assertEqual(262144, decoded["maxDownloadPartBytes"])
        self.assertNotIn("maxDownloadPartBytes",
                         decoded["file"],
                         "download limit must not leak into FileInfo")
        # The limit is explicit presence: absent means "not advertised
        # here", distinct from a zero-valued bound.
        decoded = self.round_trip({"file": fixture["file"]},
                                  "GetFileInfoResponse")
        self.assertNotIn("maxDownloadPartBytes", decoded)

    def test_abort_round_trip(self):
        self.assertEqual({"aborted": True},
                         self.round_trip({"aborted": True}, "AbortUploadResponse"))
        self.assertEqual({}, self.round_trip({}, "AbortUploadResponse"))

    def test_source_round_trips(self):
        """Preserve singular thumbnail IDs/dimensions through the real codec."""
        photo = {
            "fileId": "9007199254740993",
            "metadata": {"width": 1920, "height": 1080},
            "thumbnail": {
                "fileId": "7",
                "width": 160,
                "height": 90,
            },
        }
        decoded = self.round_trip(photo, "PhotoSource")
        self.assertEqual("9007199254740993", decoded["fileId"])
        self.assertEqual({"width": 1920, "height": 1080}, decoded["metadata"])
        self.assertEqual({
            "fileId": "7",
            "width": 160,
            "height": 90,
        }, decoded["thumbnail"])

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
            ("MediaAttribute", {"image": {"width": 1},
                                "sticker": {"emoji": "x"}}),
            ("ChatPhotoSource", {"fileId": "5", "empty": False}),
            ("SendPhotoRequest", {"chatId": 1, "photo": "5",
                                  "photoSource": {"fileId": "6"}}),
            ("EditMessageMediaRequest", {"chatId": 1, "messageId": 2,
                                         "media": {"type": "photo",
                                                   "media": "5"},
                                         "source": {"photo": {"fileId": "6"}}}),
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

    def test_no_provider_specific_leakage(self):
        # The public contract stays provider-neutral: object-store keys,
        # bucket names, regions, provider upload IDs, ETags, and
        # storage-internal cursors never appear as fields or literals in
        # the file-transfer or media sources.
        forbidden = ("s3", "gcs", "aws", "azure", "gcp", "bucket", "etag",
                     "presign", "multipart", "region=")
        for path in (REPO_ROOT / FILES_FILE, REPO_ROOT / MEDIA_FILE):
            text = path.read_text().lower()
            for token in forbidden:
                self.assertNotIn(token, text,
                                 f"{path.name} leaks {token!r}")

    def test_sequential_tags_and_json_names(self):
        for name, (file_name, message) in sorted(
                self.declarations["message"].items()):
            if file_name not in (FILES_FILE, MEDIA_FILE):
                continue
            fields = message.get("field", [])
            tags = [f["number"] for f in fields]
            self.assertEqual(list(range(1, len(fields) + 1)), tags, name)
            self.assertFalse(message.get("reservedRange"), name)
            self.assertFalse(message.get("reservedName"), name)
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
