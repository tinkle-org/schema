"""Update descriptor and real Buf codec checks; no generated SDKs.

Requires Buf and a local main branch. Descriptor comparisons and protobuf round
trips do not test runtime authorization, delivery, cursor continuity, source
publication, or atomic client application. The public controller adapters are
not implemented by this schema repository.
"""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATES_FILE = "tinkle/v1/updates.proto"
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


class UpdatesSchemaTests(unittest.TestCase):
    """Pin individual constructors, service signatures, and public payload shapes."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="tinkle-updates-")
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

    def round_trip(self, fixture, message_type="Update"):
        encoded = self.convert(fixture, message_type).stdout
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
                        if d[0] not in REPLACED_FILES | {UPDATES_FILE}}
            current = {n: d for n, d in self.current[kind].items()
                       if d[0] != UPDATES_FILE}
            self.assertTrue(baseline)
            self.assertEqual(baseline, current, kind)

    def test_constructor_inventory(self):
        self.assertEqual({
            "MessageContext", "MessageRefresh", "SendAttemptFailed", "ContentOmitted",
            "ReadStateInvalidated", "Update", "ReadUpdatesRequest",
            "ReadUpdatesResponse", "FollowUpdatesRequest", "FollowUpdatesResponse",
            "RebuildNeeded", "ConnectivityChanged", "ObserveConnectivityRequest",
            "ObserveConnectivityResponse",
        }, {m["name"] for m in self.updates["messageType"]})
        self.assertFalse(self.updates.get("enumType"), "oneof is the sole discriminator")

    def test_service_methods(self):
        self.assertEqual(1, len(self.updates["service"]))
        service = self.updates["service"][0]
        self.assertEqual("UpdatesService", service["name"])
        self.assertEqual([
            ("ReadUpdates", False), ("FollowUpdates", True), ("ObserveConnectivity", True),
        ], [(m["name"], m.get("serverStreaming", False)) for m in service["method"]])
        for method in service["method"]:
            self.assertEqual(".tinkle.v1." + method["name"] + "Request", method["inputType"])
            self.assertEqual(".tinkle.v1." + method["name"] + "Response", method["outputType"])
            self.assertFalse(method.get("clientStreaming", False))

    def test_single_update_has_exactly_one_application_payload(self):
        self.assert_fields("Update", [
            ("event_id", 1, "STRING", "", False, False),
            ("stream", 2, "STRING", "", False, False),
            ("cursor", 3, "UINT64", "", False, False),
            ("occurred_at", 4, "MESSAGE", ".google.protobuf.Timestamp", False, False),
            ("source_seq", 5, "INT64", "", False, True),
            ("source_revision", 6, "INT64", "", False, True),
            ("message_refresh", 7, "MESSAGE", "MessageRefresh", False, False),
            ("send_attempt_failed", 8, "MESSAGE", "SendAttemptFailed", False, False),
            ("content_omitted", 9, "MESSAGE", "ContentOmitted", False, False),
            ("read_state_invalidated", 10, "MESSAGE", "ReadStateInvalidated", False, False),
        ])
        record = self.message("Update")
        self.assertEqual("payload", record["oneofDecl"][0]["name"])
        for field in record["field"][6:]:
            self.assertEqual(0, field["oneofIndex"])

    def test_message_effects_are_one_constructor_not_companion_updates(self):
        for name, optional in (("MessageRefresh", True), ("SendAttemptFailed", False)):
            self.assert_fields(name, [
                ("message", 1, "MESSAGE", "Message", False, False),
                ("random_id", 2, "INT64", "", False, optional),
                ("context", 3, "MESSAGE", "MessageContext", False, False),
            ])
        self.assert_fields("MessageContext", [
            ("conversation_key", 1, "STRING", "", False, False),
            ("order_key", 2, "STRING", "", False, False),
            ("resolve_user_id", 3, "INT64", "", False, True),
            ("resolve_conversation", 4, "BOOL", "", False, False),
        ])

    def test_query_shapes(self):
        self.assert_fields("ReadUpdatesRequest", [
            ("stream", 1, "STRING", "", False, False),
            ("after_cursor", 2, "UINT64", "", False, False),
            ("page_size", 3, "INT32", "", False, False),
            ("max_replay_distance", 4, "UINT64", "", False, True),
        ])
        self.assert_fields("ReadUpdatesResponse", [
            ("updates", 1, "MESSAGE", "Update", True, False),
            ("replay_floor", 2, "UINT64", "", False, False),
            ("head", 3, "UINT64", "", False, False),
            ("has_more", 4, "BOOL", "", False, False),
        ])
        self.assert_fields("FollowUpdatesRequest", [
            ("stream", 1, "STRING", "", False, False),
            ("after_cursor", 2, "UINT64", "", False, False),
        ])

    def test_stream_result_shapes(self):
        self.assert_fields("FollowUpdatesResponse", [
            ("stream", 1, "STRING", "", False, False),
            ("head", 2, "UINT64", "", False, True),
            ("update", 3, "MESSAGE", "Update", False, False),
            ("rebuild_needed", 4, "MESSAGE", "RebuildNeeded", False, False),
        ])
        result = self.message("FollowUpdatesResponse")
        self.assertEqual("result", result["oneofDecl"][0]["name"])
        for field in result["field"][2:]:
            self.assertEqual(0, field["oneofIndex"])

    def test_connectivity_is_separate_from_replay(self):
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

    def test_nonidentifying_constructors_are_empty(self):
        for name in ("ContentOmitted", "ReadStateInvalidated", "RebuildNeeded"):
            self.assert_fields(name, [])

    def test_sequential_tags_and_explicit_json_names(self):
        for message in self.updates["messageType"]:
            fields = message.get("field", [])
            self.assertEqual(list(range(1, len(fields) + 1)), [f["number"] for f in fields])
            self.assertFalse(message.get("reservedRange"))
            for field in fields:
                self.assertEqual(field["name"], field["jsonName"])

    def test_no_transport_or_opaque_internal_payloads(self):
        self.assertEqual({"google/protobuf/timestamp.proto", "tinkle/v1/messages.proto"},
                         set(self.updates["dependency"]))
        forbidden = {"connection_id", "request_id", "handshake", "version", "error", "type"}
        for message in self.updates["messageType"]:
            for field in message.get("field", []):
                self.assertNotIn(field["name"], forbidden)
                self.assertNotEqual("TYPE_BYTES", field["type"])
                self.assertNotIn("internal.", field.get("typeName", ""))

    @staticmethod
    def message_update(failed=False):
        return {
            "event_id": "a1234567-89ab-4cde-8fab-0123456789ab",
            "stream": "user:42", "cursor": "9007199254740993",
            "occurred_at": "2026-10-24T12:00:00Z", "source_seq": "0",
            "source_revision": "2",
            "send_attempt_failed" if failed else "message_refresh": {
                "message": {"messageId": "9007199254740995", "message": "Hello 世界"},
                "random_id": "-9223372036854775808",
                "context": {"conversation_key": "42:99",
                            "order_key": "0000900719925474099300000000000000000000",
                            "resolve_user_id": "42", "resolve_conversation": True},
            },
        }

    def test_message_constructors_round_trip_with_int64_and_unicode(self):
        for failed in (False, True):
            fixture = self.message_update(failed)
            self.assertEqual(fixture, self.round_trip(fixture))

    def test_optional_sender_key_absent_is_not_zero(self):
        fixture = self.message_update()
        del fixture["message_refresh"]["random_id"]
        self.assertNotIn("random_id", self.round_trip(fixture)["message_refresh"])
        fixture["message_refresh"]["random_id"] = "0"
        self.assertEqual("0", self.round_trip(fixture)["message_refresh"]["random_id"])

    def test_omission_and_read_invalidation_round_trip(self):
        for payload in ("content_omitted", "read_state_invalidated"):
            fixture = {"stream": "user:42", "cursor": "1", payload: {}}
            self.assertEqual(fixture, self.round_trip(fixture))

    def test_page_contains_distinct_single_updates(self):
        first = {"stream": "user:42", "cursor": "1", "content_omitted": {}}
        second = {"stream": "user:42", "cursor": "2", "read_state_invalidated": {}}
        fixture = {"updates": [first, second], "replay_floor": "0", "head": "2",
                   "has_more": False}
        decoded = self.round_trip(fixture, "ReadUpdatesResponse")
        self.assertEqual([first, second], decoded["updates"])
        self.assertEqual("2", decoded["head"])
        # Proto3 JSON omits false; absent means no more replay remains.
        self.assertFalse(decoded.get("has_more", False))

    def test_progress_and_rebuild_preserve_optional_head(self):
        for result in ({}, {"rebuild_needed": {}}):
            fixture = {"stream": "user:42", **result}
            self.assertNotIn("head", self.round_trip(fixture, "FollowUpdatesResponse"))
            fixture["head"] = "0"
            self.assertEqual("0", self.round_trip(fixture, "FollowUpdatesResponse")["head"])

    def test_bounded_replay_fields_round_trip(self):
        request = {"stream": "user:42", "after_cursor": "1", "page_size": 100,
                   "max_replay_distance": "1000"}
        decoded_request = self.round_trip(request, "ReadUpdatesRequest")
        self.assertEqual(100, decoded_request["page_size"])
        self.assertEqual("1000", decoded_request["max_replay_distance"])
        # Threshold is optional; absent means no caller-imposed catch-up bound.
        minimal = {"stream": "user:42", "after_cursor": "1"}
        self.assertNotIn("max_replay_distance",
                         self.round_trip(minimal, "ReadUpdatesRequest"))
        page = {"updates": [], "replay_floor": "0", "head": "1", "has_more": True}
        self.assertTrue(self.round_trip(page, "ReadUpdatesResponse")["has_more"])

    def test_connectivity_round_trip(self):
        fixture = {"update": {"user_id": "42", "online": True, "known": True,
                              "revision": "9007199254740993"}}
        self.assertEqual(fixture, self.round_trip(fixture, "ObserveConnectivityResponse"))

    def test_conflicting_payloads_are_rejected_by_codec(self):
        fixture = self.message_update()
        fixture["content_omitted"] = {}
        result = self.convert(fixture, "Update", check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertTrue(result.stderr)

    def test_wrong_field_types_are_rejected_by_codec(self):
        for key, value in (("cursor", "not-a-number"), ("message_refresh", [])):
            fixture = copy.deepcopy(self.message_update())
            fixture[key] = value
            self.assertNotEqual(0, self.convert(fixture, "Update", check=False).returncode)

    def test_decoding_is_not_semantic_validation(self):
        # Missing payload, an invalid privacy combination, and a negative page size
        # remain representable. Runtime adapters must validate them separately.
        self.assertEqual({}, self.round_trip({}))
        private = {"event_id": "must-not-be-disclosed", "content_omitted": {}}
        self.assertEqual(private, self.round_trip(private))
        self.assertEqual({"page_size": -1},
                         self.round_trip({"page_size": -1}, "ReadUpdatesRequest"))


if __name__ == "__main__":
    unittest.main()
