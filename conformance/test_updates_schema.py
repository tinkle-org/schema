"""Connectivity descriptor and real Buf codec checks; no generated SDKs.

Requires Buf and a local main branch. Descriptor comparisons and protobuf round
trips do not test runtime authorization or observation delivery. The public
controller adapters are not implemented by this schema repository; durable
update replay and watch retired from this contract and remain
implementation-internal (Chorus capabilities).
"""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATES_FILE = "tinkle/v1/updates.proto"
# Files and declarations excluded from the baseline-collision comparison,
# because the in-flight branch stack intentionally changes them. updates.proto
# is file-level (full retirement rewrite; pinned by the tests below). files.proto
# and media.proto are file-level additions of the file-transfer contract
# (FilesService plus shared media metadata/attributes/variants). The
# declaration sets cover (1) the reconciliation additions, (2) the
# PeerInput → Target rename touching common/messages/contacts, and (3) the
# *Source media-construction renames touching messages/bot_api/channels plus
# the additive Photo/Document/UserPhoto/StickerView and bot send-request
# changes. Anything else drifting from origin/main fails the suite. Trim
# entries on branches that touch other files, and drop entries once included
# in origin/main.
CHANGED_FILES = {"tinkle/v1/updates.proto", "tinkle/v1/files.proto", "tinkle/v1/media.proto"}
CHANGED_DECLARATIONS = {
    "tinkle.v1.PeerInput",
    "tinkle.v1.Target",
    "tinkle.v1.Message",
    "tinkle.v1.Dialog",
    "tinkle.v1.GetHistoryRequest",
    "tinkle.v1.GetHistoryResponse",
    "tinkle.v1.MessagesService",
    "tinkle.v1.GetMessagesRequest",
    "tinkle.v1.GetMessagesResponse",
    "tinkle.v1.GetTargetChangesRequest",
    "tinkle.v1.GetTargetChangesResponse",
    "tinkle.v1.TargetChange",
    "tinkle.v1.TargetChangeKind",
    "tinkle.v1.ReadHistoryRequest",
    "tinkle.v1.DeleteHistoryRequest",
    "tinkle.v1.DeleteMessagesRequest",
    "tinkle.v1.SetHistoryTTLRequest",
    "tinkle.v1.UpdatePinnedMessageRequest",
    "tinkle.v1.UnpinAllMessagesRequest",
    "tinkle.v1.SendMessageRequest",
    "tinkle.v1.SendMediaRequest",
    "tinkle.v1.SendMultiMediaRequest",
    "tinkle.v1.EditMessageRequest",
    "tinkle.v1.SetTypingRequest",
    "tinkle.v1.SendStartBotRequest",
    "tinkle.v1.SearchRequest",
    "tinkle.v1.GetMessagesReactionsRequest",
    "tinkle.v1.GetMessageReactionsListRequest",
    "tinkle.v1.SendReactionRequest",
    "tinkle.v1.GetUnreadMentionsRequest",
    "tinkle.v1.ReadMentionsRequest",
    "tinkle.v1.GetUnreadReactionsRequest",
    "tinkle.v1.ReadReactionsRequest",
    "tinkle.v1.SendVoteRequest",
    "tinkle.v1.GetPollVotesRequest",
    "tinkle.v1.GetPollResultsRequest",
    "tinkle.v1.ReadThreadRequest",
    "tinkle.v1.GetThreadMessageRequest",
    "tinkle.v1.BlockRequest",
    "tinkle.v1.UnblockRequest",
    # *Source renames: names retired from the baseline.
    "tinkle.v1.MediaInput",
    "tinkle.v1.InputPhoto",
    "tinkle.v1.InputDocument",
    "tinkle.v1.InputGeoPoint",
    "tinkle.v1.InputMessageContact",
    "tinkle.v1.InputPoll",
    "tinkle.v1.PhotoInput",
    "tinkle.v1.SingleMediaInput",
    "tinkle.v1.InputMedia",
    # *Source renames and typed media additions: names introduced by the branch.
    "tinkle.v1.MediaSource",
    "tinkle.v1.PhotoSource",
    "tinkle.v1.DocumentSource",
    "tinkle.v1.GeoPointSource",
    "tinkle.v1.ContactSource",
    "tinkle.v1.PollSource",
    "tinkle.v1.VideoSource",
    "tinkle.v1.AudioSource",
    "tinkle.v1.VoiceSource",
    "tinkle.v1.StickerSource",
    "tinkle.v1.ChatPhotoSource",
    "tinkle.v1.SingleMediaSource",
    "tinkle.v1.BotMediaSource",
    "tinkle.v1.MediaAttribute",
    "tinkle.v1.AnimatedAttribute",
    # Additive canonical file references, metadata, variants, and typed bot
    # alternatives extending the declarations below.
    "tinkle.v1.Photo",
    "tinkle.v1.Document",
    "tinkle.v1.UserPhoto",
    "tinkle.v1.StickerView",
    "tinkle.v1.EditChatPhotoRequest",
    "tinkle.v1.EditPhotoRequest",
    "tinkle.v1.SendPhotoRequest",
    "tinkle.v1.SendDocumentRequest",
    "tinkle.v1.SendVideoRequest",
    "tinkle.v1.SendAudioRequest",
    "tinkle.v1.SendVoiceRequest",
    "tinkle.v1.SendStickerRequest",
    "tinkle.v1.EditMessageMediaRequest",
}
REPLACED_FILES = {"tinkle/v1/realtime.proto"}


