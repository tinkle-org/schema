"""Shared rich-text and search descriptor/codec checks, not runtime validation."""

import unittest

import test_files_schema as files


class EntitiesSearchSchemaTests(files.BufSchemaTestCase):
    """Pin the shared entity vocabulary and backend-qualified search results."""

    def test_shared_entity_contract(self):
        """Keep messaging numbers, field tags and exact-version presence stable."""
        self.assert_fields("Entity", [
            ("type", 1, "ENUM", "EntityType", False, False),
            ("offset", 2, "INT32", "", False, False),
            ("length", 3, "INT32", "", False, False),
            ("url", 4, "STRING", "", False, False),
            ("user_id", 5, "INT64", "", False, False),
            ("language", 6, "STRING", "", False, False),
            ("custom_emoji_id", 7, "INT64", "", False, False),
            ("fallback_text", 8, "STRING", "", False, True),
            ("asset_version", 9, "UINT64", "", False, True),
        ], "tinkle/v1/entities.proto")
        values = ["UNSPECIFIED", "BOLD", "ITALIC", "UNDERLINE", "STRIKETHROUGH",
                  "CODE", "PRE", "URL", "TEXT_URL", "MENTION", "MENTION_NAME",
                  "PHONE", "EMAIL", "HASHTAG", "CASHTAG", "BOT_COMMAND",
                  "CUSTOM_EMOJI", "SPOILER", "BLOCKQUOTE"]
        enum = self.declarations["enum"]["tinkle.v1.EntityType"]
        self.assertEqual("tinkle/v1/entities.proto", enum[0])
        self.assertEqual([("ENTITY_TYPE_" + value, number)
                          for number, value in enumerate(values)],
                         [(v["name"], v["number"]) for v in enum[1]["value"]])

    def test_all_entity_fields_share_one_type(self):
        """Cover help, drafts, bodies, captions and both quote representations."""
        expected = {
            ("DraftMessage", "entities", 2), ("Message", "entities", 7),
            ("MessageReplyHeader", "quote_entities", 5),
            ("ReplyInput", "quote_entities", 3), ("SingleMediaSource", "entities", 3),
            ("SendMessageRequest", "entities", 8), ("SendMediaRequest", "entities", 9),
            ("EditMessageRequest", "entities", 5),
            ("EditUserInfoRequest", "entities", 3), ("WorkforceUserInfo", "entities", 4),
        }
        actual = set()
        for _, descriptor in self.declarations["message"].values():
            for field in descriptor.get("field", []):
                if field["name"] in ("entities", "quote_entities"):
                    self.assertEqual(".tinkle.v1.Entity", field["typeName"])
                    self.assertEqual("LABEL_REPEATED", field["label"])
                    actual.add((descriptor["name"], field["name"], field["number"]))
        self.assertEqual(expected, actual)
        for kind, names in (("message", ("MessageTextEntity", "MessageEntity")),
                            ("enum", ("MessageTextEntityType", "MessageEntityType"))):
            for name in names:
                self.assertNotIn("tinkle.v1." + name, self.declarations[kind])

    def test_entity_and_reaction_codec(self):
        """Round-trip supplementary text, shared help fields and unsigned versions."""
        entity = {"type": "ENTITY_TYPE_CUSTOM_EMOJI", "offset": 2, "length": 2,
                  "customEmojiId": "9007199254740993", "fallbackText": "👋",
                  "assetVersion": "18446744073709551615"}
        self.assertEqual(entity, self.round_trip(entity, "Entity"))
        for name in ("Message", "DraftMessage", "SingleMediaSource", "SendMessageRequest",
                     "SendMediaRequest", "EditMessageRequest", "EditUserInfoRequest",
                     "WorkforceUserInfo"):
            fixture = {"message": "😀👋", "entities": [entity]}
            self.assertEqual(fixture, self.round_trip(fixture, name))
        for name in ("ReplyInput", "MessageReplyHeader"):
            fixture = {"quoteText": "😀👋", "quoteEntities": [entity]}
            self.assertEqual(fixture, self.round_trip(fixture, name))
        self.assert_fields("Reaction", [
            ("emoticon", 1, "STRING", "", False, False),
            ("custom_emoji_id", 2, "INT64", "", False, False),
            ("asset_version", 3, "UINT64", "", False, True),
        ])
        reaction = {"emoticon": "👋", "customEmojiId": entity["customEmojiId"],
                    "assetVersion": entity["assetVersion"]}
        self.assertEqual(reaction, self.round_trip(reaction, "Reaction"))

    def test_search_response_contract(self):
        """Preserve every search result field and add explicit backend metadata."""
        self.assert_fields("SearchResponse", [
            ("messages", 1, "MESSAGE", "Message", True, False),
            ("users", 2, "MESSAGE", "User", True, False),
            ("chats", 3, "MESSAGE", "Chat", True, False),
            ("count", 4, "INT32", "", False, False),
            ("next_rate", 5, "INT32", "", False, True),
            ("next_cursor", 6, "STRING", "", False, True),
            ("more_available", 7, "BOOL", "", False, True),
            ("source", 8, "ENUM", "SearchSource", False, False),
            ("coverage", 9, "ENUM", "SearchCoverage", False, False),
        ])
        for name, values in (("SearchSource", ["UNSPECIFIED", "SERVER", "CACHE"]),
                             ("SearchCoverage", ["UNSPECIFIED", "INDEXED", "CACHED_SUBSET"])):
            prefix = "SEARCH_SOURCE_" if name == "SearchSource" else "SEARCH_COVERAGE_"
            enum = self.declarations["enum"]["tinkle.v1." + name][1]
            self.assertEqual([(prefix + v, i) for i, v in enumerate(values)],
                             [(v["name"], v["number"]) for v in enum["value"]])

    def test_search_metadata_codec(self):
        """Cache exhaustion preserves subset coverage; omission stays unknown."""
        for source, coverage in (("SERVER", "INDEXED"), ("CACHE", "CACHED_SUBSET")):
            fixture = {"messages": [{"messageId": "9007199254740993", "message": "literal %_"}],
                       "moreAvailable": False, "source": "SEARCH_SOURCE_" + source,
                       "coverage": "SEARCH_COVERAGE_" + coverage}
            self.assertEqual(fixture, self.round_trip(fixture, "SearchResponse"))
        self.assertEqual({"moreAvailable": False},
                         self.round_trip({"moreAvailable": False}, "SearchResponse"))


if __name__ == "__main__":
    unittest.main()
