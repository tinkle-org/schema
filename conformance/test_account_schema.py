"""Account session descriptor and real Buf codec checks; no generated SDKs.

Requires Buf only. These checks pin the public session-review surface and
implicit protobuf defaults, not runtime authorization, UUID validation,
confirmation/revocation serialization, or gap-free snapshot delivery.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_FILE = "tinkle/v1/account.proto"


def run_buf(*arguments, input_bytes=None, check=True):
    """Run Buf with a deadline and binary-safe input/output."""
    result = subprocess.run(
        ["buf", *arguments], cwd=REPO_ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


class AccountSchemaTests(unittest.TestCase):
    """Pin retained RPCs, credential-free session shapes, and codec defaults."""

    @classmethod
    def setUpClass(cls):
        """Build the account descriptors and retain an image for codec checks."""
        temporary = tempfile.TemporaryDirectory(prefix="tinkle-account-")
        cls.addClassCleanup(temporary.cleanup)
        result = run_buf(
            "build", ".", "--exclude-source-info",
            "--as-file-descriptor-set", "-o", "-#format=json",
        )
        cls.account = next(
            f for f in json.loads(result.stdout)["file"] if f["name"] == ACCOUNT_FILE
        )
        cls.messages = {m["name"]: m for m in cls.account["messageType"]}
        cls.image_path = Path(temporary.name) / "image.json"
        cls.image_path.write_bytes(result.stdout)

    def convert(self, fixture, message_type, source="json", target="binpb", check=True):
        """Convert a fixture through Buf using the retained descriptor image."""
        payload = json.dumps(fixture).encode() if source == "json" else fixture
        return run_buf(
            "convert", f"{self.image_path}#format=json",
            f"--type=tinkle.v1.{message_type}",
            f"--from=-#format={source}", f"--to=-#format={target}",
            input_bytes=payload, check=check,
        )

    def round_trip(self, fixture, message_type):
        """Round-trip JSON through binary and verify stable re-encoding."""
        encoded = self.convert(fixture, message_type).stdout
        # All-defaults protobufs encode to no bytes; Buf rejects empty stdin.
        if not encoded:
            return {}
        decoded = json.loads(self.convert(encoded, message_type, "binpb", "json").stdout)
        self.assertEqual(encoded, self.convert(decoded, message_type).stdout)
        return decoded

    def assert_fields(self, name, expected):
        """Compare every field's tag, type, reference, repetition and presence."""
        descriptor = self.messages[name]
        actual = [
            (f["name"], f["number"], f["type"].removeprefix("TYPE_"),
             f.get("typeName", "").removeprefix(".tinkle.v1."),
             f["label"] == "LABEL_REPEATED", f.get("proto3Optional", False))
            for f in descriptor.get("field", [])
        ]
        self.assertEqual(expected, actual, name)
        self.assertFalse(descriptor.get("oneofDecl"), name)
        for field in descriptor.get("field", []):
            self.assertNotIn("oneofIndex", field, name)
            self.assertEqual(
                "".join(part.title() if i else part for i, part in
                        enumerate(field["name"].split("_"))),
                field["jsonName"], name,
            )

    def session(self) -> dict[str, str | bool]:
        """Return a fresh session fixture with lossless dates and build labels."""
        return {
            "id": "ce3ae9e5-ff55-4d2f-921d-e83a9ee77893",
            "deviceModel": "Test device", "platform": "web",
            "systemVersion": "1.0", "appVersion": "1.4.2",
            "createdDate": "9007199254740993", "activeDate": "9007199254740995",
            "ip": "192.0.2.1", "country": "US", "region": "CA",
            "appBuild": "00142",
        }

    def test_account_service_methods(self):
        """Pin every account method's name, request, response, and unary mode."""
        self.assertEqual(1, len(self.account["service"]))
        service = self.account["service"][0]
        self.assertEqual("AccountService", service["name"])
        self.assertEqual([
            "RegisterPush", "UnregisterPush", "GetNotificationSettings",
            "UpdateNotificationSetting", "ResetNotificationSettings",
            "GetPrivacy", "SetPrivacy", "UpdateProfile", "ValidateUsername",
            "UpdateUsername", "DeleteAccount", "SendChangePhoneCode",
            "ChangePhoneNumber", "GetContentSettings", "SetContentSetting",
            "Logout", "RevokeSession", "RevokeSessions", "GetSessions",
            "ConfirmSession",
            "SetProfilePhoto", "GetProfilePhotos", "SelectProfilePhoto", "DeleteProfilePhoto",
        ], [m["name"] for m in service["method"]])
        for method in service["method"]:
            with self.subTest(method=method["name"]):
                self.assertEqual(".tinkle.v1." + method["name"] + "Request",
                                 method["inputType"])
                self.assertEqual(".tinkle.v1." + method["name"] + "Response",
                                 method["outputType"])
                self.assertFalse(method.get("clientStreaming", False))
                self.assertFalse(method.get("serverStreaming", False))

    def test_credential_free_session_shape(self):
        """Preserve session field tags and exclude credential-bearing fields."""
        # Exact inventory forbids credentials, key handles and provider payloads,
        # while preserving all pre-review fields at tags 1-12.
        self.assert_fields("Session", [
            ("id", 1, "STRING", "", False, False),
            ("device_model", 2, "STRING", "", False, False),
            ("platform", 3, "STRING", "", False, False),
            ("system_version", 4, "STRING", "", False, False),
            ("app_version", 5, "STRING", "", False, False),
            ("created_date", 6, "INT64", "", False, False),
            ("active_date", 7, "INT64", "", False, False),
            ("ip", 8, "STRING", "", False, False),
            ("country", 9, "STRING", "", False, False),
            ("region", 10, "STRING", "", False, False),
            ("current", 11, "BOOL", "", False, False),
            ("app_build", 12, "STRING", "", False, False),
            ("unconfirmed", 13, "BOOL", "", False, False),
        ])

    def test_session_rpc_shapes(self):
        """Pin the request and response shapes for session management."""
        for name in ("LogoutRequest", "RevokeSessionsRequest",
                     "GetSessionsRequest"):
            with self.subTest(message=name):
                self.assert_fields(name, [])
        for name in ("RevokeSessionRequest", "ConfirmSessionRequest"):
            with self.subTest(message=name):
                self.assert_fields(name, [("session_id", 1, "STRING", "", False, False)])
        self.assert_fields("GetSessionsResponse", [
            ("sessions", 1, "MESSAGE", "Session", True, False),
        ])
        self.assert_fields("ConfirmSessionResponse", [
            ("session", 1, "MESSAGE", "Session", False, False),
        ])

    def test_session_changed_is_an_identifier_only_refresh_hint(self):
        """Limit the notification payload to the neutral session identifier."""
        self.assert_fields("SessionChanged", [
            ("session_id", 1, "STRING", "", False, False),
        ])

    def test_unconfirmed_round_trip_in_session_responses(self):
        """Preserve true review flags and omit false or unset implicit defaults."""
        # True is representable even in ConfirmSessionResponse: only the server
        # can enforce that a successful confirmation returns false.
        for name in ("GetSessionsResponse", "ConfirmSessionResponse"):
            for state in (True, False, None):
                with self.subTest(message=name, unconfirmed=state):
                    session = self.session()
                    if state is not None:
                        session["unconfirmed"] = state
                    singular = name == "ConfirmSessionResponse"
                    fixture = {"session": session} if singular else {"sessions": [session]}
                    decoded = self.round_trip(fixture, name)
                    projection = decoded["session"] if singular else decoded["sessions"][0]
                    expected = self.session()
                    if state is True:
                        expected["unconfirmed"] = True
                    self.assertEqual(expected, projection)
                    self.assertIs(state is True, projection.get("unconfirmed", False))

    def test_snapshots_preserve_multiple_sessions_and_current_flag(self):
        """Preserve distinct sessions and the caller-relative current flag."""
        sessions = [dict(self.session(), current=True), {
            "id": "a280178a-0789-4924-9c51-9af9d74f3349", "unconfirmed": True,
        }]
        fixture = {"sessions": sessions}
        self.assertEqual(fixture, self.round_trip(fixture, "GetSessionsResponse"))

    def test_empty_requests_snapshots_and_message_presence(self):
        """Distinguish empty wire defaults from a present nested session."""
        for name in ("LogoutRequest", "RevokeSessionsRequest",
                     "GetSessionsRequest"):
            with self.subTest(message=name):
                self.assertEqual(b"", self.convert({}, name).stdout)
        for fixture in ({}, {"sessions": []}):
            with self.subTest(fixture=fixture):
                self.assertEqual(b"", self.convert(fixture, "GetSessionsResponse").stdout)
        self.assertEqual(b"", self.convert({}, "ConfirmSessionResponse").stdout)
        self.assertEqual({"session": {}}, self.round_trip(
            {"session": {"unconfirmed": False}}, "ConfirmSessionResponse",
        ))

    def test_confirm_session_identifier_round_trip_and_defaults(self):
        """Round-trip confirmation IDs and pin review-flag wire defaults."""
        fixture = {"sessionId": self.session()["id"]}
        self.assertEqual(fixture, self.round_trip(fixture, "ConfirmSessionRequest"))
        # Required UUIDs and response projections are runtime requirements, not
        # protobuf presence or codec validation rules.
        for fixture in ({}, {"sessionId": ""}):
            self.assertEqual(b"", self.convert(fixture, "ConfirmSessionRequest").stdout)
        self.assertEqual(b"", self.convert({"unconfirmed": False}, "Session").stdout)
        self.assertEqual(b"", self.convert({}, "Session").stdout)
        self.assertEqual(b"\x68\x01", self.convert({"unconfirmed": True}, "Session").stdout)

    def test_session_changed_identifier_round_trip_and_defaults(self):
        """Round-trip notification IDs without treating them as validated UUIDs."""
        fixture = {"sessionId": self.session()["id"]}
        self.assertEqual(fixture, self.round_trip(fixture, "SessionChanged"))
        for fixture in ({}, {"sessionId": ""}):
            with self.subTest(fixture=fixture):
                self.assertEqual(b"", self.convert(fixture, "SessionChanged").stdout)

    def test_wrong_field_types_are_rejected_by_codec(self):
        """Reject incompatible JSON types in session messages and notifications."""
        for name, fixture in (
            ("ConfirmSessionRequest", {"sessionId": 42}),
            ("SessionChanged", {"sessionId": 42}),
            ("Session", {"unconfirmed": "true"}),
            ("Session", {"unconfirmed": 1}),
            ("GetSessionsResponse", {"sessions": {}}),
            ("GetSessionsResponse", {"sessions": "not a list"}),
            ("GetSessionsResponse", {"sessions": [{"unconfirmed": []}]}),
            ("ConfirmSessionResponse", {"session": []}),
            ("ConfirmSessionResponse", {"session": {"unconfirmed": "false"}}),
        ):
            with self.subTest(message=name, fixture=fixture):
                self.assertNotEqual(0, self.convert(fixture, name, check=False).returncode)


if __name__ == "__main__":
    unittest.main()
