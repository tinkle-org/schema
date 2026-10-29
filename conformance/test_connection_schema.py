"""InitConnect descriptor and real Buf codec checks; no generated SDKs.

These checks pin the public wrapper and ClientInfo shapes and preserve opaque
nested protobuf payloads. They do not implement or test runtime validation,
authorization, connection state, dispatch, concurrency, or retry semantics.
Those requirements are specified in connection.proto and enforced by servers.
"""

import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONNECTION_FILE = "tinkle/v1/connection.proto"
CLIENT_FIELDS = [
    "device_model", "platform", "os_version", "app_version", "app_build",
    "agent", "device_id", "install_id", "accept_language", "time_zone",
    "user_agent",
]


def run_buf(*arguments, input_bytes=None, check=True):
    """Run Buf with a deadline and binary-safe input/output."""
    result = subprocess.run(
        ["buf", *arguments], cwd=REPO_ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


class ConnectionSchemaTests(unittest.TestCase):
    """Pin InitConnect signatures, field tags, and binary/JSON carriage."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="tinkle-connection-")
        cls.addClassCleanup(temporary.cleanup)
        result = run_buf(
            "build", ".", "--exclude-source-info",
            "--as-file-descriptor-set", "-o", "-#format=json",
        )
        cls.files = {f["name"]: f for f in json.loads(result.stdout)["file"]}
        cls.messages = {
            m["name"]: m
            for f in cls.files.values() if f.get("package") == "tinkle.v1"
            for m in f.get("messageType", [])
        }
        cls.image_path = Path(temporary.name) / "image.json"
        cls.image_path.write_bytes(result.stdout)

    def convert(self, fixture, message_type, source="json", target="binpb", check=True):
        payload = json.dumps(fixture).encode() if source == "json" else fixture
        return run_buf(
            "convert", f"{self.image_path}#format=json",
            f"--type=tinkle.v1.{message_type}",
            f"--from=-#format={source}", f"--to=-#format={target}",
            input_bytes=payload, check=check,
        )

    def round_trip(self, fixture, message_type):
        encoded = self.convert(fixture, message_type).stdout
        # All-defaults protobufs encode to no bytes; Buf rejects empty stdin.
        if not encoded:
            return {}
        decoded = json.loads(self.convert(encoded, message_type, "binpb", "json").stdout)
        self.assertEqual(encoded, self.convert(decoded, message_type).stdout)
        return decoded

    def assert_fields(self, name, expected):
        actual = [
            (f["name"], f["number"], f["type"], f.get("typeName"),
             f["label"], f.get("proto3Optional", False))
            for f in self.messages[name].get("field", [])
        ]
        self.assertEqual([
            (field, number, "TYPE_" + kind, type_name, "LABEL_OPTIONAL", False)
            for field, number, kind, type_name in expected
        ], actual)
        self.assertNotIn("oneofDecl", self.messages[name])

    def client(self):
        return {
            "deviceModel": "iPhone17,2", "platform": "ios",
            "osVersion": "18.5", "appVersion": "1.4.2", "appBuild": "00142",
        }

    def test_connection_file_surface(self):
        descriptor = self.files[CONNECTION_FILE]
        self.assertEqual("tinkle.v1", descriptor["package"])
        self.assertEqual(
            "github.com/tinklehq/tinkle-proto/tinkle/v1;tinklev1",
            descriptor["options"]["goPackage"],
        )
        self.assertEqual(
            ["InitConnectRequest", "InitConnectResponse", "ClientInfo"],
            [m["name"] for m in descriptor["messageType"]],
        )
        self.assertFalse(descriptor.get("dependency"))
        self.assertFalse(descriptor.get("enumType"))
        self.assertEqual(1, len(descriptor["service"]))
        service = descriptor["service"][0]
        self.assertEqual("ConnectionService", service["name"])
        self.assertEqual(1, len(service["method"]))
        method = service["method"][0]
        self.assertEqual("InitConnect", method["name"])
        self.assertEqual(".tinkle.v1.InitConnectRequest", method["inputType"])
        self.assertEqual(".tinkle.v1.InitConnectResponse", method["outputType"])
        self.assertFalse(method.get("clientStreaming", False))
        self.assertFalse(method.get("serverStreaming", False))

    def test_wrapper_shapes(self):
        self.assert_fields("InitConnectRequest", [
            ("client", 1, "MESSAGE", ".tinkle.v1.ClientInfo"),
            ("method", 2, "STRING", None),
            ("payload", 3, "BYTES", None),
        ])
        self.assert_fields("InitConnectResponse", [("payload", 1, "BYTES", None)])

    def test_client_info_shape(self):
        self.assert_fields("ClientInfo", [
            (name, number, "STRING", None)
            for number, name in enumerate(CLIENT_FIELDS, 1)
        ])

    def test_client_info_json_names(self):
        self.assertEqual([
            "deviceModel", "platform", "osVersion", "appVersion", "appBuild",
            "agent", "deviceId", "installId", "acceptLanguage", "timeZone",
            "userAgent",
        ], [f["jsonName"] for f in self.messages["ClientInfo"]["field"]])

    def test_existing_auth_requests_are_unchanged(self):
        service = self.files["tinkle/v1/auth.proto"]["service"][0]
        self.assertEqual(["SendCode", "SignIn"], [m["name"] for m in service["method"]])
        self.assert_fields("SendCodeRequest", [
            ("phone_number", 1, "STRING", None), ("lang_code", 2, "STRING", None),
        ])
        self.assert_fields("SignInRequest", [
            ("phone_number", 1, "STRING", None), ("code", 2, "STRING", None),
            ("verification_id", 3, "STRING", None),
        ])

    def test_minimal_client_and_full_client_round_trip(self):
        minimal = self.client()
        self.assertEqual(minimal, self.round_trip(minimal, "ClientInfo"))
        full = dict(minimal, agent="Tinkle/1.4.2 SDK/0.9", deviceId="device-123",
                    installId="install-456", acceptLanguage="en-US,en;q=0.9",
                    timeZone="America/New_York", userAgent="Tinkle iOS/1.4.2")
        self.assertEqual(full, self.round_trip(full, "ClientInfo"))

    def test_client_info_boundary_labels_round_trip(self):
        limits = [128, 32, 64, 64, 64, 256, 128, 128, 64, 64, 1024]
        fixture = {name: "a" * limit for name, limit in zip(CLIENT_FIELDS, limits)}
        decoded = self.round_trip(fixture, "ClientInfo")
        for field, limit in zip(self.messages["ClientInfo"]["field"], limits):
            self.assertEqual("a" * limit, decoded[field["jsonName"]])

    def test_message_presence_and_labels_are_not_normalized_by_codec(self):
        for fixture in ({}, {"client": {}}, {"client": {"platform": " IOS "}}):
            with self.subTest(fixture=fixture):
                self.assertEqual(fixture, self.round_trip(fixture, "InitConnectRequest"))

    def test_wrapped_auth_requests_preserve_typed_payload(self):
        fixtures = [
            ("SendCode", {"phoneNumber": "+14155551234", "langCode": "en"}),
            ("SignIn", {"phoneNumber": "+14155551234", "code": "012345",
                        "verificationId": "e6f64856-0caa-4b02-a329-061a872b30f0"}),
        ]
        for method, request in fixtures:
            with self.subTest(method=method):
                encoded = self.convert(request, method + "Request").stdout
                wrapper = {
                    "client": self.client(),
                    "method": "/tinkle.v1.AuthService/" + method,
                    "payload": base64.b64encode(encoded).decode(),
                }
                decoded = self.round_trip(wrapper, "InitConnectRequest")
                nested = base64.b64decode(decoded["payload"])
                self.assertEqual(encoded, nested)
                self.assertEqual(request, json.loads(
                    self.convert(nested, method + "Request", "binpb", "json").stdout,
                ))

    def test_wrapped_response_preserves_typed_payload(self):
        response = {"sessionToken": "synthetic-fixture-token", "isNewUser": True}
        encoded = self.convert(response, "SignInResponse").stdout
        decoded = self.round_trip(
            {"payload": base64.b64encode(encoded).decode()}, "InitConnectResponse",
        )
        self.assertEqual(encoded, base64.b64decode(decoded["payload"]))

    def test_empty_nested_messages_are_valid_wire_shapes(self):
        self.assertEqual(b"", self.convert({}, "GetConfigRequest").stdout)
        request = {"client": self.client(), "method": "/tinkle.v1.HelpService/GetConfig"}
        self.assertEqual(request, self.round_trip(request, "InitConnectRequest"))
        self.assertEqual(b"", self.convert({}, "InitConnectResponse").stdout)

    def test_opaque_bytes_do_not_require_a_known_nested_type(self):
        payload = base64.b64encode(bytes(range(256))).decode()
        self.assertEqual(
            {"payload": payload},
            self.round_trip({"payload": payload}, "InitConnectResponse"),
        )

    def test_codec_does_not_enforce_server_constraints(self):
        """Even missing/unsafe labels encode; runtime rejection needs server tests."""
        self.assertEqual(b"", self.convert({}, "InitConnectRequest").stdout)
        for value in ("", "   ", "m" * 129, "Téléphone", "model\n"):
            with self.subTest(value=value):
                fixture = dict(self.client(), deviceModel=value)
                decoded = self.round_trip(fixture, "ClientInfo")
                self.assertEqual(value, decoded.get("deviceModel", ""))

    def test_wrong_field_types_are_rejected_by_codec(self):
        for message_type, fixture in [
            ("ClientInfo", {"appBuild": 142}),
            ("InitConnectRequest", {"client": "not a message"}),
            ("InitConnectRequest", {"method": 42}),
            ("InitConnectRequest", {"payload": "%%%"}),
            ("InitConnectResponse", {"payload": [1, 2]}),
        ]:
            with self.subTest(message_type=message_type, fixture=fixture):
                self.assertNotEqual(0, self.convert(
                    fixture, message_type, check=False,
                ).returncode)


if __name__ == "__main__":
    unittest.main()
