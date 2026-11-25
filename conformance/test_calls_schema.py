"""Direct call descriptor and wire checks, not endpoint authorization or ICE tests."""

import unittest

import test_files_schema as files


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

        def visit(name):
            if name in seen:
                return
            seen.add(name)
            path, message = self.declarations["message"][name]
            self.assertNotEqual("tinkle/v1/call_signaling.proto", path, name)
            for field in message.get("field", []):
                if field["type"] == "TYPE_MESSAGE" and field["typeName"].startswith(".tinkle.v1."):
                    visit(field["typeName"].lstrip("."))

        for root in ("GetCallResponse", "ListActiveCallsResponse", "CallChanged",
                     "CallSignalsAvailable", "CallConnectionRefreshRequired"):
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