def run_buf(*arguments, input_bytes=None, check=True):
    """Run Buf with a deadline and binary-safe input/output."""
    result = subprocess.run(
        ["buf", *arguments], cwd=REPO_ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def declarations(image):
    """Index owned descriptors, including nested types and map entries."""
    result = {"message": {}, "enum": {}, "service": {}}

    def messages(items, prefix, filename):
        for item in items:
            name = prefix + item["name"]
            result["message"][name] = (filename, item)
            for enum in item.get("enumType", []):
                result["enum"][name + "." + enum["name"]] = (filename, enum)
            messages(item.get("nestedType", []), name + ".", filename)

    for file in image["file"]:
        if not file["name"].startswith("tinkle/"):
            continue
        prefix = file["package"] + "."
        messages(file.get("messageType", []), prefix, file["name"])
        for kind, key in (("enum", "enumType"), ("service", "service")):
            for item in file.get(key, []):
                result[kind][prefix + item["name"]] = (file["name"], item)
    return result


class ConnectivitySchemaTests(unittest.TestCase):
    """Pin constructors, service signatures, and public shapes that remain."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="tinkle-connectivity-")
        cls.addClassCleanup(temporary.cleanup)
        images = {}
        for label, source in (("current", "."), ("baseline", ".git#branch=origin/main")):
            result = run_buf(
                "build", source, "--exclude-source-info",
                "--as-file-descriptor-set", "-o", "-#format=json",
            )
            images[label] = json.loads(result.stdout)
            if label == "current":
                cls.image_path = Path(temporary.name) / "current.json"
                cls.image_path.write_bytes(result.stdout)
        cls.current = declarations(images["current"])
        cls.baseline = declarations(images["baseline"])
        cls.updates = next(f for f in images["current"]["file"] if f["name"] == UPDATES_FILE)

    def message(self, name):
        filename, descriptor = self.current["message"]["tinkle.v1." + name]
        self.assertEqual(UPDATES_FILE, filename)
        return descriptor

    def convert(self, fixture, message_type, source="json", target="binpb", check=True):
        payload = json.dumps(fixture).encode() if source == "json" else fixture
        return run_buf(
            "convert", f"{self.image_path}#format=json", f"--type=tinkle.v1.{message_type}",
            f"--from=-#format={source}", f"--to=-#format={target}",
            input_bytes=payload, check=check,
        )

    def round_trip(self, fixture, message_type="ObserveConnectivityResponse"):
        encoded = self.convert(fixture, message_type).stdout
        if not encoded:
            # All-defaults messages encode to zero bytes, and newer Buf
            # versions reject zero-length binary payloads on stdin. An
            # empty wire form decodes to an empty message by definition,
            # so the empty case asserts the encoding alone.
            return {}
        decoded = json.loads(self.convert(encoded, message_type, "binpb", "json").stdout)
        self.assertEqual(encoded, self.convert(decoded, message_type).stdout)
        return decoded

    def assert_fields(self, name, expected):
        """Compare all field names, tags, types, references, repetition and presence."""
        actual = [
            (f["name"], f["number"], f["type"].removeprefix("TYPE_"),
             f.get("typeName", "").removeprefix(".tinkle.v1."),
             f["label"] == "LABEL_REPEATED", f.get("proto3Optional", False))
            for f in self.message(name).get("field", [])
        ]
        self.assertEqual(expected, actual)

    def test_unrelated_contracts_are_unchanged(self):
        for kind in self.baseline:
            baseline = {n: d for n, d in self.baseline[kind].items()
                        if d[0] not in REPLACED_FILES | CHANGED_FILES
                        and n not in CHANGED_DECLARATIONS}
            current = {n: d for n, d in self.current[kind].items()
                       if d[0] not in CHANGED_FILES and n not in CHANGED_DECLARATIONS}
            self.assertTrue(baseline)
            self.assertEqual(baseline, current, kind)

    def test_constructor_inventory(self):
        self.assertEqual({
            "ConnectivityChanged", "ObserveConnectivityRequest",
            "ObserveConnectivityResponse",
        }, {m["name"] for m in self.updates["messageType"]})
        self.assertFalse(self.updates.get("enumType"), "no enum survives retirement")

    def test_service_methods(self):
        self.assertEqual(1, len(self.updates["service"]))
        service = self.updates["service"][0]
        self.assertEqual("UpdatesService", service["name"])
        self.assertEqual([
            ("ObserveConnectivity", True),
        ], [(m["name"], m.get("serverStreaming", False)) for m in service["method"]])
        for method in service["method"]:
            self.assertEqual(".tinkle.v1." + method["name"] + "Request", method["inputType"])
            self.assertEqual(".tinkle.v1." + method["name"] + "Response", method["outputType"])
            self.assertFalse(method.get("clientStreaming", False))

    def test_connectivity_shape(self):
        self.assert_fields("ConnectivityChanged", [
            ("user_id", 1, "INT64", "", False, False),
            ("online", 2, "BOOL", "", False, False),
            ("known", 3, "BOOL", "", False, False),
            ("revision", 4, "UINT64", "", False, False),
        ])
        self.assert_fields("ObserveConnectivityRequest", [
            ("user_ids", 1, "INT64", "", True, False),
        ])
        self.assert_fields("ObserveConnectivityResponse", [
            ("update", 1, "MESSAGE", "ConnectivityChanged", False, False),
        ])

    def test_sequential_tags_and_explicit_json_names(self):
        for message in self.updates["messageType"]:
            fields = message.get("field", [])
            self.assertEqual(list(range(1, len(fields) + 1)), [f["number"] for f in fields])
            self.assertFalse(message.get("reservedRange"))
            for field in fields:
                self.assertEqual(field["name"], field["jsonName"])

    def test_no_transport_or_opaque_internal_payloads(self):
        # The retired file carried Timestamp and Message hydration imports for
        # the removed envelope; the surviving surface declares nothing.
        self.assertEqual(set(), set(self.updates.get("dependency", [])))
        forbidden = {"connection_id", "request_id", "handshake", "version", "error", "type"}
        for message in self.updates["messageType"]:
            for field in message.get("field", []):
                self.assertNotIn(field["name"], forbidden)
                self.assertNotEqual("TYPE_BYTES", field["type"])
                self.assertNotIn("internal.", field.get("typeName", ""))

    def test_observation_round_trip(self):
        fixture = {"update": {"user_id": "42", "online": True, "known": True,
                              "revision": "9007199254740993"}}
        self.assertEqual(fixture, self.round_trip(fixture))

    def test_unknown_observation_state_round_trip(self):
        # Retraction: unknown must never be confused with a factual offline.
        fixture = {"update": {"user_id": "42", "known": False, "revision": "7"}}
        decoded = self.round_trip(fixture)["update"]
        self.assertNotIn("online", decoded)
        self.assertIs(False, decoded.get("known", False))
        self.assertEqual("7", decoded["revision"])
        self.assertNotIn("update", self.round_trip({}))

    def test_wrong_field_types_are_rejected_by_codec(self):
        for message_type, fixture in (
            ("ConnectivityChanged", {"user_id": "not-a-number", "online": True}),
            ("ObserveConnectivityRequest", {"user_ids": "42"}),
            ("ObserveConnectivityResponse", {"update": []}),
        ):
            self.assertNotEqual(
                0, self.convert(fixture, message_type, check=False).returncode,
                message_type,
            )


if __name__ == "__main__":
    unittest.main()
