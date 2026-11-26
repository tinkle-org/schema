"""Wire contracts for independent Daily/Post lifecycles; no runtime enforcement."""

import json
import unittest

import test_files_schema as files


class SocialSchemaTests(files.BufSchemaTestCase):
    def test_shared_media_but_distinct_publications(self):
        self.assert_oneof("SocialMediaSource", "media", ["photo", "video"])
        self.assert_oneof("SocialMedia", "kind", ["photo", "video"])
        for name, source, repeated in (("Daily", "SocialMedia", False), ("Post", "SocialMedia", True),
                                       ("PublishDailyRequest", "SocialMediaSource", False),
                                       ("PublishPostRequest", "SocialMediaSource", True)):
            field = next(f for f in self.descriptor(name)["field"] if f["name"] == "media")
            self.assertEqual((".tinkle.v1." + source, repeated),
                             (field["typeName"], field["label"] == "LABEL_REPEATED"))
        for name, forbidden in (("Post", {"expires_at", "daily_id", "source_daily_id", "seen"}),
                                ("Daily", {"post_id", "liked_by_me", "like_count"}),
                                ("PublishPostRequest", {"also_publish_post", "daily_id", "expires_at"}),
                                ("ListDailyArchiveRequest", {"user_id", "author_id"}),
                                ("EditDailyRequest", {"media", "expires_at", "published_at"}),
                                ("EditPostRequest", {"media", "expires_at", "published_at"})):
            self.assertFalse(forbidden.intersection(f["name"] for f in self.descriptor(name)["field"]), name)
        # Decoders may discard unknown JSON fields. Pin the authoring vocabulary
        # in the descriptor; only a server can reject an empty/unknown source.
        self.assert_fields("SocialMediaSource", [("photo", 1, "MESSAGE", "PhotoSource", False, False),
                                                ("video", 2, "MESSAGE", "VideoSource", False, False)])
        conflict = {"photo": {"fileId": "1"}, "video": {"fileId": "2"}}
        self.assertNotEqual(0, self.convert(conflict, "SocialMediaSource", check=False).returncode)

    def test_dual_publish_and_archive_save(self):
        key = "6c651447-0b44-4f20-b311-cfdbe00cb60f"
        photo = {"photo": {"fileId": "9007199254740993"}}
        video = {"video": {"fileId": "9007199254740994"}}
        contacts = {"mode": "SOCIAL_AUDIENCE_MODE_CONTACTS"}
        selected = {"mode": "SOCIAL_AUDIENCE_MODE_SELECTED", "userIds": ["9"]}
        daily_id, post_id = "41", "53"
        caption = {"text": "📷 hi", "entities": [{"type": "ENTITY_TYPE_BOLD", "offset": 3, "length": 2}]}
        daily = {"dailyId": daily_id, "authorId": "8", "revision": "2", "seen": True,
                 "media": {"fileId": photo["photo"]["fileId"], "photo": {"width": 32, "height": 32}},
                 "publishedAt": "2026-01-01T09:04:00Z", "expiresAt": "2026-01-02T09:04:00Z"}
        post = {"postId": post_id, "authorId": "8", "revision": "1", "media": [daily["media"]],
                "publishedAt": daily["publishedAt"], "caption": caption, "audience": selected}
        for name, fixture in (
            ("PublishDailyRequest", {"requestId": key, "media": photo, "caption": caption, "audience": contacts,
                                     "alsoPublishPost": True, "postAudience": selected}),
            ("PublishDailyResponse", {"dailyId": daily_id, "postId": post_id, "updates": [
                {"daily_changed": {"daily": dict(daily, caption=caption, audience=contacts)}},
                {"post_changed": {"post": post}}]}),
            ("PublishPostRequest", {"requestId": key, "media": [video, photo], "audience": selected}),
            ("ListDailyArchiveResponse", {"dailies": [daily], "nextPageToken": "opaque"}),
            ("SaveDailyAsPostRequest", {"dailyId": daily_id, "requestId": key}),
            ("SaveDailyAsPostResponse", {"postId": post_id}),
            ("EditDailyRequest", {"dailyId": daily_id, "requestId": key, "caption": {}}),
            ("SetPostLikeRequest", {"postId": post_id, "requestId": key, "liked": False}),
            ("GetPostResponse", {"post": dict(post, likedByMe=True, likeCount="1", revision="2")}),
        ):
            with self.subTest(name=name):
                self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_ring_and_private_reply(self):
        available = {"userId": "9", "hasActiveDailies": True, "nextExpiryAt": "2026-01-02T09:04:00Z"}
        for name, fixture in (
            ("BatchGetDailyAvailabilityResponse", {"availability": [available, {"userId": "10"}]}),
            ("ListDailyFeedResponse", {"authors": [dict(available, hasUnseenDailies=True)]}),
            ("SendMessageRequest", {"target": {"userId": "9"}, "message": "Where was this?",
                                    "idempotencyKey": "-7", "replyTo": {"dailyId": "41"}}),
            ("MessageReplyHeader", {"dailyId": "41"}),
        ):
            self.assertEqual(fixture, self.round_trip(fixture, name))

    def test_pre_social_reader_keeps_known_update_siblings(self):
        old = self.image_path.with_name("before-social.json")
        files.run_buf("build", ".git#ref=644c529f3c9e18a5552ce5550ed157493a124707", "--exclude-source-info",
                      "--as-file-descriptor-set", "-o", str(old))
        known = {"dialog_changed": {"target": {"userId": "9"}}}
        wire = self.encode({"updates": [known, {"daily_removed": {"dailyId": "41", "revision": "3"}}, known]},
                           "SendMessageResponse")
        result = self.convert(wire, "SendMessageResponse", "binpb", "json", image_path=old)
        self.assertEqual({"updates": [known, {}, known]}, json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
