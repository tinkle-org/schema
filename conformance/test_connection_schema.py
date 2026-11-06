"""Connection RPC descriptor and real Buf codec checks; no generated SDKs.

These checks pin the public wrapper, KeepAlive, and ClientInfo shapes and preserve opaque
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
    """Pin connection signatures, field tags, and binary/JSON carriage."""

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
        """Pin both unary methods and their transport-independent message shapes."""
        descriptor = self.files[CONNECTION_FILE]
        self.assertEqual("tinkle.v1", descriptor["package"])
        self.assertEqual(
            "github.com/tinklehq/tinkle-proto/tinkle/v1;tinklev1",
            descriptor["options"]["goPackage"],
        )
        self.assertEqual(
            ["InitConnectRequest", "InitConnectResponse", "KeepAliveRequest",
             "KeepAliveResponse", "ClientInfo"],
            [m["name"] for m in descriptor["messageType"]],
        )
        self.assertFalse(descriptor.get("dependency"))
        self.assertFalse(descriptor.get("enumType"))
        self.assertEqual(1, len(descriptor["service"]))
        service = descriptor["service"][0]
        self.assertEqual("ConnectionService", service["name"])
        self.assertEqual(["InitConnect", "KeepAlive"], [m["name"] for m in service["method"]])
        for method in service["method"]:
            self.assertEqual(".tinkle.v1." + method["name"] + "Request", method["inputType"])
            self.assertEqual(".tinkle.v1." + method["name"] + "Response", method["outputType"])
            self.assertFalse(method.get("clientStreaming", False))
            self.assertFalse(method.get("serverStreaming", False))

    def test_keep_alive_shapes_and_sequence_round_trip(self):
        """KeepAlive carries only a lossless uint64 sequence in each direction."""
        for name in ("KeepAliveRequest", "KeepAliveResponse"):
            self.assert_fields(name, [("sequence", 1, "UINT64", None)])
            for sequence in ("1", "9007199254740993", "18446744073709551615"):
                with self.subTest(message=name, sequence=sequence):
                    fixture = {"sequence": sequence}
                    self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_wrapped_keep_alive_preserves_application_sequence(self):
        """InitConnect can carry the unary liveness payload without changing it."""
        fixture = {"sequence": "9007199254740993"}
        request = self.convert(fixture, "KeepAliveRequest").stdout
        wrapper = {
            "client": self.client(),
            "method": "/tinkle.v1.ConnectionService/KeepAlive",
            "payload": base64.b64encode(request).decode(),
        }
        decoded = self.round_trip(wrapper, "InitConnectRequest")
        self.assertEqual(request, base64.b64decode(decoded["payload"]))
        response = self.convert(fixture, "KeepAliveResponse").stdout
        decoded = self.round_trip(
            {"payload": base64.b64encode(response).decode()}, "InitConnectResponse",
        )
        self.assertEqual(response, base64.b64decode(decoded["payload"]))

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

    def test_auth_enrollment_surface(self):
        """Pin the recoverable enrollment RPCs and retained sign-in field tags."""
        service = self.files["tinkle/v1/auth.proto"]["service"][0]
        self.assertEqual([
            "SendCode", "SignIn", "ResumeEnrollment", "ActivateEnrollment",
            "RotateEnrollment",
        ], [m["name"] for m in service["method"]])
        for method in service["method"]:
            self.assertEqual(".tinkle.v1." + method["name"] + "Request", method["inputType"])
            self.assertEqual(".tinkle.v1." + method["name"] + "Response", method["outputType"])
            self.assertFalse(method.get("clientStreaming", False))
            self.assertFalse(method.get("serverStreaming", False))
        self.assert_fields("SendCodeRequest", [
            ("phone_number", 1, "STRING", None), ("lang_code", 2, "STRING", None),
        ])
        self.assert_fields("SendCodeResponse", [
            ("code_type", 1, "ENUM", ".tinkle.v1.VerificationCodeType"),
            ("request_id", 2, "STRING", None),
            ("expires_at", 3, "MESSAGE", ".google.protobuf.Timestamp"),
            ("verification_id", 4, "STRING", None),
        ])
        self.assert_fields("SignInRequest", [
            ("phone_number", 1, "STRING", None), ("code", 2, "STRING", None),
            ("verification_id", 3, "STRING", None),
            ("operation_id", 4, "STRING", None), ("resume_secret", 5, "BYTES", None),
        ])
        self.assert_fields("SignInResponse", [
            ("user", 1, "MESSAGE", ".tinkle.v1.User"),
            ("is_new_user", 3, "BOOL", None),
            ("enrollment", 4, "MESSAGE", ".tinkle.v1.DeviceEnrollment"),
        ])
        response = self.messages["SignInResponse"]
        self.assertEqual([{"start": 2, "end": 3}], response["reservedRange"])
        self.assertEqual(["session_token"], response["reservedName"])

    def test_enrollment_shapes_and_secret_free_activation(self):
        """Activation takes a capability and tuple; its response carries no key."""
        self.assert_fields("DeviceEnrollment", [
            ("operation_id", 1, "STRING", None), ("session_id", 2, "STRING", None),
            ("authorization_key", 3, "BYTES", None), ("handle", 4, "BYTES", None),
            ("enrollment_epoch", 5, "UINT64", None),
            ("scope", 6, "ENUM", ".tinkle.v1.DeviceKeyScope"),
            ("expires_at", 7, "MESSAGE", ".google.protobuf.Timestamp"),
            ("state", 8, "ENUM", ".tinkle.v1.DeviceEnrollmentState"),
            ("user_id", 9, "INT64", None), ("account_auth_epoch", 10, "UINT64", None),
        ])
        self.assert_fields("DeviceEnrollmentStatus", [
            ("operation_id", 1, "STRING", None), ("session_id", 2, "STRING", None),
            ("handle", 3, "BYTES", None), ("enrollment_epoch", 4, "UINT64", None),
            ("scope", 5, "ENUM", ".tinkle.v1.DeviceKeyScope"),
            ("expires_at", 6, "MESSAGE", ".google.protobuf.Timestamp"),
            ("state", 7, "ENUM", ".tinkle.v1.DeviceEnrollmentState"),
            ("user_id", 8, "INT64", None), ("account_auth_epoch", 9, "UINT64", None),
        ])
        self.assert_fields("ActivateEnrollmentRequest", [
            ("operation_id", 1, "STRING", None), ("session_id", 2, "STRING", None),
            ("handle", 3, "BYTES", None), ("enrollment_epoch", 4, "UINT64", None),
            ("scope", 5, "ENUM", ".tinkle.v1.DeviceKeyScope"),
            ("resume_secret", 6, "BYTES", None),
        ])
        self.assert_fields("ActivateEnrollmentResponse", [
            ("enrollment", 1, "MESSAGE", ".tinkle.v1.DeviceEnrollmentStatus"),
        ])
        for name in ("ResumeEnrollment", "RotateEnrollment"):
            self.assert_fields(name + "Request", [
                ("operation_id", 1, "STRING", None), ("resume_secret", 2, "BYTES", None),
            ])
            self.assert_fields(name + "Response", [
                ("enrollment", 1, "MESSAGE", ".tinkle.v1.DeviceEnrollment"),
            ])

    def test_enrollment_enums_and_neutral_session_identifier(self):
        """Pin lifecycle values and keep UI session IDs separate from key material."""
        enums = {e["name"]: e for e in self.files["tinkle/v1/auth.proto"]["enumType"]}
        for name, values in (
            ("DeviceKeyScope", ["UNSPECIFIED", "ACCOUNT"]),
            ("DeviceEnrollmentState", ["UNSPECIFIED", "STAGED", "ACTIVE", "REVOKED", "EXPIRED"]),
        ):
            prefix = "DEVICE_KEY_SCOPE_" if name == "DeviceKeyScope" else "DEVICE_ENROLLMENT_STATE_"
            self.assertEqual(
                [(prefix + value, number) for number, value in enumerate(values)],
                [(v["name"], v["number"]) for v in enums[name]["value"]],
            )
        session_fields = self.messages["Session"]["field"]
        self.assertEqual(("id", 1, "TYPE_STRING"), (
            session_fields[0]["name"], session_fields[0]["number"], session_fields[0]["type"],
        ))
        self.assertTrue({"authorization_key", "session_token", "resume_secret", "handle"}.isdisjoint(
            f["name"] for f in session_fields
        ))
        fixture = {"id": "ce3ae9e5-ff55-4d2f-921d-e83a9ee77893", "current": True}
        self.assertEqual(fixture, self.round_trip(fixture, "Session"))

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
        """Initialization preserves verification and retained recovery inputs."""
        fixtures = [
            ("SendCode", {"phoneNumber": "+14155551234", "langCode": "en"}),
            ("SignIn", {"phoneNumber": "+14155551234", "code": "012345",
                        "verificationId": "e6f64856-0caa-4b02-a329-061a872b30f0",
                        "operationId": "a280178a-0789-4924-9c51-9af9d74f3349",
                        "resumeSecret": base64.b64encode(bytes(range(32))).decode()}),
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
        """Initialization preserves the protected typed enrollment response."""
        response = {"enrollment": self.enrollment(), "isNewUser": True}
        encoded = self.convert(response, "SignInResponse").stdout
        decoded = self.round_trip(
            {"payload": base64.b64encode(encoded).decode()}, "InitConnectResponse",
        )
        self.assertEqual(encoded, base64.b64decode(decoded["payload"]))

    def enrollment(self):
        """Build a synthetic staged-key fixture with lossless uint64 epochs."""
        return {
            "operationId": "a280178a-0789-4924-9c51-9af9d74f3349",
            "sessionId": "ce3ae9e5-ff55-4d2f-921d-e83a9ee77893",
            "authorizationKey": base64.b64encode(bytes(range(32))).decode(),
            "handle": base64.b64encode(bytes(range(8))).decode(),
            "enrollmentEpoch": "18446744073709551615",
            "scope": "DEVICE_KEY_SCOPE_ACCOUNT",
            "expiresAt": "2026-11-06T12:00:00Z",
            "state": "DEVICE_ENROLLMENT_STATE_STAGED",
            "userId": "9007199254740993", "accountAuthEpoch": "9007199254740995",
        }

    def test_enrollment_delivery_and_ack_round_trip(self):
        """Keys remain binary, and a large epoch survives JSON/binary conversion."""
        fixture = self.enrollment()
        for name in ("SignIn", "ResumeEnrollment", "RotateEnrollment"):
            with self.subTest(name=name):
                result = self.round_trip({"enrollment": fixture}, name + "Response")
                self.assertEqual(fixture, result["enrollment"])
        status = {key: value for key, value in fixture.items() if key != "authorizationKey"}
        status["state"] = "DEVICE_ENROLLMENT_STATE_ACTIVE"
        self.assertEqual({"enrollment": status}, self.round_trip(
            {"enrollment": status}, "ActivateEnrollmentResponse",
        ))
        # Descriptor shape, rather than unknown-field handling by a JSON codec,
        # guarantees that activation has no key field and sign-in has no token.

    def test_activation_provisioning_capability_round_trip(self):
        """Bootstrap activation preserves the exact candidate and binary capability."""
        enrollment = self.enrollment()
        request = {key: enrollment[key] for key in (
            "operationId", "sessionId", "handle", "enrollmentEpoch", "scope",
        )}
        request["resumeSecret"] = base64.b64encode(bytes(range(32))).decode()
        decoded = self.round_trip(request, "ActivateEnrollmentRequest")
        self.assertEqual(request, decoded)
        self.assertEqual(bytes(range(32)), base64.b64decode(decoded["resumeSecret"]))

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
