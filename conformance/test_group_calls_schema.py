"""Group call wire contracts. Fixtures do not simulate authorization, SFU or roster transitions."""

import unittest

import test_files_schema as files


CALL = "9007199254740993"
JOIN = "9007199254740995"
SESSION = {"groupCallId": CALL, "participantId": JOIN, "sessionId": "local-device",
           "generation": "18446744073709551615"}


class GroupCallSchemaTests(files.BufSchemaTestCase):
    def test_room_snapshot_has_one_lifecycle_state(self):
        self.assert_oneof("GroupCall", "state", ["scheduled_for", "started_at", "ended_at", "cancelled_at"])
        when = "2030-01-01T00:00:00Z"
        for state in ("scheduledFor", "startedAt", "endedAt", "cancelledAt"):
            snapshot = {"groupCallId": CALL, "target": {"channelId": "11"}, "revision": "3", state: when}
            self.assertEqual(snapshot, self.round_trip(snapshot, "GroupCall"))

    def test_device_session_and_membership_selectors(self):
        self.assert_fields("GroupCallSession", [
            ("group_call_id", 1, "INT64", "", False, False), ("participant_id", 2, "INT64", "", False, False),
            ("session_id", 3, "STRING", "", False, False), ("generation", 4, "UINT64", "", False, False)])
        self.assert_fields("GetGroupCallConnectionRequest", [("group_call_id", 1, "INT64", "", False, False)])
        session = ("session", 1, "MESSAGE", "GroupCallSession", False, False)
        target = ("participant_id", 2, "INT64", "", False, False)
        for method, fields in (
            ("LeaveGroupCall", []), ("RestartGroupCallConnection", []), ("RemoveGroupCallParticipant", [target]),
            ("SetGroupCallParticipantRole", [target, ("role", 3, "ENUM", "GroupCallParticipantRole", False, False)]),
            ("SetGroupCallParticipantRestrictions", [target, ("restrictions", 3, "MESSAGE",
                                                              "GroupCallParticipantRestrictions", False, False)]),
            ("SetGroupCallHandRaised", [("hand_raised", 2, "BOOL", "", False, False)]),
        ):
            self.assert_fields(method + "Request", [session, *fields])
        for name, fixture in (
            ("JoinGroupCallRequest", {"groupCallId": CALL, "previousParticipantId": JOIN,
                                      "idempotencyKey": "018f65d2-1234-7abc-9def-0123456789ab"}),
            ("JoinGroupCallResponse", {"session": SESSION}),
            ("ListGroupCallParticipantsResponse", {"participantsRevision": "8", "nextPageToken": "next",
                "participants": [{"groupCallId": CALL, "participantId": JOIN, "userId": "17", "revision": "2",
                                  "role": "GROUP_CALL_PARTICIPANT_ROLE_LISTENER", "handRaised": True,
                                  "restrictions": {"cameraRestricted": True}, "media": {}}]}),
        ):
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_sfu_offer_and_answer_track_maps(self):
        session = {"session": SESSION, "sequence": "9007199254740997"}
        mic = {"mid": "mic", "source": "SOURCE_MICROPHONE", "participantId": JOIN}
        share = {"mid": "slides", "source": "SOURCE_PRESENTATION_VIDEO", "participantId": "23",
                 "presentationId": "screen-1"}
        for name, fixture in (
            ("GetGroupCallConnectionResponse", {"connection": {"session": SESSION, "relayOnly": True,
                "iceServers": [{"urls": ["turns:relay.invalid"], "username": "example", "credential": "fixture"}]}}),
            ("NegotiateGroupCallConnectionRequest", dict(session, offerSdp="offer fixture", tracks=[mic, share])),
            ("NegotiateGroupCallConnectionResponse", dict(session, answerSdp="answer fixture", tracks=[mic])),
            ("SetGroupCallMediaStateRequest", dict(session, publishedMids=["mic"])),
        ):
            with self.subTest(name=name):
                self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_history_keeps_direct_and_group_id_spaces_distinct(self):
        self.assert_oneof("CallReference", "kind", ["call_id", "group_call_id"])
        self.assert_fields("CallMessageSummary", [
            ("call", 1, "MESSAGE", "CallReference", False, False),
            ("media_kind", 2, "ENUM", "CallMediaKind", False, False),
            ("ended", 3, "MESSAGE", "CallEnded", False, False)])
        direct, group = {"callId": CALL}, {"groupCallId": CALL}
        self.assertNotEqual(0, self.convert({**direct, **group}, "CallReference", check=False).returncode)
        entries = [{"call": direct, "direction": "CALL_HISTORY_DIRECTION_INCOMING", "target": {"userId": "13"},
                    "ended": {"reason": "CALL_END_REASON_NO_ANSWER"}},
                   {"call": group, "direction": "CALL_HISTORY_DIRECTION_GROUP", "target": {"chatId": "42"},
                    "ended": {"reason": "CALL_END_REASON_COMPLETED", "durationSeconds": 0}}]
        for name, fixture in (
            ("ListCallHistoryResponse", {"entries": entries, "nextPageToken": "next"}),
            ("DeleteCallHistoryRequest", {"calls": [direct, group]}),
            ("DeleteCallHistoryResponse", {"deleted": [group], "unavailable": [direct]}),
            ("SubmitCallDiagnosticsRequest", {"call": group, "consent": True, "diagnostics": {"roundTripMs": 0}}),
        ):
            self.assertEqual(fixture, self.round_trip(fixture, name))
        self.assert_fields("CallDiagnostics", [(name, tag, "UINT32", "", False, True) for tag, name in
                                             enumerate(("round_trip_ms", "packet_loss_per_mille", "jitter_ms"), 1)])

    def test_presentation_endpoint_is_private_and_query_uses_stable_reference(self):
        name = "CallPresentationEndpoint"
        self.assert_fields(name, [("direct", 1, "MESSAGE", "CallSession", False, False),
                                  ("group", 2, "MESSAGE", "GroupCallSession", False, False)])
        direct = {"direct": {"callId": CALL, "sessionId": "other-device", "generation": "2"}}
        group = {"group": SESSION}
        for endpoint in (direct, group):
            self.assertEqual(endpoint, self.round_trip(endpoint, name))
        self.assertNotEqual(0, self.convert({**direct, **group}, name, check=False).returncode)
        self.assertEqual(group, self.decode(self.encode(direct, name) + self.encode(group, name), name))
        for method in ("StartCallPresentation", "StopCallPresentation", "ListCallPresentations"):
            request = self.descriptor(method + "Request")["field"]
            ref = "CallReference" if method == "ListCallPresentations" else name
            self.assertEqual(1, sum(f.get("typeName") == ".tinkle.v1." + ref and f["label"] == "LABEL_OPTIONAL"
                                    for f in request), method)
        response = self.descriptor("ListCallPresentationsResponse")["field"]
        self.assertEqual(1, sum(f.get("typeName") == ".tinkle.v1.CallPresentation" and f["label"] == "LABEL_REPEATED"
                                for f in response))
        for selector in ({"callId": CALL}, {"groupCallId": CALL}):
            fixture = {"call": selector}
            self.assertEqual(fixture, self.round_trip(fixture, "ListCallPresentationsRequest"))


if __name__ == "__main__":
    unittest.main()
