# tinkle-proto

Source of truth for the `tinkle.v1` Protobuf contract. The schema is
published to the [Buf Schema Registry](https://buf.build/tinklecorp/tinkle-proto)
(public), which generates and serves **Go** and **Rust** SDKs to
consumers. This repo contains only the proto source and Buf config.

The public `.proto` files are maintained directly here under `tinkle/v1/`.
This repository is the source of truth, not a mirror of the server repository.
Consumers use BSR-generated SDKs; no language-specific generated code is stored here.

## Architecture

```
tinklehq/tinkle-proto/                 ← proto source + Buf config
├── tinkle/v1/*.proto                  authoritative public proto source
├── buf.yaml                           v2 workspace; module is published
│                                      to buf.build/tinklecorp/tinkle-proto
├── buf.lock                           generated
├── LICENSE                            at module root (required for pkg.go.dev)
├── README.md
└── .github/workflows/buf-ci.yaml      bufbuild/buf-action:
                                         build/lint/format/breaking/push
```

No per-language directories, no `buf.gen.yaml`, no generated code in
the tree. The BSR owns the generated Go and Rust artifacts.

```
main (proto source + Buf config)
   │
   ▼  CI: buf push on every merge to main
buf.build/tinklecorp/tinkle-proto (public)
   │
   ▼  consumer reads
go get buf.build/gen/go/tinklecorp/tinkle-proto/{protocolbuffers,grpc}/go
cargo add --registry buf tinklecorp_tinkle-proto_bufbuild_community_tonic-prost
```

## Consuming the bindings

The BSR auto-versions each push. SDK versions are
`{plugin-version}-{module-commit-timestamp}-{module-commit-id}.{plugin-revision}`
(e.g. `v1.36.11-20260617120000-abc123def456.1`). Pin with
`@vX.Y.Z-…`, `@<commit-id>`, or `@<label>`.

### Go

```bash
go get buf.build/gen/go/tinklecorp/tinkle-proto/protocolbuffers/go@latest
go get buf.build/gen/go/tinklecorp/tinkle-proto/grpc/go@latest
```

```go
import (
    tinklev1   "buf.build/gen/go/tinklecorp/tinkle-proto/protocolbuffers/go/tinkle/v1"
    tinklegrpc "buf.build/gen/go/tinklecorp/tinkle-proto/grpc/go/tinkle/v1;tinklev1grpc"
)
```

The two modules must be pinned to the same module commit
(the timestamp and short-id segments) so the message types and the
gRPC stubs stay in sync.

### Rust

Add the `buf` Cargo registry to `.cargo/config.toml`:

```toml
[registries.buf]
index = "sparse+https://buf.build/gen/cargo/"
credential-provider = "cargo:token"
```

Then add the crate:

```bash
cargo add --registry buf tinklecorp_tinkle-proto_bufbuild_community_tonic-prost
```

> **First-`cargo-add` priming.** Rust SDKs are generated eagerly on
> the BSR (Cargo needs a checksum for every version). The first
> `cargo add` against this module triggers the initial generation;
> every subsequent push to `main` produces a new crate version
> automatically.

### Other ecosystems

The BSR also serves TypeScript/JavaScript, Python, Java/Kotlin, and
Swift SDKs against the same module — see
[buf.build/tinklecorp/tinkle-proto/sdks](https://buf.build/tinklecorp/tinkle-proto/sdks).

## CI

`.github/workflows/buf-ci.yaml` runs `bufbuild/buf-action@v1`. On
every PR to `main` it runs `build`, `lint`, `format`, and `breaking`,
and posts a summary comment. On every push to `main` it also runs
`buf push`, which publishes the named module to the BSR. On a branch
delete it archives the matching BSR label.

### Required secret

`BUF_TOKEN` — a BSR API token for the `tinklecorp` org, configured
as a repository secret (Settings → Secrets and variables → Actions).
The action auto-creates the BSR repo on first push; `push_create_visibility: public`
is set explicitly. Without `BUF_TOKEN`, the first push fails and
the BSR module is not created.

### Breaking changes

`buf breaking` runs on every PR with the `FILE` category (the
strictest — catches anything that would break generated code). For
intentional breaks, add the `buf skip breaking` label to the PR
(Issues → Labels in the repo settings); the action checks for the
label and skips the breaking step. For permanent breaks, add a new
package path (`tinkle/v2/`) rather than mutating `tinkle/v1/`.

## Local validation

```bash
buf format -d
buf lint
buf breaking --against ".git#branch=origin/main"
buf build
# Additional schema/codec conformance; no SDK generation or server runtime.
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s conformance -p 'test_*.py' -v
```

These are the same checks the buf-ci action runs on every PR. There
is no local `buf generate` step — code generation happens on the
BSR.

## Realtime Syntra protocol (version 1)

[`tinkle/v1/realtime.proto`](tinkle/v1/realtime.proto) defines Syntra-only
application data, not gRPC contracts and not a legacy JSON WebSocket. The binding
uses generic `RpcRequest`/`RpcResult` and `Notification.payload`, declares no
`RealtimeService` gRPC service, and adds no application fields to Syntra core.

### Syntra application binding (feature branch)

This is the feature-branch design on `feat/realtime-sync-recovery`, not a shipped or
BSR-published binding or an implemented server endpoint. Read [REALTIME.md](REALTIME.md)
for normative requirements and [realtime conformance](conformance/realtime.md) for
implementation checks; schema validation alone cannot prove synchronization.

#### Method and payload selection

These generic Syntra dispatcher identifiers map to the existing draft messages in
`tinkle/v1/realtime.proto`; they do not declare a new gRPC service or endpoint.

| `RpcRequest.method` | Request payload | Successful `RpcResult.payload` |
| --- | --- | --- |
| `/tinkle.v1.Realtime/SubscribeBatched` | `SubscribeRequest` | `SubscribeResponse` |
| `/tinkle.v1.Realtime/UnsubscribeBatched` | `UnsubscribeRequest` | `UnsubscribeResponse` |

Failures use Syntra `RpcResult.error`. Syntra `ServerReady` alone establishes the
connection: `SubscribeResponse` reserves the draft `connection_id` field and tag,
and confirms interests, not replay completion. No Tinkle ready/hello is sent.
The verified principal selects the own-user stream. Room and presence interests
remain authority-checked and bounded; unsubscribe releases only optional watches.

Every Tinkle realtime `Notification.payload` is one protobuf-binary
`RealtimeNotification`, whose `kind` oneof selects `batch`, `presence`, or
`reset_required`. Durable delivery is only a complete `RealtimeBatch` of 1–4
ordered events: optional user/chat primers, snapshot or sender-only send failure,
then position; or a singleton redaction or read-state invalidation. Never flatten
batches, send bare events/batches/presence/resets, fall back to JSON, or try multiple
decoders. Validate known kinds, event enum/variant agreement, and the complete batch
before effects; unsupported variants stop application without checkpoint progress.

Message bodies use only public `Message` projections from `tinkle/v1/messages.proto`,
not private journal/policy data. Redactions disclose no identifying metadata.
Presence is ephemeral, never checkpointed, and cleared on disconnect.

#### Checkpoints and recovery

- Checkpoints belong to one authenticated principal, stream, and valid history scope,
  independently of connection/request IDs. Reauthenticate and explicitly resubscribe
  after reconnect; no Syntra session resumption or exactly-once guarantee is provided.
- Validate and atomically commit all batch effects plus `final_cursor`, or neither.
  Complete required invalidation refreshes before checkpointing. Deduplicate whole
  batches by `(stream, cursor)` within principal/history scope, not members by UUID;
  hydrated replay need not be byte-identical. Receipt/enqueue is not application commit.
- Accept the next cursor only; duplicates do not reapply, gaps stop progress, and
  older cursors never move a checkpoint backward. See REALTIME.md for overlap rules.
- Positions fit `0..9223372036854775807`; delivered cursors are positive. An absent
  cursor means zero, never start-live. With `replay_floor` the largest removed cursor,
  `after < replay_floor` expires, equality is valid, and `after > head` is invalid.
- Reset stops one stream. Its optional `head` is diagnostic, **not a snapshot
  checkpoint**. Do not fetch unrelated pages and resume at sampled head or zero.
  No snapshot/fence RPC is added; recovery remains unavailable until a proven
  consistent source snapshot/checkpoint and race-free watch bootstrap exist.
- Persist the exact pending send request and nonzero signed `random_id` before
  sending. A lost result means unknown outcome; retry the unchanged request/key
  with fresh transport correlation, subject to authorization and bounded retries.

Source-snapshot/projection fencing, room leave/rejoin/history-scope continuity,
identity-free redaction and privacy-safe cache reconciliation, and actual source
CDC publication/catch-up remain separate blockers to full synchronization.

#### Compatibility and release

Pre-release restructuring removed the legacy JSON WebSocket messages. This is an
intentional breaking change with no external compatibility commitment. There are
no experimental Subscribe aliases to preserve. Select the batched binding before
decoding; do not mix bindings on one connection.

Review schema/conformance, explicitly publish through the normal main-merge/BSR
workflow, pin exact generated Go/Rust revisions, implement server dispatch and
validators, then roll out compatible clients. Consume the new types only after
publication; no generated realtime gRPC stub is required. On rollback,
stop the new binding explicitly while preserving durable checkpoints, heads, and
source identities; do not switch decoders or reset Kafka groups to claim recovery.

## BSR resource

- Module: <https://buf.build/tinklecorp/tinkle-proto>
- Generated SDKs: <https://buf.build/tinklecorp/tinkle-proto/sdks>
- Documentation: <https://buf.build/tinklecorp/tinkle-proto/docs>

## Source

- Public proto source of truth: this repository, `tinkle/v1/`.
- Server implementation consumes the published BSR SDK; public schemas are not mirrored there.
