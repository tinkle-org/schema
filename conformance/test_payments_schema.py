"""Payments wire contracts only. Store trust, atomicity and races need release tests."""

import json

from test_files_schema import BufSchemaTestCase


RPC = "tinkle/v1/payments.proto"
TYPES = "tinkle/v1/payment_types.proto"
LEAVES = "tinkle/v1/payment_updates.proto"
METHODS = (
    "CreateInvoice GetInvoice GetPaymentForm ValidatePaymentDetails SubmitPayment "
    "GetPayment ListPayments GetPaymentReceipt CreateRefund GetRefund "
    "VerifyStorePurchase GetMyEntitlements"
).split()


class PaymentsSchemaTests(BufSchemaTestCase):
    def test_rpc_order_and_direct_updates(self):
        path, service = self.declarations["service"]["tinkle.v1.PaymentsService"]
        self.assertEqual(RPC, path)
        self.assertEqual(service["method"], [
            {"name": m, "inputType": f".tinkle.v1.{m}Request", "outputType": f".tinkle.v1.{m}Response"}
            for m in METHODS
        ])
        update_tags = {"CreateInvoice": 3, "SubmitPayment": 2, "CreateRefund": 2, "VerifyStorePurchase": 3}
        for m in METHODS:
            fields = self.descriptor(m + "Response", RPC)["field"]
            updates = [f for f in fields if f["name"] == "updates" or f.get("typeName") == ".tinkle.v1.Update"]
            self.assertEqual(updates, [] if m not in update_tags else [{
                "name": "updates", "jsonName": "updates", "number": update_tags[m],
                "type": "TYPE_MESSAGE", "label": "LABEL_REPEATED", "typeName": ".tinkle.v1.Update",
            }], m)

    def test_unions_and_private_projections(self):
        for message, union, members in [
            ("CreateInvoiceRequest", "purpose", ["premium", "other_order_id"]),
            ("PremiumCheckoutRequest", "product", ["apple_product_id", "play_product_id"]),
            ("StorePurchaseIntent", "binding", ["apple_app_account_token", "play_obfuscated_account_id"]),
            ("VerifyStorePurchaseRequest", "evidence", ["apple_signed_transaction", "play_purchase_token"]),
            ("StorePurchaseResult", "outcome", ["pending", "verified_payment", "not_completed"]),
            ("GetPaymentRequest", "lookup", ["payment_id", "submit_payment_request_id", "verify_store_purchase_request_id"]),
            ("GetPaymentResponse", "outcome", ["payment", "verification"]),
            ("GetRefundRequest", "lookup", ["refund_id", "create_refund_request_id"]),
        ]:
            self.assert_oneof(message, union, members)
        # Pin the entire safe projection graph, not a denylist of likely secret names.
        # Each entry pins field order/tag, type and explicit (?)/repeated (*) presence.
        shapes = {
            "Invoice": "invoice_id:string origin:PaymentOrigin environment:PaymentEnvironment product_id:string amount:PaymentAmount expires_at:int64",
            "PaymentAmount": "currency:string minor_units:int64",
            "Payment": "payment_id:string origin:PaymentOrigin environment:PaymentEnvironment product_id:string amount:PaymentAmount state:PaymentState revision:uint64 invoice_id:?string billing_source_id:?string refund_id:?string",
            "Refund": "refund_id:string payment_id:string state:RefundState revision:uint64",
            "MyEntitlements": "environment:PaymentEnvironment revision:uint64 premium_until:?int64 billing_sources:*PremiumBillingSource checkout_unresolved:bool",
            "PremiumBillingSource": "billing_source_id:string origin:PaymentOrigin product_id:string state:PremiumSourceState covered_until:?int64 auto_renews:?bool",
            "PaymentChanged": "payment_id:string revision:uint64",
            "RefundChanged": "refund_id:string revision:uint64",
            "MyEntitlementsChanged": "revision:uint64",
            "GetPaymentReceiptResponse": "payment:Payment settled_at:int64",
            "GetPaymentReceiptRequest": "payment_id:string",
            "GetInvoiceRequest": "invoice_id:string",
            "GetInvoiceResponse": "invoice:Invoice",
            "GetPaymentFormRequest": "invoice_id:string",
            "GetPaymentFormResponse": "form_id:string provider:string expires_at:int64",
            "ValidatePaymentDetailsRequest": "form_id:string provider_token:bytes",
            "ValidatePaymentDetailsResponse": "validated_details_id:string",
            "SubmitPaymentResponse": "payment:Payment updates:*Update",
            "GetPaymentRequest": "payment_id:string submit_payment_request_id:string verify_store_purchase_request_id:string",
            "GetPaymentResponse": "payment:Payment verification:StorePurchaseResult entitlements:MyEntitlements",
            "ListPaymentsRequest": "limit:uint32 cursor:bytes",
            "ListPaymentsResponse": "payments:*Payment next_cursor:bytes",
            "CreateRefundRequest": "request_id:string payment_id:string",
            "CreateRefundResponse": "refund:Refund updates:*Update",
            "GetRefundRequest": "refund_id:string create_refund_request_id:string",
            "GetRefundResponse": "refund:Refund",
            "GetMyEntitlementsRequest": "",
            "GetMyEntitlementsResponse": "entitlements:MyEntitlements checkout_fence:bytes",
            "CreateInvoiceRequest": "request_id:string premium:PremiumCheckoutRequest other_order_id:string",
            "CreateInvoiceResponse": "invoice:Invoice store_intent:StorePurchaseIntent updates:*Update",
            "PremiumCheckoutRequest": "checkout_fence:bytes apple_product_id:string play_product_id:string",
            "StorePurchaseIntent": "intent_id:string expires_at:int64 apple_app_account_token:string play_obfuscated_account_id:string",
            "SubmitPaymentRequest": "request_id:string invoice_id:string validated_details_id:string",
            "VerifyStorePurchaseRequest": "request_id:string intent_id:?string apple_signed_transaction:string play_purchase_token:string",
            "VerifyStorePurchaseResponse": "result:StorePurchaseResult entitlements:MyEntitlements updates:*Update",
            "StorePurchaseResult": "pending:StorePurchasePending verified_payment:Payment not_completed:StorePurchaseNotCompleted",
            "StorePurchasePending": "",
            "StorePurchaseNotCompleted": "",
        }
        for name, spec in shapes.items():
            desc = self.descriptor(name)
            actual = []
            for tag, field in enumerate(desc.get("field", []), 1):
                self.assertEqual(field["number"], tag, name)
                kind = field.get("typeName", field["type"].removeprefix("TYPE_").lower()).removeprefix(".tinkle.v1.")
                prefix = "*" if field["label"] == "LABEL_REPEATED" else "?" if field.get("proto3Optional") else ""
                actual.append(f"{field['name']}:{prefix}{kind}")
            self.assertEqual(spec.split(), actual, name)
        files = {f["name"]: f for f in json.loads(self.image_path.read_bytes())["file"]}
        for path in (LEAVES, TYPES):
            self.assertFalse(files[path].get("dependency"))
            self.assertFalse(files[path].get("service"))

    def test_checkout_and_restore_codec(self):
        for product, binding, proof in [
            ("appleProductId", "appleAppAccountToken", "appleSignedTransaction"),
            ("playProductId", "playObfuscatedAccountId", "playPurchaseToken"),
        ]:
            fixtures = [
                ("CreateInvoiceRequest", {"requestId": "request", "premium": {"checkoutFence": "AAE=", product: "premium"}}),
                ("CreateInvoiceResponse", {"storeIntent": {"intentId": "intent", "expiresAt": "2000000000", binding: "binding"}}),
                ("VerifyStorePurchaseRequest", {"requestId": "e5ceed35-344e-4532-b219-9bf4993c2d23", "intentId": "intent", proof: "fixture"}),
                ("VerifyStorePurchaseRequest", {"requestId": "8bb3d4d0-141a-4577-933f-ed5fdb7b76b3", proof: "fixture"}),
            ]
            for name, fixture in fixtures:
                self.assertEqual(fixture, self.round_trip(fixture, name))
        for name, bad in [
            ("VerifyStorePurchaseRequest", {"appleSignedTransaction": "a", "playPurchaseToken": "b"}),
            ("CreateInvoiceRequest", {"premium": {}, "otherOrderId": "order"}),
            ("StorePurchaseResult", {"pending": {}, "verifiedPayment": {}}),
            ("GetPaymentResponse", {"payment": {}, "verification": {"pending": {}}}),
            ("GetPaymentRequest", {"submitPaymentRequestId": "key", "verifyStorePurchaseRequestId": "key"}),
            ("GetRefundRequest", {"refundId": "refund", "createRefundRequestId": "key"}),
        ]:
            self.assertNotEqual(0, self.convert(bad, name, check=False).returncode, name)

    def test_both_sources_and_renewal_receipts_codec(self):
        sources = [
            {"origin": "PAYMENT_ORIGIN_APPLE", "billingSourceId": "a", "coveredUntil": "2000000000",
             "state": "PREMIUM_SOURCE_STATE_COVERED", "autoRenews": False},
            {"origin": "PAYMENT_ORIGIN_PLAY", "billingSourceId": "p", "coveredUntil": "2100000000",
             "state": "PREMIUM_SOURCE_STATE_COVERED"},
        ]
        current = {"environment": "PAYMENT_ENVIRONMENT_LAB", "revision": "9007199254740993",
                   "billingSources": sources, "premiumUntil": "2100000000"}
        self.assertEqual({"entitlements": current}, self.round_trip({"entitlements": current}, "GetMyEntitlementsResponse"))
        payments = [{"paymentId": key, "billingSourceId": "p", "origin": "PAYMENT_ORIGIN_PLAY",
                     "state": "PAYMENT_STATE_SUCCEEDED"} for key in ("order-2", "order-1")]
        page = {"payments": payments, "nextCursor": "/w=="}
        self.assertEqual(page, self.round_trip(page, "ListPaymentsResponse"))
        refund = {"refund": {"refundId": "refund", "paymentId": "order-1", "state": "REFUND_STATE_SUCCEEDED"}}
        self.assertEqual(refund, self.round_trip(refund, "GetRefundResponse"))

    def test_keyed_recovery_and_original_settlement_codec(self):
        key = "e5ceed35-344e-4532-b219-9bf4993c2d23"
        for message, lookup in [
            ("GetPaymentRequest", {"submitPaymentRequestId": key}),
            ("GetPaymentRequest", {"verifyStorePurchaseRequestId": key}),
            ("GetPaymentRequest", {"paymentId": "order-A"}),
            ("GetRefundRequest", {"createRefundRequestId": key}),
            ("GetRefundRequest", {"refundId": "refund-A"}),
        ]:
            self.assertEqual(lookup, self.round_trip(lookup, message))

        self.assert_enum_values("PaymentState", ["PAYMENT_STATE_" + s for s in
                                ("UNSPECIFIED", "PENDING", "SUCCEEDED", "FAILED")], TYPES)
        settled = {"paymentId": "order-A", "origin": "PAYMENT_ORIGIN_PLAY", "state": "PAYMENT_STATE_SUCCEEDED",
                   "refundId": "refund-A", "amount": {"currency": "USD", "minorUnits": "999"}}
        revoked = {"environment": "PAYMENT_ENVIRONMENT_LAB", "revision": "17", "billingSources": [
            {"billingSourceId": "p", "origin": "PAYMENT_ORIGIN_PLAY", "state": "PREMIUM_SOURCE_STATE_REVOKED"}]}
        for result in ({"pending": {}}, {"verifiedPayment": settled}, {"notCompleted": {}}):
            for message, field in (("VerifyStorePurchaseResponse", "result"), ("GetPaymentResponse", "verification")):
                body = {field: result, "entitlements": revoked}
                self.assertEqual(body, self.round_trip(body, message))
        receipt = {"payment": settled, "settledAt": "2000000000"}
        self.assertEqual(receipt, self.round_trip(receipt, "GetPaymentReceiptResponse"))
        for message, fields in (("PaymentChanged", {"paymentId": "order-A"}),
                                ("RefundChanged", {"refundId": "refund-A"}), ("MyEntitlementsChanged", {})):
            hint = dict(fields, revision="9007199254740993")
            self.assertEqual(hint, self.round_trip(hint, message))
