"""Global clean-reset invariants, including nested messages and oneof members."""

import unittest

import test_files_schema as files


class SchemaNumberingTests(files.BufSchemaTestCase):
    """Require compact declaration-order tags without inventing empty fields."""

    def test_all_messages_and_enums_use_the_clean_contract(self):
        """Inspect the whole public descriptor, including nested/map declarations."""
        def check_enum(enum, identity):
            """Keep proto3's explicit unknown value, but no reservation slots."""
            self.assertFalse(enum.get("reservedRange"), identity)
            self.assertFalse(enum.get("reservedName"), identity)
            first = enum["value"][0]
            self.assertTrue(first["name"].endswith("_UNSPECIFIED"), identity)
            self.assertEqual(0, first["number"], identity)

        def check_message(message, identity):
            """Oneofs share their enclosing message's sequence; nested types restart."""
            self.assertFalse(message.get("reservedRange"), identity)
            self.assertFalse(message.get("reservedName"), identity)
            fields = message.get("field", [])
            self.assertEqual(list(range(1, len(fields) + 1)),
                             [f["number"] for f in fields], identity)
            for nested in message.get("nestedType", []):
                check_message(nested, identity + "." + nested["name"])
            for enum in message.get("enumType", []):
                check_enum(enum, identity + "." + enum["name"])

        for _, message in self.declarations["message"].values():
            check_message(message, "tinkle.v1." + message["name"])
        for _, enum in self.declarations["enum"].values():
            check_enum(enum, "tinkle.v1." + enum["name"])


if __name__ == "__main__":
    unittest.main()
