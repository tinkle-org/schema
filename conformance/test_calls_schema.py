"""Direct call wire checks and shared call privacy boundaries; not authorization or ICE tests."""

import json
import unittest

import test_files_schema as files
from test_updates_schema import declarations
from update_contract import CASE_FILES


class CallsSchemaTests(files.BufSchemaTestCase):
    def test_lifecycle_and_lookup_selectors(self):
        self.assert_oneof("Call", "state", ["ringing", "connecting", "active", "ended"])
        self.assert_oneof("GetCallRequest", "selector", ["call_id", "idempotency_key"])
        for state in ({"ringing": {"expiresAt": "2030-01-01T00:01:00Z"}},
                      {"connecting": {}}, {"active": {}},
                      {"ended": {"reason": "CALL_END_REASON_COMPLETED", "durationSeconds": 0}}):
            with self.subTest(state=next(iter(state))):
                call = {"callId": "9007199254740993", "revision": "2", **state}
                change = {"call_changed": {"call": call}}
                self.assertEqual(change, self.round_trip(change, "Update"))

    def test_shared_reads_and_updates_do_not_embed_private_signaling(self):
        # Follow message references: a private connection inside a shared call
        # snapshot leaks just as surely as a top-level connection field.
        seen = set()
        messages = declarations(json.loads(self.image_path.read_bytes()))["message"]

        def visit(name):
            if name in seen:
                return
            seen.add(name)
            path, message = messages[name]
            self.assertNotIn(path, ("tinkle/v1/call_signaling.proto", "tinkle/v1/group_call_media.proto"), name)
            self.assertNotIn(name, ("tinkle.v1.CallDiagnostics", "tinkle.v1.CallPresentationEndpoint"))
            for field in message.get("field", []):
                self.assertNotIn(field["name"], {"session_id", "offer_sdp", "answer_sdp", "candidate", "credential",
                                                 "ice_servers", "mid", "published_mids", "stars", "diagnostics"}, name)
                if field["type"] == "TYPE_MESSAGE" and field["typeName"].startswith(".tinkle.v1."):
                    visit(field["typeName"].lstrip("."))

        changes = [n for n, path in CASE_FILES.items() if path == "tinkle/v1/call_updates.proto"]
        for root in (*changes, "GetCallResponse", "ListActiveCallsResponse", "GetGroupCallResponse",
                     "ListGroupCallsResponse", "GetGroupCallParticipantsResponse", "ListGroupCallParticipantsResponse",
                     "ListGroupCallInvitationsResponse", "ListCallPresentationsResponse", "ListCallHistoryResponse",
                     "CallMessageSummary"):
            visit("tinkle.v1." + root)

    def test_private_connection_round_trip(self):
        session = {"callId": "9007199254740993", "sessionId": "local-device",
                   "generation": "18446744073709551615"}
        ice = {"urls": ["turns:relay.invalid:5349"], "username": "example", "credential": "fixture",
               "expiresAt": "2030-01-01T00:00:00Z"}
        connection = {"session": session, "iceServers": [ice], "relayOnly": True}
        self.assertEqual(connection, self.round_trip(connection, "CallConnection"))

    def test_signal_payload_choices(self):
        name = "CallSignalPayload"
        self.assert_oneof(name, "kind", ["offer", "answer", "candidate", "end_of_candidates"])
        target = {"mid": "audio", "line": 0, "ufrag": "example"}
        cases = [{"offer": "offer fixture"}, {"answer": "answer fixture"},
                 {"candidate": {"candidate": "candidate:fixture", "target": target}},
                 {"endOfCandidates": target}]
        session = {"callId": "9007199254740993", "sessionId": "local-device", "generation": "2"}
        for payload in cases:
            with self.subTest(case=next(iter(payload))):
                signal = {"session": session, "position": "9007199254740995", "payload": payload,
                          "expiresAt": "2030-01-01T00:00:00Z"}
                self.assertEqual(signal, self.round_trip(signal, "CallSignal"))
        self.assertNotEqual(0, self.convert({**cases[0], **cases[1]}, name, check=False).returncode)
        self.assertEqual(cases[1], self.decode(self.encode(cases[0], name) + self.encode(cases[1], name), name))


if __name__ == "__main__":
    unittest.main()
