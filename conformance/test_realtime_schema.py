"""Descriptor and ProtoJSON/binpb conformance checks; no generated bindings.

Requires Python's standard library, Buf 1.59, and a local main Git branch. Both
build inputs are local (no BSR/network input or code generation). Each descriptor
set is built once per class; conversions reuse the current image in an external
TemporaryDirectory, removed even if class setup fails. Subprocesses have deadlines.

These checks do NOT implement/enforce REALTIME.md's runtime max-count/byte limits,
authorization, cursor state/continuity, event grammar, reset recovery, or client
atomicity. Buf 1.59 silently discards unknown JSON field/enum names; the tests
record that these can decode to missing kind/UNSPECIFIED, NOT valid application
deliveries. A successful conversion must never substitute for semantic validation.
Proto3 numeric enums are open, and
decoding is not application validation. Default-valued non-optional scalars may
be omitted by Buf's ProtoJSON encoder; this is not the legacy manual WebSocket
JSON contract. No endpoint, runtime validator, or SDK is implemented.

Run from the repository root:
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s conformance -p 'test_*.py' -v
"""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


# Resolve inputs independently of the caller's working directory.
REPO_ROOT = Path(__file__).resolve().parents[1]
REALTIME_FILE = "tinkle/v1/realtime.proto"
NOTIFICATION_TYPE = "tinkle.v1.RealtimeNotification"


def _run_buf(*arguments, input_bytes=None, timeout=30, check=True):
    """Run local Buf operations with binary-safe stdin/stdout and a deadline."""
    command = ["buf", *arguments]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"{command!r} exited {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return result


def _declarations(image):
    """Index owned declarations, including nested messages/enums and map entries.

    Keep the complete descriptor object and its source filename: tag, type,
    jsonName, options, presence, oneofs, reservations, RPC signatures/streaming,
    nesting, and relocation all participate in the published compatibility check.
    """
    declarations = {"message": {}, "enum": {}, "service": {}}

    def visit_messages(messages, prefix, filename):
        """Walk nested descriptors without flattening away their contents."""
        for message in messages:
            name = prefix + message["name"]
            declarations["message"][name] = (filename, message)
            for enum in message.get("enumType", []):
                declarations["enum"][name + "." + enum["name"]] = (filename, enum)
            visit_messages(message.get("nestedType", []), name + ".", filename)

    for file in image["file"]:
        if not file["name"].startswith("tinkle/"):
            continue
        prefix = file["package"] + "."
        filename = file["name"]
        visit_messages(file.get("messageType", []), prefix, filename)
        for kind, key in (("enum", "enumType"), ("service", "service")):
            for declaration in file.get(key, []):
                declarations[kind][prefix + declaration["name"]] = (
                    filename,
                    declaration,
                )
    return declarations


def _field(name, number, field_type, *, repeated=False, reference=None,
           oneof=None, optional=False):
    """Specify a complete expected realtime field with its snake_case JSON name."""
    field = {
        "name": name,
        "number": number,
        "label": "LABEL_REPEATED" if repeated else "LABEL_OPTIONAL",
        "type": "TYPE_" + field_type,
        "jsonName": name,
    }
    if reference is not None:
        field["typeName"] = reference
    if oneof is not None:
        field["oneofIndex"] = oneof
    if optional:
        field["proto3Optional"] = True
    return field


