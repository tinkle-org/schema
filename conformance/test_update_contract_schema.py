"""Public update graph, append-only command replies, and old/new Buf wire checks."""

import json
import re
import unittest

import test_files_schema as files
from test_updates_schema import declarations
from update_contract import (BASELINE, CALL_METHODS, CASE_FILES, COMMANDS_WITHOUT_UPDATES,
                             NEW_SERVICE_METHODS, PRE_CALL_BASELINE, SOCIAL_METHODS, UPDATE_FILE,
                             UPDATE_RESPONSES, current_filename)


RESPONSE = "SendMessageResponse"
CALL_SUMMARY_FIELD = {"name": "call_summary", "jsonName": "callSummary", "number": 21,
                     "label": "LABEL_OPTIONAL", "type": "TYPE_MESSAGE", "typeName": ".tinkle.v1.CallMessageSummary"}


def with_social_fields(old):
    """Apply only the specified social additions to a historical descriptor."""
    daily = {"name": "daily_id", "jsonName": "dailyId", "number": 5,
             "label": "LABEL_OPTIONAL", "type": "TYPE_INT64", "oneofIndex": 0}
    if old["name"] == "FileAccessContext":
        post = dict(daily, name="post_id", jsonName="postId", number=6)
        return dict(old, field=[*old["field"], daily, post])
    if old["name"] in ("ReplyInput", "MessageReplyHeader"):
        oneofs = old.get("oneofDecl", [])
        tag = 5 if old["name"] == "ReplyInput" else 6
        return dict(old, field=[*old["field"], dict(daily, number=tag, oneofIndex=len(oneofs), proto3Optional=True)],
                    oneofDecl=[*oneofs, {"name": "_daily_id"}])
    return old


