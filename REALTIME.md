# Tinkle realtime application binding

Status: feature-branch contract for review and implementation. This document does
not establish BSR publication, server support, or end-to-end synchronization
readiness. The words MUST, MUST NOT, and SHOULD describe requirements for an
implementation claiming this binding. Schemas live in `tinkle/v1/realtime.proto`.

## 1. Ownership and transport boundary

Protobuf defines application data independently of gRPC. Syntra owns the outer
`Frame`, protocol version, handshake, authenticated connection binding,
connection ID, request correlation, generic RPC errors, cancellation and transport
liveness. Tinkle MUST NOT reproduce those operations in its notification payload.

Tinkle owns subscription interests, stream-local checkpoints, complete update
batches, presence data and synchronization resets. No Syntra schema is imported
or modified. `RealtimeNotification` is an application discriminator inside
`syntra.v1.Notification.payload`, not another transport frame.

The published `RealtimeFrame`, `RealtimeReady`, `RealtimeUpdate`,
`RealtimeConnectControl` and `RealtimeError` remain frozen for the legacy
`/connection/websocket` JSON binding. They MUST NOT be used as framing for this
binding. `RealtimeOnline` and `RealtimeResetRequired` are reusable application
data, carried only through the new notification discriminator here.

## 2. Explicit method binding and migration

| Syntra method | Request payload | Successful result payload |
| --- | --- | --- |
| `/tinkle.v1.Realtime/SubscribeBatched` | `SubscribeRequest` | `SubscribeResponse` |
| `/tinkle.v1.Realtime/UnsubscribeBatched` | `UnsubscribeRequest` | `UnsubscribeResponse` |

These are opaque Syntra dispatcher identifiers, not a declared gRPC service or a
new gRPC endpoint. Failures use Syntra `RpcResult.error`, never bytes disguised
as a successful result. The existing gRPC application services are unchanged.

Method identity selects the application encoding BEFORE payload decoding. A
server MUST NOT reinterpret the existing experimental
`/tinkle.v1.Realtime/Subscribe` or `/tinkle.v1.RealtimeService/Subscribe` methods as
this binding. Those methods keep their existing experimental formats; they are
not aliases for SubscribeBatched. Unknown-method failure is not permission to
try another decoder on the same bytes.

A connection MUST select at most one realtime binding. A second Subscribe or a
request to mix experimental and batched bindings MUST fail before opening more
watches. Subscribe success confirms registered interests, not replay completion
or a source snapshot. No application ready/hello notification follows it.
Implementations MUST handle notifications and unrelated RPC results independently;
Syntra correlation determines which call a result completes.

After selecting this binding, every Tinkle realtime notification MUST contain one
serialized `RealtimeNotification`, selecting exactly one known `kind`. Bare
events, bare batches, bare presence/reset messages, JSON and trial decoding are
not allowed. Unsupported kinds or event variants MUST stop application of the
affected binding without checkpoint advancement. Generated protobuf decoding
alone does not enforce these semantic requirements. This binding adds no custom
wire parser; ordinary protobuf duplicate-field/oneof decoding rules still apply.

## 3. Authorization and bounded interests

The own-user stream MUST derive from the verified principal. A cursor is not
authority, and a request MUST NOT select another private user. Room access and
history visibility MUST be checked against the room authority before disclosure,
including replay and subsequent polls/deliveries. Reconnect authenticates again.

At most 15 distinct positive room IDs and 100 distinct positive presence IDs are
allowed, subject to lower deployment limits. IDs fit positive signed 64-bit
storage values. Unsubscribe releases optional room/presence interests, never the
own-user watch. Unsupported release operations MUST fail explicitly. Presence
policy remains authoritative; unknown/hidden state retracts to `known=false`,
`online=false`, revision zero and does not prove offline.

Implementations MUST bound frame bytes, queue bytes/count and active watches.
A complete batch MUST fit the existing Syntra/host limits including its wrapper.
An oversized or unqueueable batch MUST fail explicitly without being split into
partial durable notifications or claiming application progress. No limit is
increased by this binding.

## 4. Complete durable batches

A `RealtimeNotification.batch` contains exactly one source update projected into
one authorized stream. It has 1..4 ordered events. Every member MUST share
`batch.stream`, the same positive cursor equal to `batch.final_cursor`, and the
same canonical lowercase nonzero source UUID, except for singleton redactions.
Every event enum MUST agree with its selected payload variant.

Allowed event sequences are precisely:

```text
[user_hydration?] [chat_hydration?] message_snapshot chat_position
[user_hydration?] [chat_hydration?] message_send_failed chat_position
update_redacted
dialog_read_advanced
```

Each optional primer occurs at most once and precedes its primary message;
position follows that message. Position and chat-primer keys MUST refer to that
message's conversation, and a user primer MUST identify its sender. There is one
primary event, not multiple messages, primer-only batches or mixed invalidations.
Primers are ID-only hydration hints, not complete entities. Sender-only failure
and `random_id` disclosure rules apply to all companion events too.

Present source sequence/revision markers MUST be nonnegative, and timestamps MUST
be valid protobuf timestamps. The position `order` is the concatenation of the
cursor and source sequence as zero-padded 20-digit unsigned decimal strings
(40 ASCII digits total); absent source sequence means zero. It is a presentation
hint within this stream, not a global order or another checkpoint.

