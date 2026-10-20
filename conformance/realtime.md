# Batched realtime conformance obligations

Applies to the application binding in [REALTIME.md](../REALTIME.md), not the
frozen legacy JSON WebSocket or Syntra core. This is a specification of expected
behavior, not a claim that a server/client implementation has passed these cases.

## Executable schema and codec checks

Run from the repository root with Python 3.9+ and Buf 1.59:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s conformance -p 'test_*.py' -v
buf format -d
buf lint
buf build
buf breaking --against '.git#branch=main'
```

`test_realtime_schema.py` uses standard-library subprocesses and local Buf images,
not generated SDKs or network dependencies. It compares all published message,
enum and service descriptors with local `main`, pins new notification/batch/event
tags, proves no realtime gRPC service or duplicate transport operations were added,
and exercises typed binary round trips. Images live in an external temporary
directory and are deleted on completion; no bindings are generated in this repo.

Round trips preserve optional absent/zero heads, 64-bit values above JavaScript's
exact integer range, signed random IDs, Unicode public content and full batches.
Ill-typed JSON values and conflicting JSON oneof selections fail conversion.
Buf 1.59 may silently discard unknown JSON keys/symbolic enums; numeric proto3
enums are open. Tests explicitly demonstrate that successful conversion, including
an empty notification or semantically invalid batch, is NOT application validation.
ProtoJSON is test input/output only, not this binding's wire encoding.

## Runtime obligations (not executable in this schema-only repository)

Server and client implementations MUST add deterministic tests for the cases
below. Test results from descriptor checks MUST NOT be reported as runtime
conformance. Authorization requires actual authority integration, not trusted
client metadata; persistence/replay proof requires the owning service's durable
store, not just in-memory event fixtures.

| ID | Case | Required result |
| --- | --- | --- |
| APP-001 | SubscribeBatched with valid protobuf request | Exactly one terminal success/error, using Syntra result correlation; no application hello/ready. Success alone does not prove replay completion. |
| APP-002 | Existing experimental Subscribe method | Keeps its old format; is never treated as SubscribeBatched or guessed by decoding success. |
| APP-003 | Second subscription or mixed binding on one socket | Explicit failure before additional watches; unrelated RPC semantics unchanged. |
| APP-004 | Notification with batch, presence, or reset kind | Dispatch only by `RealtimeNotification.kind`. No bare-type or JSON fallback. |
| APP-005 | Empty/unrecognized notification kind | Stop application without checkpoint progress; no successful decode implies validity. |
| APP-006 | Unset/unknown event kind, enum zero, unknown enum, or enum/kind mismatch | Reject the whole batch without applying a prefix or checkpoint. |
| APP-007 | Snapshot plus position, optionally preceded by user then chat primers | Accept 2..4 events after complete validation. Both primers and each individual primer are valid combinations. |
| APP-008 | Sender-only failed message plus position, with optional primers | Same complete-batch rule; all companions remain sender-only and expose no admission reason. |
| APP-009 | Singleton redaction | Accept only stream/cursor/redacted variant; no UUID, timestamp, source markers or message identity/content. It is not an eviction receipt. |
| APP-010 | Singleton dialog read invalidation | Refetch required authoritative state before checkpointing. Crash must not discard unfinished refresh work. |
| APP-011 | Zero events, five events, primer-only, missing position, repeated primary/primer, wrong order, mixed primary/invalidation | Reject whole batch; no best-effort prefix. |
| APP-012 | Mismatched member stream/cursor/UUID, or `final_cursor` differs from any member | Reject whole batch. Redaction is the sole identity-free singleton exception. |
| APP-013 | Primer/position conversation differs from the message, sender primer differs from sender, or invalid order/timestamp/source marker | Reject whole batch. Order is exactly 40 decimal digits; it is not a global sequence. |
| APP-014 | Duplicate complete checkpoint | No reapplication or second checkpoint commit; a known conflicting UUID requires recovery. Do not deduplicate individual members by their shared UUID. |
| APP-015 | Replayed source update has different current hydration or primer selection | Do not require byte-identical replay. Check complete-batch identity within principal/stream/history scope. |
| APP-016 | Next cursor, missing cursor, older cursor, exhausted numeric range | Apply only the next complete batch; gaps/rollback stop progress; no unsigned wraparound or backward checkpoint. |
| APP-017 | `after = floor-1`, `floor`, `floor+1`, `head`, `head+1` | Below floor expires; equality is valid; future head is invalid. Successful pages never imply skipping to head. |
| APP-018 | Absent/zero cursor with nonzero replay floor | Reset/OutOfRange, never silently start at live head or oldest retained event. |
| APP-019 | Commit after final replay snapshot, before next live poll | Eventually deliver from durable log or explicitly reset if retention/scope invalidates continuity; no silent gap. |
| APP-020 | Crash before, during, after batch application/checkpoint transaction | Restart sees either the old checkpoint with retryable batch or the complete new effects/checkpoint, never a partially committed group. |
| APP-021 | Oversized or unqueueable batch; interrupted WebSocket | Explicit failure/close; no splitting into partial notifications or claiming client commit. Reconnect uses last fully applied cursor. |
| APP-022 | Client/server restart or independent devices | Fresh handshake/authentication, independently persisted per-device checkpoints, stable durable identities; connection IDs never resume state. |
| APP-023 | Reset with head absent, zero, or positive | Stop that sequence; head is not a snapshot fence. No resubscribe-at-head/zero shortcut. Unrelated RPCs can remain usable. |
| APP-024 | Snapshot/checkpoint contract unavailable | Report reset recovery unavailable; do not invent a fence from GetDialogs/GetHistory pages and independently sampled head. |
| APP-025 | Same pending send retried after lost result | Preserve exact request and scoped random ID; deduplication is application-owned, not request-ID owned. Conflicting payload fails. |
| APP-026 | Another user stream, unauthorized room, removal during replay | No private disclosure; room authority rechecked during backlog, not only at subscription time. |
| APP-027 | Room rejoin/history scope changed while disconnected | Require independently proven scope/snapshot continuity; numeric cursor alone cannot authorize or rebuild old cache. |
| APP-028 | Recipient/other room viewer receives sender correlation/failure | Reject disclosure, including companion primers/position for a failed attempt. |
| APP-029 | Unknown/hidden presence, disconnect, or reset | Presence retracts; never infer offline from unknown or use its revision as a durable cursor. |
| APP-030 | Unsupported new binding during rollout/rollback | Explicit unsupported-method failure; no decoder downgrade, cursor overwrite, source identity deletion or Kafka group reset. |

The current schema does not provide snapshot fencing, privacy-safe cache eviction,
room scope continuity, source-to-projector completeness or a runtime validator.
Those are separate release gates. No case here attests exactly-once delivery,
Syntra session resumption, publication success or deployed compatibility.