class RealtimeSchemaTests(unittest.TestCase):
    """Freeze published descriptors and exercise Buf's codec, not an app runtime."""

    @classmethod
    def setUpClass(cls):
        """Build current/main once and register temporary-image cleanup up front."""
        super().setUpClass()
        temporary = tempfile.TemporaryDirectory(prefix="tinkle-realtime-schema-")
        cls.addClassCleanup(temporary.cleanup)
        images = {}
        for name, source in (("current", "."), ("baseline", ".git#branch=main")):
            result = _run_buf(
                "build", source, "--exclude-source-info",
                "--as-file-descriptor-set", "-o", "-#format=json", timeout=60,
            )
            images[name] = json.loads(result.stdout)
            if name == "current":
                cls.image_path = Path(temporary.name) / "current.json"
                cls.image_path.write_bytes(result.stdout)
        cls.current_image = images["current"]
        cls.baseline_image = images["baseline"]
        cls.current = _declarations(cls.current_image)
        cls.baseline = _declarations(cls.baseline_image)

    def _message(self, name):
        """Look up one current Tinkle message, failing if absent or relocated."""
        filename, descriptor = self.current["message"]["tinkle.v1." + name]
        self.assertEqual(REALTIME_FILE, filename)
        return descriptor

    def _convert(self, payload, source_format, target_format, *, check=True):
        """Convert through stdin using the already-built external JSON image."""
        return _run_buf(
            "convert", f"{self.image_path}#format=json",
            f"--type={NOTIFICATION_TYPE}", f"--from=-#format={source_format}",
            f"--to=-#format={target_format}", input_bytes=payload, check=check,
        )

    def _round_trip(self, fixture):
        """Serialize JSON to binpb, decode JSON, then verify binary stability."""
        encoded = self._convert(json.dumps(fixture).encode(), "json", "binpb")
        decoded = json.loads(self._convert(encoded.stdout, "binpb", "json").stdout)
        reencoded = self._convert(json.dumps(decoded).encode(), "json", "binpb")
        self.assertEqual(encoded.stdout, reencoded.stdout)
        return decoded

    def _assert_conversion_rejected(self, fixture):
        """Require a real Buf nonzero exit, never a test-side substitute validator."""
        result = self._convert(json.dumps(fixture).encode(), "json", "binpb", check=False)
        self.assertNotEqual(
            0, result.returncode,
            f"Buf accepted an ill-typed fixture: {fixture!r}",
        )
        self.assertTrue(result.stderr, "conversion failure must include a diagnostic")

    def test_published_messages_are_unchanged(self):
        """Every published message, nested type and map entry remains identical."""
        self.assertTrue(self.baseline["message"], "main must contain messages")
        for name, descriptor in self.baseline["message"].items():
            with self.subTest(message=name):
                self.assertIn(name, self.current["message"])
                self.assertEqual(descriptor, self.current["message"][name])

    def test_published_enums_are_unchanged(self):
        """Published enum values, numbers, options and reservations are frozen."""
        self.assertTrue(self.baseline["enum"], "main must contain enums")
        for name, descriptor in self.baseline["enum"].items():
            with self.subTest(enum=name):
                self.assertIn(name, self.current["enum"])
                self.assertEqual(descriptor, self.current["enum"][name])

    def test_grpc_services_are_identical_without_realtime_service(self):
        """Generic Syntra method identifiers must not become gRPC declarations."""
        self.assertTrue(self.baseline["service"], "main must contain services")
        self.assertEqual(self.baseline["service"], self.current["service"])
        for file in self.current_image["file"]:
            for service in file.get("service", []):
                with self.subTest(file=file["name"], service=service["name"]):
                    self.assertNotIn(service["name"], ("RealtimeService", "Realtime"))

    def test_notification_has_exact_application_oneof(self):
        """The only notification variants are batch=1, presence=2 and reset=3."""
        self.assertEqual({
            "name": "RealtimeNotification",
            "field": [
                _field("batch", 1, "MESSAGE", reference=".tinkle.v1.RealtimeBatch", oneof=0),
                _field("presence", 2, "MESSAGE", reference=".tinkle.v1.RealtimeOnline", oneof=0),
                _field("reset_required", 3, "MESSAGE", reference=".tinkle.v1.RealtimeResetRequired", oneof=0),
            ],
            "oneofDecl": [{"name": "kind"}],
        }, self._message("RealtimeNotification"))

    def test_new_application_messages_do_not_duplicate_transport_fields(self):
        """New declarations cannot add handshake fields or wrap legacy framing."""
        forbidden_names = {"version", "connectionid", "hello", "ready", "error"}
        forbidden_types = {
            ".tinkle.v1." + name for name in (
                "RealtimeFrame", "RealtimeReady", "RealtimeUpdate",
                "RealtimeConnectControl", "RealtimeError",
            )
        }
        legacy_framing = {name.rsplit(".", 1)[1] for name in forbidden_types}
        self.assertIn(NOTIFICATION_TYPE, self.current["message"])
        for name, (filename, descriptor) in self.current["message"].items():
            if filename != REALTIME_FILE:
                continue
            # Exempt frozen legacy framing (including its nested map entries),
            # not application messages, even after the new binding lands on main.
            root_name = name.removeprefix("tinkle.v1.").split(".")[0]
            if root_name in legacy_framing:
                continue
            for field in descriptor.get("field", []):
                with self.subTest(message=name, field=field["name"]):
                    for spelling in (field["name"], field["jsonName"]):
                        self.assertNotIn(spelling.replace("_", "").lower(), forbidden_names)
                    self.assertNotIn(field.get("typeName"), forbidden_types)

    def test_subscribe_response_reserves_connection_slot_and_keeps_tags(self):
        """Tag 1/name connection_id stay reserved; tags 2/3/4 retain their shapes."""
        self.assertEqual({
            "name": "SubscribeResponse",
            "field": [
                _field("stream", 2, "STRING"),
                _field("after_cursor", 3, "UINT64"),
                _field("head", 4, "UINT64", oneof=0, optional=True),
            ],
            "oneofDecl": [{"name": "_head"}],
            # Descriptor reserved range ends are exclusive.
            "reservedRange": [{"start": 1, "end": 2}],
            "reservedName": ["connection_id"],
        }, self._message("SubscribeResponse"))

    def test_batch_fields_are_immutable(self):
        """Pin batch stream/events/final_cursor tags, types and JSON names."""
        self.assertEqual({
            "name": "RealtimeBatch",
            "field": [
                _field("stream", 1, "STRING"),
                _field("events", 2, "MESSAGE", repeated=True, reference=".tinkle.v1.RealtimeEvent"),
                _field("final_cursor", 3, "UINT64"),
            ],
        }, self._message("RealtimeBatch"))

    def test_event_fields_are_immutable(self):
        """Pin metadata presence and every event payload reference/tag/JSON name."""
        fields = [
            _field("event_id", 1, "STRING"),
            _field("stream", 2, "STRING"),
            _field("cursor", 3, "UINT64"),
            _field("occurred_at", 4, "MESSAGE", reference=".google.protobuf.Timestamp"),
            _field("source_seq", 5, "INT64", oneof=1, optional=True),
            _field("source_revision", 6, "INT64", oneof=2, optional=True),
            _field("type", 7, "ENUM", reference=".tinkle.v1.RealtimeEventType"),
        ]
        variants = (
            ("message_snapshot", "RealtimeMessageSnapshot"),
            ("message_send_failed", "RealtimeMessageSendFailed"),
            ("update_redacted", "RealtimeUpdateRedacted"),
            ("dialog_read_advanced", "RealtimeDialogReadAdvanced"),
            ("user_hydration", "RealtimeUserHydration"),
            ("chat_hydration", "RealtimeChatHydration"),
            ("chat_position", "RealtimeChatPosition"),
        )
        fields.extend(
            _field(name, tag, "MESSAGE", reference=".tinkle.v1." + reference, oneof=0)
            for tag, (name, reference) in enumerate(variants, start=8)
        )
        self.assertEqual({
            "name": "RealtimeEvent", "field": fields,
            "oneofDecl": [{"name": "kind"}, {"name": "_source_seq"}, {"name": "_source_revision"}],
        }, self._message("RealtimeEvent"))

    def test_event_enum_and_oneof_agree_statically(self):
        """Each known payload has a matching named enum; runtime matching is separate."""
        expected = {
            "REALTIME_EVENT_TYPE_UNSPECIFIED": 0,
            "REALTIME_EVENT_TYPE_MESSAGE_SNAPSHOT": 1,
            "REALTIME_EVENT_TYPE_MESSAGE_SEND_FAILED": 2,
            "REALTIME_EVENT_TYPE_UPDATE_REDACTED": 3,
            "REALTIME_EVENT_TYPE_DIALOG_READ_ADVANCED": 4,
            "REALTIME_EVENT_TYPE_USER_HYDRATION": 5,
            "REALTIME_EVENT_TYPE_CHAT_HYDRATION": 6,
            "REALTIME_EVENT_TYPE_CHAT_POSITION": 7,
        }
        filename, enum = self.current["enum"]["tinkle.v1.RealtimeEventType"]
        self.assertEqual(REALTIME_FILE, filename)
        self.assertEqual({
            "name": "RealtimeEventType",
            "value": [{"name": name, "number": number} for name, number in expected.items()],
        }, enum)
        event = self._message("RealtimeEvent")
        kind_index = event["oneofDecl"].index({"name": "kind"})
        variants = {
            "REALTIME_EVENT_TYPE_" + field["name"].upper()
            for field in event["field"] if field.get("oneofIndex") == kind_index
        }
        self.assertEqual(set(expected) - {"REALTIME_EVENT_TYPE_UNSPECIFIED"}, variants)

    def test_payloads_reuse_public_message_and_minimal_hints(self):
        """Snapshots use public Message; redaction/read hints carry no identity."""
        expected = {
            "RealtimeMessageSnapshot": {
                "field": [
                    _field("message", 1, "MESSAGE", reference=".tinkle.v1.Message"),
                    _field("random_id", 2, "INT64", oneof=0, optional=True),
                ], "oneofDecl": [{"name": "_random_id"}],
            },
            "RealtimeMessageSendFailed": {"field": [
                _field("message", 1, "MESSAGE", reference=".tinkle.v1.Message"),
                _field("random_id", 2, "INT64"),
            ]},
            "RealtimeUpdateRedacted": {},
            "RealtimeDialogReadAdvanced": {},
            "RealtimeUserHydration": {"field": [_field("user_id", 1, "INT64")]},
            "RealtimeChatHydration": {"field": [_field("chat_key", 1, "STRING")]},
            "RealtimeChatPosition": {"field": [
                _field("chat_key", 1, "STRING"), _field("order", 2, "STRING"),
            ]},
        }
        for name, contents in expected.items():
            with self.subTest(message=name):
                self.assertEqual({"name": name, **contents}, self._message(name))
        self.assertEqual("tinkle/v1/messages.proto", self.current["message"]["tinkle.v1.Message"][0])

    def test_no_new_syntra_or_any_imports(self):
        """The import graph stays application-only without new Syntra/Any edges."""
        baseline = {file["name"]: set(file.get("dependency", []))
                    for file in self.baseline_image["file"]}
        for file in self.current_image["file"]:
            additions = set(file.get("dependency", [])) - baseline.get(file["name"], set())
            for dependency in additions:
                with self.subTest(file=file["name"], dependency=dependency):
                    self.assertNotIn("syntra", dependency.lower())
                    self.assertNotEqual("google/protobuf/any.proto", dependency)

    def test_codec_singleton_redacted_batch(self):
        """A typed empty redaction survives binary encoding without identity data."""
        fixture = {"batch": {
            "stream": "user:42", "final_cursor": "1",
            "events": [{
                "stream": "user:42", "cursor": "1",
                "type": "REALTIME_EVENT_TYPE_UPDATE_REDACTED", "update_redacted": {},
            }],
        }}
        self.assertEqual(fixture, self._round_trip(fixture))

    def test_codec_unknown_presence_preserves_optional_zero_revision(self):
        """False scalars default normally; an explicitly present revision=0 survives."""
        fixture = {"presence": {
            "user_id": "42", "online": False, "known": False, "revision": "0",
        }}
        decoded = self._round_trip(fixture)
        self.assertEqual({"presence": {"user_id": "42", "revision": "0"}}, decoded)
        self.assertIs(decoded["presence"].get("known", False), False)
        self.assertIs(decoded["presence"].get("online", False), False)
        self.assertEqual("0", decoded["presence"]["revision"])

    def test_codec_reset_head_absent_zero_and_large_exact_integers(self):
        """Optional head distinguishes absent/zero and never loses high integer bits."""
        for head in (None, "0", "9007199254740993", "4611686018427387905", "9223372036854775807"):
            with self.subTest(head=head):
                reset = {"stream": "user:42"}
                if head is not None:
                    reset["head"] = head
                fixture = {"reset_required": reset}
                decoded = self._round_trip(fixture)
                self.assertEqual(fixture, decoded)
                self.assertEqual(head is not None, "head" in decoded["reset_required"])

    def test_codec_populated_snapshot_with_optional_primers(self):
        """Public Message, source markers, signed key and ordered primers round-trip."""
        metadata = {
            "event_id": "123e4567-e89b-42d3-a456-426614174000",
            "stream": "room:7", "cursor": "9007199254740993",
            "occurred_at": "2026-10-20T12:00:00Z",
            "source_seq": "0", "source_revision": "1",
        }
        snapshot = {**metadata,
            "type": "REALTIME_EVENT_TYPE_MESSAGE_SNAPSHOT",
            "message_snapshot": {
                "message": {
                    "messageId": "9223372036854775807", "peer": {"chatId": "7"},
                    "fromId": "42", "date": "2026-10-20T11:59:00Z",
                    "message": "Hello, \u4e16\u754c", "pinned": True,
                },
                "random_id": "-9223372036854775808",
            },
        }
        position = {**metadata, "type": "REALTIME_EVENT_TYPE_CHAT_POSITION",
                    "chat_position": {"chat_key": "room:7", "order": f"{int(metadata['cursor']):020d}{0:020d}"}}
        user = {**metadata, "type": "REALTIME_EVENT_TYPE_USER_HYDRATION",
                "user_hydration": {"user_id": "42"}}
        chat = {**metadata, "type": "REALTIME_EVENT_TYPE_CHAT_HYDRATION",
                "chat_hydration": {"chat_key": "room:7"}}
        for name, primers in (("none", []), ("user", [user]), ("chat", [chat]), ("both", [user, chat])):
            with self.subTest(primers=name):
                fixture = {"batch": {
                    "stream": metadata["stream"], "final_cursor": metadata["cursor"],
                    "events": [*primers, snapshot, position],
                }}
                self.assertEqual(fixture, self._round_trip(fixture))

    def test_codec_unknown_notification_kind_is_not_semantic_validation(self):
        """Buf can discard an unknown JSON kind; the resulting unset kind is invalid."""
        self.assertEqual({}, self._round_trip({"future_kind": {}}))

    def test_codec_unknown_event_enum_name_is_not_semantic_validation(self):
        """Buf can discard an unknown enum name; the resulting UNSPECIFIED is invalid."""
        self.assertEqual({"batch": {"events": [{}]}}, self._round_trip({
            "batch": {"events": [{"type": "REALTIME_EVENT_TYPE_FUTURE"}]},
        }))

    def test_codec_rejects_invalid_field_types_and_conflicting_oneofs(self):
        """Ill-typed values, uint64 overflow and multiple oneof members fail."""
        fixtures = {
            "invalid bool": {"presence": {"known": "not-a-bool"}},
            "invalid integer": {"reset_required": {"head": "not-an-integer"}},
            "invalid repeated field": {"batch": {"events": {}}},
            "negative uint64": {"reset_required": {"head": "-1"}},
            "uint64 overflow": {"reset_required": {"head": "18446744073709551616"}},
            "conflicting oneof": {"presence": {}, "reset_required": {}},
        }
        for name, fixture in fixtures.items():
            with self.subTest(case=name):
                self._assert_conversion_rejected(fixture)

    def test_codec_is_not_application_semantic_validation(self):
        """Document codec acceptance of cases that a runtime validator must reject.

        These are deliberately semantically invalid fixtures, NOT conformance
        examples. No auth/cursor-state/client-transaction machinery exists here.
        """
        redacted = {"stream": "user:42", "cursor": "1",
                    "type": "REALTIME_EVENT_TYPE_UPDATE_REDACTED", "update_redacted": {}}
        fixtures = {
            "missing notification kind": {},
            "empty batch": {"batch": {}},
            "over four events": {"batch": {"stream": "user:42", "final_cursor": "1",
                                           "events": [copy.deepcopy(redacted) for _ in range(5)]}},
            "enum disagrees with kind": {"batch": {"events": [
                {**redacted, "type": "REALTIME_EVENT_TYPE_MESSAGE_SNAPSHOT"},
            ]}},
            "unknown numeric enum": {"batch": {"events": [{**redacted, "type": 999}]}},
            "head exceeds application signed storage range": {
                "reset_required": {"stream": "user:42", "head": "9223372036854775808"},
            },
            "batch and member cursor disagree": {"batch": {
                "stream": "user:42", "final_cursor": "2", "events": [redacted],
            }},
        }
        for name, fixture in fixtures.items():
            with self.subTest(case=name):
                self.assertEqual(fixture, self._round_trip(fixture))


if __name__ == "__main__":
    unittest.main()
