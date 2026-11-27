"""Boost wire contracts. Entitlement, ACLs and atomic updates require runtime tests."""

import unittest

import test_files_schema as files


class BoostsSchemaTests(files.BufSchemaTestCase):
    def test_service(self):
        methods = ("GetBoostConfiguration", "GetMyBoosts", "ApplyBoosts",
                   "GetBoostStatus", "ListBoosts", "GetUserBoosts")
        path, service = self.declarations["service"]["tinkle.v1.BoostsService"]
        self.assertEqual("tinkle/v1/boosts.proto", path)
        self.assertEqual([{"name": m, "inputType": f".tinkle.v1.{m}Request",
                           "outputType": f".tinkle.v1.{m}Response"} for m in methods], service["method"])

    def test_private_slot_and_mutation(self):
        self.assert_fields("GetBoostConfigurationRequest", [])
        self.assert_fields("GetBoostConfigurationResponse", [("extra_shared_pins", 1, "UINT32", "", False, False)])
        self.assert_fields("GetMyBoostsRequest", [])
        self.assert_fields("GetMyBoostsResponse", [
            ("my_boosts", 1, "MESSAGE", "MyBoosts", False, False)])
        self.assert_fields("MyBoosts", [
            ("revision", 1, "UINT64", "", False, False), ("slot", 2, "MESSAGE", "BoostSlot", False, False)],
            "tinkle/v1/boost_types.proto")
        self.assert_fields("BoostSlot", [
            ("target", 1, "MESSAGE", "RoomQueryTarget", False, False),
            ("expires_at", 2, "INT64", "", False, False)], "tinkle/v1/boost_types.proto")
        self.assert_fields("ApplyBoostsRequest", [
            ("request_id", 1, "STRING", "", False, False), ("expected_revision", 2, "UINT64", "", False, False),
            ("target", 3, "MESSAGE", "RoomQueryTarget", False, False),
            ("release", 4, "MESSAGE", ".google.protobuf.Empty", False, False)])
        self.assert_oneof("ApplyBoostsRequest", "assignment", ["target", "release"])
        self.assert_fields("ApplyBoostsResponse", [
            ("accepted_revision", 1, "UINT64", "", False, False), ("my_boosts", 2, "MESSAGE", "MyBoosts", False, False),
            ("updates", 3, "MESSAGE", "Update", True, False)])

    def test_room_projections_and_hints(self):
        target = ("target", 1, "MESSAGE", "RoomQueryTarget", False, False)
        revision = ("revision", 1, "UINT64", "", False, False)
        self.assert_fields("GetBoostStatusRequest", [target])
        self.assert_fields("GetBoostStatusResponse", [revision, ("active_boost_count", 2, "UINT64", "", False, False),
                                                     ("shared_pin_limit", 3, "UINT32", "", False, False)])
        self.assert_fields("ListBoostsRequest", [target, ("page_size", 2, "UINT32", "", False, False),
                                                 ("page_token", 3, "STRING", "", False, False)])
        self.assert_fields("ListBoostsResponse", [revision, ("user_ids", 2, "INT64", "", True, False),
                                                  ("next_page_token", 3, "STRING", "", False, False)])
        self.assert_fields("GetUserBoostsRequest", [target, ("user_id", 2, "INT64", "", False, False)])
        self.assert_fields("GetUserBoostsResponse", [revision, ("boosting", 2, "BOOL", "", False, False)])
        leaf = "tinkle/v1/boost_updates.proto"
        self.assert_fields("MyBoostsChanged", [revision], leaf)
        self.assert_fields("BoostStatusChanged", [target, ("revision", 2, "UINT64", "", False, False)], leaf)

    def test_slot_states_and_explicit_release(self):
        rev = "9007199254740993"
        slot = {"expiresAt": "1900000000"}
        key = {"requestId": "9cf21817-a4bf-478d-aa79-e99f5abfca4d", "expectedRevision": rev}
        room = {"channelId": rev}
        for kind, fixture in (
            ("GetMyBoostsResponse", {"myBoosts": {"revision": rev}}),
            ("GetMyBoostsResponse", {"myBoosts": {"revision": rev, "slot": slot}}),
            ("GetMyBoostsResponse", {"myBoosts": {"revision": rev, "slot": dict(slot, target=room)}}),
            ("ApplyBoostsRequest", dict(key, target={"chatId": rev})),
            ("ApplyBoostsRequest", dict(key, release={})),
            ("ApplyBoostsResponse", {"acceptedRevision": rev, "myBoosts": {"revision": rev, "slot": dict(slot, target=room)}}),
            ("ApplyBoostsResponse", {"acceptedRevision": rev, "myBoosts": {"revision": str(int(rev) + 1)}}),
            ("BoostStatusChanged", {"revision": rev, "target": room}),
        ):
            with self.subTest(kind=kind, fixture=fixture):
                self.assertEqual(fixture, self.round_trip(fixture, kind))
        for invalid in (dict(key, target=room, release={}), dict(key, target=dict(room, chatId=rev))):
            self.assertNotEqual(0, self.convert(invalid, "ApplyBoostsRequest", check=False).returncode)


if __name__ == "__main__":
    unittest.main()