class UpdateContractSchemaTests(files.BufSchemaTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.baseline_path = cls.image_path.with_name("before-updates.json")
        files.run_buf("build", ".git#ref=" + BASELINE, "--exclude-source-info",
                      "--as-file-descriptor-set", "-o", str(cls.baseline_path))
        cls.before = declarations(json.loads(cls.baseline_path.read_bytes()))
        cls.pre_call_path = cls.image_path.with_name("before-calls.json")
        files.run_buf("build", ".git#ref=" + PRE_CALL_BASELINE, "--exclude-source-info",
                      "--as-file-descriptor-set", "-o", str(cls.pre_call_path))
        current = json.loads(cls.image_path.read_bytes())
        cls.after = {p["name"]: p for p in current["file"]}
        cls.current = declarations(current)

    def test_only_planned_fields_appended_since_pre_call_baseline(self):
        before = declarations(json.loads(self.pre_call_path.read_bytes()))
        for kind in ("message", "enum"):
            for name, (old_path, old) in before[kind].items():
                path, current = self.current[kind][name]
                if name == "tinkle.v1.Update":
                    # test_update_surface pins every appended choice.
                    current = dict(current, field=current["field"][:len(old["field"])])
                elif name == "tinkle.v1.Message":
                    old = dict(old, field=[*old["field"], CALL_SUMMARY_FIELD])
                self.assertEqual((old_path, with_social_fields(old)), (path, current), name)

    def test_legacy_fields_and_file_moves(self):
        for kind in ("message", "enum"):
            for name, (old_path, old) in self.before[kind].items():
                with self.subTest(type=name):
                    path, current = self.current[kind][name]
                    self.assertEqual(current_filename(old_path, name), path)
                    expected = dict(old)
                    short = name.removeprefix("tinkle.v1.")
                    fields = old.get("field", [])
                    if short in UPDATE_RESPONSES:
                        expected["field"] = [*fields, self.updates_field(len(fields) + 1)]
                    elif short == "Message":
                        expected["field"] = [*fields, CALL_SUMMARY_FIELD]
                    elif short in ("GetInfoResponse", "OwnedBot"):
                        # Additional fields are pinned by the bot recovery check below.
                        current = dict(current, field=current["field"][:len(fields)])
                    self.assertEqual(with_social_fields(expected), current)

    @staticmethod
    def updates_field(tag):
        return {"name": "updates", "jsonName": "updates", "number": tag,
                "label": "LABEL_REPEATED", "type": "TYPE_MESSAGE", "typeName": ".tinkle.v1.Update"}

    def test_only_planned_command_replies_embed_updates(self):
        actual = []
        for name, (_, msg) in self.current["message"].items():
            for field in msg.get("field", []):
                if field.get("typeName") == ".tinkle.v1.Update":
                    self.assertEqual(self.updates_field(field["number"]), field, name)
                    actual.append(name.removeprefix("tinkle.v1."))
        self.assertEqual(145, len(UPDATE_RESPONSES))
        self.assertCountEqual(UPDATE_RESPONSES, actual)

    def test_update_inventory_accounts_for_rpc_handlers(self):
        """Review commands by service/method, not just messages whose names end in Response."""
        outputs = []
        without_updates = set()
        reads = ("Get", "List", "Search", "BatchGet", "Check", "CanSend", "Validate", "Observe")
        for _, service in self.current["service"].values():
            for method in service["method"]:
                output = method["outputType"].removeprefix(".tinkle.v1.")
                if output in UPDATE_RESPONSES:
                    self.assertFalse(method["name"].startswith(reads), method["name"])
                    outputs.append(output)
                elif not method["name"].startswith(reads):
                    without_updates.add((service["name"], method["name"]))
        self.assertCountEqual(UPDATE_RESPONSES, outputs)
        self.assertEqual({(service, method) for service, methods in COMMANDS_WITHOUT_UPDATES.items()
                          for method in methods.split()}, without_updates)

    def test_baseline_services_and_new_method_signatures(self):
        services = dict(self.current["service"])
        key = "tinkle.v1.MessagesService"
        path, service = services[key]
        added = {name: {"name": name, "inputType": f".tinkle.v1.{name}Request",
                        "outputType": f".tinkle.v1.{name}Response"}
                 for name in ("SetDraft", "SetDialogPin", "MoveDialogToSpace")}
        methods = service["method"]
        self.assertCountEqual(added.values(), [m for m in methods if m["name"] in added])
        services[key] = path, dict(service, method=[m for m in methods if m["name"] not in added])
        for name, inventory in {"CallsService": CALL_METHODS, "SocialService": SOCIAL_METHODS, **NEW_SERVICE_METHODS}.items():
            path = f"tinkle/v1/{name.removesuffix('Service').lower()}.proto"
            expected = {"name": name, "method": [
                {"name": m, "inputType": f".tinkle.v1.{m}Request", "outputType": f".tinkle.v1.{m}Response"}
                for m in inventory]}
            self.assertEqual((path, expected), services.pop("tinkle.v1." + name))
        self.assertEqual(self.before["service"], services)

    def test_update_import_graph(self):
        # Buf rejects import cycles. Check every reachable file, not only direct imports.
        seen = set()
        def visit(path):
            if path not in seen:
                seen.add(path)
                self.assertFalse(self.after[path].get("service"), path)
                for dependency in self.after[path].get("dependency", []):
                    visit(dependency)
        visit(UPDATE_FILE)

    def test_update_payloads_are_not_recursive(self):
        # Imports can be acyclic while two messages in the same file refer to each other.
        done = set()

        def visit(name, path):
            self.assertNotIn(name, path, " -> ".join((*path, name)))
            if name not in done:
                for field in self.current["message"][name][1].get("field", []):
                    ref = field.get("typeName", "").lstrip(".")
                    if ref in self.current["message"]:
                        visit(ref, (*path, name))
                done.add(name)

        visit("tinkle.v1.Update", ())

    def test_bot_recovery_projections(self):
        self.assert_fields("GetInfoResponse", [
            ("info", 1, "MESSAGE", "BotInfo", False, False),
            ("group_default_admin_scopes", 2, "MESSAGE", "ChatAdminScopes", False, False),
            ("broadcast_default_admin_scopes", 3, "MESSAGE", "ChatAdminScopes", False, False)])
        self.assertEqual(("active_usernames", 4, "LABEL_REPEATED", "TYPE_STRING"),
                         tuple(self.descriptor("OwnedBot")["field"][3][k]
                               for k in ("name", "number", "label", "type")))
        self.assertEqual(4, len(self.descriptor("OwnedBot")["field"]))
        known_empty = {"groupDefaultAdminScopes": {}, "broadcastDefaultAdminScopes": {}}
        self.assertEqual(known_empty, self.round_trip(known_empty, "GetInfoResponse"))

    def test_owner_dialog_commands(self):
        target = ("target", 1, "MESSAGE", "Target", False, False)
        self.assert_fields("SetDraftRequest", [target, ("draft", 2, "MESSAGE", "DraftMessage", False, False),
                           ("expected_dialog_id", 3, "INT64", "", False, True),
                           ("expected_draft_revision", 4, "INT64", "", False, True)])
        self.assert_fields("SetDialogPinRequest", [target, ("pinned", 2, "BOOL", "", False, False)])
        self.assert_fields("MoveDialogToSpaceRequest", [target, ("space_id", 2, "INT64", "", False, False)])
        for method in ("SetDraft", "SetDialogPin", "MoveDialogToSpace"):
            self.assertEqual([self.updates_field(1)], self.descriptor(method + "Response", files.MESSAGES_FILE)["field"])
        clear = {"target": {"chatId": "11"}, "expectedDialogId": "9007199254740993", "expectedDraftRevision": "0"}
        for fixture in (clear, dict(clear, draft={"message": "hello"}), {"target": clear["target"]}):
            self.assertEqual(fixture, self.round_trip(fixture, "SetDraftRequest"))

    def test_update_surface(self):
        source = self.after[UPDATE_FILE]
        self.assertFalse(source.get("service"))
        self.assertFalse(source.get("enumType"))
        self.assertEqual(["Update"], [d["name"] for d in source["messageType"]])
        update = self.descriptor("Update", UPDATE_FILE)
        self.assertEqual(79, len(CASE_FILES))
        expected = []
        for tag, name in enumerate(CASE_FILES, 1):
            key = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            expected.append({"name": key, "jsonName": key, "number": tag, "label": "LABEL_OPTIONAL",
                             "type": "TYPE_MESSAGE", "typeName": ".tinkle.v1." + name, "oneofIndex": 0})
        self.assertEqual({"name": "Update", "oneofDecl": [{"name": "change"}], "field": expected}, update)
        for name, filename in CASE_FILES.items():
            self.descriptor(name, filename)
        for path in ("tinkle/v1/call_updates.proto", "tinkle/v1/social_updates.proto",
                     "tinkle/v1/payment_updates.proto", "tinkle/v1/boost_updates.proto"):
            changes = [name for name, filename in CASE_FILES.items() if filename == path]
            self.assertEqual(changes, [msg["name"] for msg in self.after[path]["messageType"]
                                       if msg["name"] in changes], path)
        self.assertNotIn("tinkle.v1.DialogInvalidated", self.current["message"])
        for name in ("MessageAdded", "MessageEdited"):
            self.assert_fields(name, [("message", 1, "MESSAGE", "Message", False, False)])
        target = ("target", 1, "MESSAGE", "Target", False, False)
        self.assert_fields("MessageAccepted", [target, ("idempotency_key", 2, "INT64", "", False, False),
                                              ("message_id", 3, "INT64", "", False, False)])
        self.assert_fields("DialogChanged", [target], "tinkle/v1/dialog_updates.proto")

        self.assert_fields("MessageRemoval", [("message_id", 1, "INT64", "", False, False),
                           ("scope", 2, "ENUM", "MessageRemovalScope", False, False),
                           ("message_revision", 3, "INT64", "", False, True)], "tinkle/v1/message_updates.proto")
        for name, owner, prefix, suffixes in (
            ("MessageRemovalScope", "message", "MESSAGE_REMOVAL_SCOPE_", ["UNSPECIFIED", "PERSONAL", "EVERYONE"]),
            ("ReadScope", "dialog", "READ_SCOPE_", ["UNSPECIFIED", "INBOX", "OUTBOX"]),
        ):
            path, descriptor = self.current["enum"]["tinkle.v1." + name]
            self.assertEqual(f"tinkle/v1/{owner}_updates.proto", path)
            self.assertEqual([{"name": prefix + s, "number": i} for i, s in enumerate(suffixes)], descriptor["value"])
        people = ("users", 2, "MESSAGE", "User", True, False)
        rooms = ("chats", 3, "MESSAGE", "Chat", True, False)
        self.assert_fields(RESPONSE, [("message", 1, "MESSAGE", "Message", False, False), people, rooms,
                                      ("updates", 4, "MESSAGE", "Update", True, False)],
                           files.MESSAGES_FILE)

    def test_sender_reply_and_independent_edit(self):
        # The same sender/target/message, but separate inputs: a stale body does not make
        # the bodyless receipt stale. Applying these in either order belongs to the SDK.
        target = {"userId": "22"}
        body = {"target": target, "fromId": "11", "messageId": "42", "acceptSeq": "8",
                "message": "first", "bodyRevision": "2", "personalPin": False}
        receipt = {"target": target, "idempotencyKey": "-9007199254740993", "messageId": "42"}
        sender = {"message": body, "updates": [
            {"message_added": {"message": body}}, {"message_accepted": receipt},
            {"dialog_changed": {"target": target}}]}
        self.assertEqual(sender, self.round_trip(sender, RESPONSE))
        edit = {"message_edited": {"message": dict(body, message="edited", bodyRevision="3")}}
        self.assertEqual(edit, self.round_trip(edit, "Update"))

    def test_peer_projection(self):
        # The other side of the DM sees the sender as target, not the sender's
        # target, private pin or receipt. This fixture does not test authorization.
        target = {"userId": "11"}
        body = {"target": target, "fromId": "11", "messageId": "42", "acceptSeq": "8",
                "message": "first", "bodyRevision": "2"}
        for notification in ({"message_added": {"message": body}}, {"dialog_changed": {"target": target}}):
            self.assertEqual(notification, self.round_trip(notification, "Update"))

    def test_invalid_update_shapes_and_conflicting_cases(self):
        conflicting = {"message_added": {}, "message_edited": {}}
        for message, fixture in (("Update", conflicting), (RESPONSE, {"updates": [conflicting]}),
                                 (RESPONSE, {"updates": {"updates": []}}), ("Update", {"dialog_changed": []})):
            with self.subTest(message=message, fixture=fixture):
                self.assertNotEqual(0, self.convert(fixture, message, check=False).returncode)
        # Unlike invalid JSON with two alternatives, concatenated binary oneofs use the last case.
        last = {"reconciliation_required": {}}
        wire = self.encode({"dialog_changed": {}}, "Update") + self.encode(last, "Update")
        self.assertEqual(last, self.decode(wire, "Update"))

    def test_pre_call_reader_preserves_known_siblings(self):
        first = {"dialog_changed": {"target": {"chatId": "7"}}}
        last = {"reconciliation_required": {}}
        current = {"updates": [first, {"call_changed": {}}, last]}
        wire = self.encode(current, RESPONSE)
        self.assertEqual(current, self.decode(wire, RESPONSE))
        old = self.convert(wire, RESPONSE, "binpb", "json", image_path=self.pre_call_path)
        self.assertEqual({"updates": [first, {}, last]}, json.loads(old.stdout))
        self.assertNotEqual(0, self.convert(wire[:-1], RESPONSE, "binpb", "json", check=False).returncode)

    def test_pre_call_reader_keeps_message_fields_and_known_updates(self):
        message = {"messageId": "9007199254740993", "target": {"chatId": "11"}, "bodyRevision": "1",
                   "personalPin": False}
        summary = {"call": {"groupCallId": "37"}, "ended": {"reason": "CALL_END_REASON_COMPLETED"}}
        known = {"dialog_changed": {"target": {"chatId": "11"}}}
        current = {"message": dict(message, callSummary=summary), "updates": [{"group_call_changed": {}}, known]}
        wire = self.encode(current, RESPONSE)
        self.assertEqual(current, self.decode(wire, RESPONSE))
        old = self.convert(wire, RESPONSE, "binpb", "json", image_path=self.pre_call_path)
        self.assertEqual({"message": message, "updates": [{}, known]}, json.loads(old.stdout))

    def test_pre_payments_reader_keeps_known_update_siblings(self):
        old = self.image_path.with_name("before-payments.json")
        files.run_buf("build", ".git#ref=a83e60986f837d7b3457e1e56c34e0904b2dcf3f", "--exclude-source-info",
                      "--as-file-descriptor-set", "-o", str(old))
        first = {"post_likes_changed": {}}
        last = {"dialog_changed": {"target": {"chatId": "7"}}}
        current = {"updates": [first, {"payment_changed": {"paymentId": "p", "revision": "1"}},
                               {"refund_changed": {"refundId": "r", "revision": "2"}},
                               {"my_entitlements_changed": {"revision": "3"}},
                               {"my_boosts_changed": {"revision": "4"}},
                               {"boost_status_changed": {"target": {"channelId": "7"}, "revision": "5"}}, last]}
        wire = self.encode(current, RESPONSE)
        self.assertEqual(current, self.decode(wire, RESPONSE))
        old_view = self.convert(wire, RESPONSE, "binpb", "json", image_path=old)
        self.assertEqual({"updates": [first, {}, {}, {}, {}, {}, last]}, json.loads(old_view.stdout))

    def test_binary_response_compatibility_in_both_directions(self):
        legacy = {"message": {"messageId": "9007199254740993", "target": {"chatId": "9"}, "fromId": "11",
                              "message": "hello", "acceptSeq": "8", "bodyRevision": "2"},
                  "users": [{"data": {"id": "11", "name": "Alice"}}], "chats": [{"chatId": "9", "title": "Room"}]}
        target = legacy["message"]["target"]
        operation = {"operationId": "ef01a521-eb3f-4995-af4b-08524880b52a", "success": True,
                     "completed": False, "processedCount": "17", "offset": 2}
        contacts = {"importedContacts": [{"userId": "22", "customId": "ok"}],
                    "retryContacts": [{"customId": "retry"}]}
        status_hint = {"target": target, "idempotencyKey": "-7", "revision": "1"}
        for response, result, updates in (
            (RESPONSE, legacy, [{"message_added": {"message": legacy["message"]}},
                                {"dialog_changed": {"target": target}}]),
            ("ImportContactsResponse", contacts, [{"contacts_changed": {}}]),
            ("DeleteHistoryResponse", operation, [{"history_changed": {"target": target}}]),
            ("SendMediaResponse", {"sendStatus": dict(status_hint, state="SEND_STATE_PENDING")},
             [{"send_status_changed": status_hint}]),
        ):
            with self.subTest(response=response):
                old_wire = self.convert(result, response, image_path=self.baseline_path).stdout
                self.assertEqual(result, self.decode(old_wire, response))
                self.assertEqual(self.encode(result, response), self.encode(dict(result, updates=[]), response))
                current = dict(result, updates=updates)
                wire = self.encode(current, response)
                self.assertEqual(current, self.decode(wire, response))
                old_view = self.convert(wire, response, "binpb", "json", image_path=self.baseline_path)
                self.assertEqual(result, json.loads(old_view.stdout))

    def test_legacy_scheduled_reply_has_no_updates_or_acceptance_position(self):
        pending = {"message": {"target": {"userId": "22"}, "messageId": "42", "message": "later",
                               "scheduledState": "MESSAGE_SCHEDULED_STATE_PENDING", "scheduleDate": 1893456000}}
        wire = self.convert(pending, RESPONSE, image_path=self.baseline_path).stdout
        self.assertEqual(pending, self.decode(wire, RESPONSE))


if __name__ == "__main__":
    unittest.main()
