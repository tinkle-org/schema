"""Analytics wire surface and codec checks; policy enforcement belongs to servers."""

import unittest

import test_files_schema as files


SERVICE = "tinkle/v1/analytics.proto"
TYPES = "tinkle/v1/analytics_types.proto"
DOMAINS = (
    ("Channel", "channel_id", ("subscribers", "messages")),
    ("Group", "group_id", ("members", "messages")),
    ("Message", "message", ("reactions",)),
    ("Daily", "daily_id", ("publications",)),
    ("Post", "post_id", ("likes",)),
    ("Poll", "poll", ("voters",)),
)


class AnalyticsSchemaTests(files.BufSchemaTestCase):
    def test_ordered_unary_reads(self):
        methods = ["GetAnalyticsAccess", *(f"Get{d}Stats" for d, _, _ in DOMAINS), "GetAnalyticsSeries"]
        path, service = self.declarations["service"]["tinkle.v1.AnalyticsService"]
        self.assertEqual(SERVICE, path)
        self.assertEqual([{"name": m, "inputType": f".tinkle.v1.{m}Request",
                           "outputType": f".tinkle.v1.{m}Response"} for m in methods], service["method"])

    def test_closed_subjects_and_disclosure(self):
        subjects = []
        for tag, (domain, key, metrics) in enumerate(DOMAINS, 1):
            kind, ref = ("INT64", "") if key.endswith("_id") else ("MESSAGE", "AnalyticsMessageRef")
            subjects.append((key, tag, kind, ref, False, False))
            self.assert_fields(f"Get{domain}StatsRequest", [
                (key, 1, kind, ref, False, False), ("period", 2, "MESSAGE", "AnalyticsPeriod", False, False)], SERVICE)
            self.assert_fields(f"Get{domain}StatsResponse", [
                ("coverage", 1, "MESSAGE", "AnalyticsPeriod", False, False),
                ("stats", 2, "MESSAGE", domain + "Stats", False, False),
                ("freshness", 3, "MESSAGE", "AnalyticsFreshness", False, False)], SERVICE)
            self.assert_fields(domain + "Stats", [(m, i, "MESSAGE", "AnalyticsCount", False, False)
                                                  for i, m in enumerate(metrics, 1)], TYPES)
        self.assert_fields("AnalyticsSubject", subjects, TYPES)
        self.assert_oneof("AnalyticsSubject", "subject", [key for _, key, _ in DOMAINS])
        self.assert_fields("AnalyticsMessageRef", [("target", 1, "MESSAGE", "RoomQueryTarget", False, False),
                                                   ("message_id", 2, "INT64", "", False, False)], TYPES)
        self.assert_enum_values("AnalyticsMetric", ["ANALYTICS_METRIC_" + name for name in (
            "UNSPECIFIED", "SUBSCRIBERS", "MESSAGES", "MEMBERS", "REACTIONS", "PUBLICATIONS", "LIKES", "VOTERS")], TYPES)
        self.assert_fields("GetAnalyticsAccessRequest", [("subject", 1, "MESSAGE", "AnalyticsSubject", False, False)], SERVICE)
        self.assert_fields("GetAnalyticsAccessResponse", [("metrics", 1, "ENUM", "AnalyticsMetric", True, False),
                           ("granularities", 2, "ENUM", "AnalyticsGranularity", True, False),
                           ("supported_period", 3, "MESSAGE", "AnalyticsPeriod", False, False)], SERVICE)

    def test_room_namespaces_and_availability(self):
        self.assert_oneof("RoomQueryTarget", "room", ["chat_id", "channel_id"])
        for arm in ("message", "poll"):
            fixtures = [{arm: {"target": {key: "42"}, "messageId": "7"}} for key in ("chatId", "channelId")]
            self.assertNotEqual(*(self.encode(f, "AnalyticsSubject") for f in fixtures))
            for f in fixtures:
                self.assertEqual(f, self.round_trip(f, "AnalyticsSubject"))
        self.assert_enum_values("AnalyticsGranularity", ["ANALYTICS_GRANULARITY_UNSPECIFIED", "ANALYTICS_GRANULARITY_DAY"], TYPES)
        self.assert_fields("AnalyticsFreshness", [(k, i, "MESSAGE", ".google.protobuf.Timestamp", False, False)
                           for i, k in enumerate(("generated_at", "data_through"), 1)], TYPES)
        access = {"metrics": ["ANALYTICS_METRIC_LIKES"], "granularities": ["ANALYTICS_GRANULARITY_DAY"],
                  "supportedPeriod": {"start": "2026-11-01T00:00:00Z", "end": "2026-11-26T13:10:00Z"}}
        self.assertEqual(access, self.round_trip(access, "GetAnalyticsAccessResponse"))

    def test_zero_is_not_withheld_or_missing(self):
        self.assert_oneof("AnalyticsCount", "result", ["value", "withheld"], TYPES)
        for state in ({"value": "0"}, {"withheld": {}}, {}):
            with self.subTest(state=state):
                self.assertEqual(state, self.round_trip(state, "AnalyticsCount"))
        self.assertNotEqual(0, self.convert({"value": "0", "withheld": {}}, "AnalyticsCount", check=False).returncode)

    def test_series_query_and_deferred_result(self):
        self.assert_fields("GetAnalyticsSeriesRequest", [
            ("query", 1, "MESSAGE", "AnalyticsSeriesQuery", False, False),
            ("pending_token", 2, "BYTES", "", False, False)], SERVICE)
        self.assert_oneof("GetAnalyticsSeriesRequest", "source", ["query", "pending_token"], SERVICE)
        self.assert_fields("GetAnalyticsSeriesResponse", [
            ("series", 1, "MESSAGE", "AnalyticsSeries", False, False),
            ("pending", 2, "MESSAGE", "AnalyticsPending", False, False),
            ("unavailable", 3, "ENUM", "AnalyticsSeriesUnavailableReason", False, False),
            ("freshness", 4, "MESSAGE", "AnalyticsFreshness", False, False)], SERVICE)
        self.assert_oneof("GetAnalyticsSeriesResponse", "result", ["series", "pending", "unavailable"], SERVICE)
        self.assert_fields("AnalyticsSeries", [
            ("coverage", 1, "MESSAGE", "AnalyticsPeriod", False, False),
            ("buckets", 2, "MESSAGE", "AnalyticsBucket", True, False)], TYPES)
        self.assert_fields("AnalyticsBucket", [
            ("period", 1, "MESSAGE", "AnalyticsPeriod", False, False),
            ("count", 2, "MESSAGE", "AnalyticsCount", False, False)], TYPES)
        self.assert_fields("AnalyticsPending", [
            ("token", 1, "BYTES", "", False, False),
            ("expires_at", 2, "MESSAGE", ".google.protobuf.Timestamp", False, False),
            ("retry_after_seconds", 3, "UINT32", "", False, False)], TYPES)
        self.assert_enum_values("AnalyticsSeriesUnavailableReason", ["ANALYTICS_SERIES_UNAVAILABLE_REASON_" + reason
                                for reason in ("UNSPECIFIED", "WITHHELD", "NO_COVERAGE")], TYPES)
        self.assert_fields("AnalyticsSeriesQuery", [
            ("subject", 1, "MESSAGE", "AnalyticsSubject", False, False), ("metric", 2, "ENUM", "AnalyticsMetric", False, False),
            ("period", 3, "MESSAGE", "AnalyticsPeriod", False, False),
            ("granularity", 4, "ENUM", "AnalyticsGranularity", False, True)], TYPES)
        requested = {"start": "2026-11-26T00:00:00Z", "end": "2026-11-27T00:00:00Z"}
        covered = dict(requested, end="2026-11-26T13:10:00Z")
        # Actual end precedes both timestamps; none is a proxy for the other.
        freshness = {"dataThrough": "2026-11-26T14:00:00Z", "generatedAt": "2026-11-26T15:00:00Z"}
        query = {"subject": {"postId": "9007199254740993"}, "metric": "ANALYTICS_METRIC_LIKES", "period": requested,
                 "granularity": "ANALYTICS_GRANULARITY_DAY"}
        for name, fixture in (
            ("GetAnalyticsSeriesRequest", {"query": query}),
            ("GetAnalyticsSeriesRequest", {"pendingToken": "AQID"}),
            ("GetAnalyticsSeriesResponse", {"pending": {"token": "AQID", "expiresAt": "2026-11-26T13:25:00Z", "retryAfterSeconds": 5}}),
            ("GetAnalyticsSeriesResponse", {"series": {"coverage": covered, "buckets": [{"period": covered, "count": {"value": "0"}}]}, "freshness": freshness}),
            ("GetAnalyticsSeriesResponse", {"unavailable": "ANALYTICS_SERIES_UNAVAILABLE_REASON_NO_COVERAGE", "freshness": freshness}),
            ("GetAnalyticsSeriesResponse", {"unavailable": "ANALYTICS_SERIES_UNAVAILABLE_REASON_WITHHELD", "freshness": {"generatedAt": freshness["generatedAt"]}}),
            ("GetPostStatsResponse", {"coverage": covered, "stats": {"likes": {"withheld": {}}}, "freshness": freshness}),
        ):
            with self.subTest(name=name, fixture=fixture):
                self.assertEqual(fixture, self.round_trip(fixture, name))
        self.assertNotEqual(0, self.convert({"query": query, "pendingToken": "AQID"}, "GetAnalyticsSeriesRequest", check=False).returncode)


if __name__ == "__main__":
    unittest.main()