Redaction is a singleton: source UUID, timestamps, source markers and message
identity/content MUST be absent. Only stream/cursor and the redacted variant are
disclosed. It is not an identifying deletion receipt. A message snapshot MUST
contain only the public `Message` projection, never internal policy/journal bytes.
Snapshots are hydrated current state; source sequence/revision does not version
the returned body. A replay can change content or omit/repeat primers while
preserving the same durable checkpoint identity.

A client MUST validate the complete batch before exposing any effects. It MUST
atomically commit all required application effects and the checkpoint, including
message indexes, position and pending-send reconciliation. When an invalidation
requires a refetch, the client MUST complete the required authoritative refresh
before checkpointing; a checkpoint MUST NOT discard pending refresh work on crash.
Failure or crash during application MUST leave the old checkpoint usable. Neither
queue admission, socket write, a pong nor an unrelated result proves this commit.
The server does not observe it: this binding has no application acknowledgment.

## 5. Checkpoints, duplicates and retention

Checkpoint scope is the same authenticated principal, stream and valid history
scope, independent of Syntra connection and request IDs. It survives client and
server connection restarts while history remains retained. Account switches MUST
NOT reuse another account's checkpoint. Presence is ephemeral and is cleared on
disconnect. Neither connection ID nor presence revision is a replay token.

For a complete batch cursor `c` and last fully applied cursor `a`:

| Condition | Required handling |
| --- | --- |
| `c == a` | Duplicate complete batch; do not apply members or advance again. A known conflicting source UUID invalidates continuity. |
| `c < a` | Rollback or old overlap; do not apply as new state or move the checkpoint backward. Without an agreed overlap procedure, stop and recover. |
| `c > a` and `c - a == 1` | Apply the complete next batch, then commit its checkpoint atomically. |
| `c > a` and `c - a > 1` | Missing update; stop, retain the old checkpoint and recover. Never skip to `c` or head. |

Deduplicate whole batches by `(stream,cursor)` within principal/history scope,
not individual members by shared UUID. UUID identifies the source update, not a
global ordering position or permission grant. Do not require byte-identical
replay, or use text/time equality as message identity. Cursor subtraction is used
only after an ordering comparison; overflow MUST NOT create a false successor.

Supported cursors/heads are 0..9223372036854775807; delivered cursors are positive.
Absent subscription cursor means zero, exactly. Zero is a request after position
zero, not "start live" or permission to skip a retained prefix. With replay floor
equal to the largest removed cursor, `after < floor` expires, equality is valid,
and `after > head` is invalid. These fail explicitly with reset or OutOfRange;
retention is deployment-defined and MUST NOT be assumed infinite. Cursor order
is per stream, never global, and differs from message acceptance/source ordering.

There is no automatic exactly-once guarantee or Syntra session resumption.
Retained replay may repeat batches after explicit authenticated resubscription.
Watches and in-flight RPC state do not survive the old connection. A server's
local send/enqueue position MUST NOT replace the client's applied checkpoint.

## 6. Reset, snapshots and send recovery

Reset is terminal for one stream's current sequence, not a Syntra connection
handshake/error. A client MUST stop applying it and obtain a proven consistent
snapshot/checkpoint before establishing a replacement watch. The optional reset
head is diagnostic progress only, not a snapshot fence. A client MUST NOT sample
head, fetch unrelated pages, then silently resume at that head or zero.

**No snapshot/fence RPC is defined by this change.** Existing GetDialogs and
GetHistory are authoritative reads but supply no source-to-updates fence or
cross-page consistency guarantee. A complete source snapshot, asynchronous
projection fence and race-free watch bootstrap require a separate reviewed
contract and implementation. Until available, reset recovery MUST report itself
unavailable rather than invent continuity. Identity-free redaction likewise
cannot identify stale cached content to evict; privacy-safe reconciliation is a
separate requirement, not solved by advancing the checkpoint.

Clients persist the exact pending SendMessage request and nonzero signed
`random_id` before sending. Lost result means unknown outcome: an application may
retry the unchanged request/key using fresh transport correlation after
reauthentication, with bounded retries/backoff. Syntra request ID does not
deduplicate persistence. The current message journal scopes deduplication to
`(canonical target, authenticated sender, random_id)`; conflicting payloads fail.
Its current no-TTL records are not an indefinite deployment retention promise.
Current room authorization can still prevent disclosure of a prior outcome.

## 7. Publication and remaining integration gates

Legacy schemas and gRPC services MUST retain their published tags and meaning.
The unpublished draft RealtimeService is not added as a gRPC service. The draft
SubscribeResponse connection-ID slot is reserved rather than repurposed. New
application fields stay in Tinkle, never in Syntra core.

Release order: review schema/conformance, publish via the normal main-merge/BSR
workflow, pin the exact generated revision, implement the new dispatch bindings
and validators, then release compatible clients. No schema presence establishes
an implemented endpoint. Old experimental connections continue their old formats;
on rollback, stop the new binding explicitly and keep durable checkpoints, heads
and source identities intact. Do not silently downgrade payload decoding or reset
Kafka groups as a recovery mechanism.

Before advertising full synchronization, separately resolve: source-snapshot
fencing, room leave/rejoin/history-scope continuity, privacy-safe cache eviction,
and actual source-to-projector publication/catch-up. Membership authorization,
mTLS, error sanitization and resource bounds MUST NOT be weakened. Conformance
obligations are listed in `conformance/realtime.md`; schema checks alone cannot
prove delivery, client transaction durability or any of those integration gates.
