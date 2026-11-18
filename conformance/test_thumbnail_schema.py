"""Pin the clean thumbnail cutover; codecs do not enforce media validation."""

import unittest

import test_files_schema as files


# Owning message -> pre-reset collection tag, current singular tag, boundary type.
# The historical tag identifies the exact allowed removal in baseline comparisons.
THUMBNAILS = {
    "PhotoSource": (3, 4, "ThumbnailSource"),
    "DocumentSource": (3, 4, "ThumbnailSource"),
    "VideoSource": (3, 4, "ThumbnailSource"),
    "AudioSource": (3, 4, "ThumbnailSource"),
    "StickerSource": (3, 6, "ThumbnailSource"),
    "ProfilePhotoSource": (3, 4, "ThumbnailSource"),
    "StickerAssetSource": (3, 4, "ThumbnailSource"),
    "Photo": (7, 9, "Thumbnail"),
    "Document": (8, 10, "Thumbnail"),
    "ChatPhoto": (5, 7, "Thumbnail"),
    "UserPhoto": (2, 5, "Thumbnail"),
    "ProfilePhoto": (5, 8, "Thumbnail"),
    "StickerView": (9, 11, "Thumbnail"),
}


class ThumbnailSchemaTests(files.BufSchemaTestCase):
    """Check compact tags, presence, retired names and full-width file identities."""

    def test_shared_thumbnail_shapes(self):
        """Both boundary values carry a file ID and implicit positive dimensions."""
        for name in ("Thumbnail", "ThumbnailSource"):
            self.assert_fields(name, [
                ("file_id", 1, "INT64", "", False, False),
                ("width", 2, "UINT32", "", False, False),
                ("height", 3, "UINT32", "", False, False),
            ], files.MEDIA_FILE)
        for name in ("MediaVariant", "MediaVariantSource"):
            self.assertNotIn("tinkle.v1." + name, self.declarations["message"])
        self.assertNotIn("tinkle.v1.MediaVariantRole", self.declarations["enum"])

    def test_singular_wiring_and_removed_fields(self):
        """Remove old names entirely; the global reset deliberately reuses tags."""
        for name, (_, tag, kind) in THUMBNAILS.items():
            with self.subTest(message=name):
                descriptor = self.descriptor(name)
                self.assertFalse(descriptor.get("reservedName"))
                self.assertFalse(descriptor.get("reservedRange"))
                fields = {f["name"]: f for f in descriptor["field"]}
                self.assertNotIn("variants", fields)
                field = fields["thumbnail"]
                self.assertEqual((tag, "TYPE_MESSAGE", ".tinkle.v1." + kind, "LABEL_OPTIONAL"),
                                 (field["number"], field["type"], field["typeName"], field["label"]))
                self.assertNotIn("oneofIndex", field)
        sticker = self.descriptor("StickerView")
        self.assertNotIn("thumb_file_id", [f["name"] for f in sticker["field"]])
        self.assertNotIn("thumbnail", [f["name"] for f in self.descriptor("VoiceSource")["field"]])

    def test_thumbnail_presence_and_codec(self):
        """Distinguish absent enrichment from present messages, preserving exact IDs."""
        thumbnail = {"fileId": "9007199254740993", "width": 128, "height": 64}
        for name in ("Thumbnail", "ThumbnailSource"):
            self.assertEqual(thumbnail, self.round_trip(thumbnail, name))
        for name in THUMBNAILS:
            for fixture in ({}, {"thumbnail": {}}, {"thumbnail": thumbnail}):
                self.assertEqual(fixture, self.round_trip(fixture, name))
            self.assertNotEqual(0, self.convert({"thumbnail": [thumbnail]}, name, check=False).returncode)
            # Buf 1.59 discards unknown JSON fields, even when not reserved.
            # This is codec behavior, not a compatibility alias or runtime validation.
            self.assertEqual({}, self.round_trip({"variants": [{"fileId": "7"}]}, name))
        # Missing/zero dimensions encode as defaults; owning actions must reject
        # them when the thumbnail message is present, not treat it as omission.
        self.assertEqual({"fileId": "1"}, self.round_trip(
            {"fileId": "1", "width": 0, "height": 0}, "ThumbnailSource"))


if __name__ == "__main__":
    unittest.main()
