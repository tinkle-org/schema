# tinkle-proto

Source of truth for the `tinkle.v1` Protobuf contract. The schema is
published to the [Buf Schema Registry](https://buf.build/tinkle-org/schema)
(public), which generates and serves **Go** and **Rust** SDKs to
consumers. The repo holds the proto source, the Buf config, and the
documentation content for the schema docs at tinkle.me/schema/ — its API
reference is generated from the proto descriptor set.

The public `.proto` files are maintained directly here under `tinkle/v1/`.
This repository is the source of truth, not a mirror of the server repository.
Consumers use BSR-generated SDKs; no language-specific generated code is stored here.

## Architecture

```
tinkle-org/schema/               ← proto source + Buf config + docs site
├── tinkle/v1/*.proto                  authoritative public proto source
├── conformance/                       schema/codec checks (pure Python)
├── buf.yaml                           v2 workspace; module published to
│                                      buf.build/tinkle-org/schema
├── version.txt                        schema release version (release-please)
├── release-please-config.json         release config (simple type)
├── .release-please-manifest.json      bootstrap 0.0.0
├── buf.lock                           generated
├── LICENSE                            at module root (required for pkg.go.dev)
├── website/                           docs content sources (tinkle.me/schema/)
│   ├── scripts/generate-reference.mjs descriptor-set → reference pages
│   └── content/reference/             generated (not committed)
└── .github/workflows/
    ├── buf-ci.yaml                    validate on PRs, publish on main paths
    ├── release-please.yaml            Release PRs, tags, changelogs, version-label publish
    ├── docs-ci.yaml                   site build on PRs
    └── docs-build.yaml                content build + website dispatch on main
```

The BSR owns the generated Go and Rust SDKs. This repository generates only
the docs site's reference pages, which are rebuilt on every build and git-ignored.

## Publishing

Publication to the Buf Schema Registry is **trunk-based**:

```
feature branch ──► PR: buf-ci validates (build/lint/format/breaking, no publish)
       │  merge to main
       ▼
buf-ci.yaml on main paths: build + buf push with Git metadata
       │
       ├── BSR commit + moving main label (test here first)
       └── tag push (v*) publishes the version label
release-please maintains Release PRs, tags, changelogs, and the version-label
publish fallback (plus manual tag recovery)
```

- Every `main` push matching the buf-ci paths publishes. Test unreleased
  changes from other repos via the BSR commit or `@main` before cutting
  a formal release.
- Bump semantics follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:` minor, `fix:` patch); `bump-minor-pre-major` is on, so breaking
  restructuring bumps the pre-1.0 minor instead of the major.
- Secrets: `BUF_TOKEN` (BSR token for `tinkle-org`, used by `buf-ci.yaml`)
  and, recommended, `RELEASE_PLEASE_TOKEN` (a PAT so Release PRs trigger
  repository CI — PRs created with the default token do not trigger
  workflows).

```
main (proto source + Buf config)
   │
   ▼  buf-ci push on main path matches (+ tag pushes for versions)
buf.build/tinkle-org/schema (public)
   │
   ▼  consumer reads commit, main label, or version label
go get buf.build/gen/go/tinkle-org/schema/{protocolbuffers,grpc}/go@main
cargo add --registry buf tinkle-org_schema_bufbuild_community_tonic-prost
```

## Consuming the bindings

The BSR auto-versions each push. SDK versions are
`{plugin-version}-{module-commit-timestamp}-{module-commit-id}.{plugin-revision}`
(e.g. `v1.36.11-20260617120000-abc123def456.1`). Pin with
`@vX.Y.Z-…`, `@<commit-id>`, or `@<label>`.

### Go

```bash
go get buf.build/gen/go/tinkle-org/schema/protocolbuffers/go@latest
go get buf.build/gen/go/tinkle-org/schema/grpc/go@latest
```

```go
import (
    tinklev1   "buf.build/gen/go/tinkle-org/schema/protocolbuffers/go/tinkle/v1"
    tinklegrpc "buf.build/gen/go/tinkle-org/schema/grpc/go/tinkle/v1"
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
cargo add --registry buf tinkle-org_schema_bufbuild_community_tonic-prost
```

> **First-`cargo-add` priming.** Rust SDKs are generated eagerly on
> the BSR (Cargo needs a checksum for every version). The first
> `cargo add` against this module triggers the initial generation;
> every subsequent trunk-based BSR publication produces a new crate
> version automatically.

### Other ecosystems

The BSR also serves TypeScript/JavaScript, Python, Java/Kotlin, and
Swift SDKs against the same module — see
[buf.build/tinkle-org/schema/sdks](https://buf.build/tinkle-org/schema/sdks).

## CI

Two independent workflows:

- `.github/workflows/buf-ci.yaml` runs `bufbuild/buf-action@v1`.
  On every PR to `main` it runs `build`, `lint`, `format`, and `breaking`,
  and posts a summary comment (no publish). On pushes to `main` (and `v*`
  tags) it validates and publishes to the BSR. See [Publishing](#publishing).
- `.github/workflows/release-please.yaml` maintains Release PRs on `main`
  for versioning, changelogs, and Git tags, and publishes the version
  label on release (plus manual tag recovery). It does not move the
  `main` label.

### Required secrets

- `BUF_TOKEN` — a BSR API token for the `tinkle-org` org, used by
  `buf-ci.yaml` to publish on `main` and tag pushes and by
  `release-please.yaml` to publish the version label. Without it,
  merges validate but publishing fails.
- `RELEASE_PLEASE_TOKEN` (recommended) — a personal access token with
  repo scope, so Release PRs created by release-please trigger the
  repository's CI checks (PRs created with the default `GITHUB_TOKEN`
  do not trigger workflows). It also gates the `schema-docs-updated`
  dispatch from `docs-build.yaml` to the website repo — without it the
  dispatch is skipped.

### Breaking changes

The intended stable policy is `FILE` (the strictest — catches anything
that would break generated code), but pre-release restructuring
currently disables builtin breaking entirely (`buf.yaml`
`breaking.disable_builtin`), so `buf breaking` does not fail CI on
`tinkle/v1/` restructuring. Once re-enabled at the first stable
release, for intentional breaks add the `buf skip breaking` label to
the PR (Issues → Labels in the repo settings); the action checks for
the label and skips the breaking step. For permanent breaks, add a new
package path (`tinkle/v2/`) rather than mutating `tinkle/v1/`.

## Documentation site

`website/` holds the docs **content sources and generators** for the schema
documentation published at **<https://tinkle.me/schema/>**. Rendering happens
in the main website repo (`tinkle-org/tinkle-website-nextjs`), which serves
the content as a Nextra section at the `/schema/` path. The schema reference
(generated by [`website/scripts/generate-reference.mjs`](website/scripts/generate-reference.mjs))
is generated from `buf build --as-file-descriptor-set` output — proto doc
comments, deprecations, oneofs and reserved definitions all appear in the
generated pages. Hand-written pages describe the transport-independent schema;
runtime transport bindings belong in their implementation repositories.

```bash
cd website
npm run generate   # descriptor set → content/reference/
npm run check      # internal /schema/... links resolve + structure is sane
```

Hand-written pages live in `website/content/` (`index.mdx`,
`introduction.mdx`, [Connection Initialization](website/content/connection-initialization.mdx),
[Device Enrollment](website/content/device-enrollment.mdx), and `file-transfers.mdx`)
and are committed; generated
output (`website/content/reference/`) is
git-ignored. To preview the rendered site, run the website repo locally —
it fetches this repo and generates the content as part of its build.

Build: `.github/workflows/docs-build.yaml` runs on merges to `main`,
validates the generated content, and dispatches a `schema-docs-updated`
event to the website repo when `RELEASE_PLEASE_TOKEN` is configured
(skipped without it; the website still picks up the content on its next
build), which rebuilds and re-validates against the
fresh content (deploy follows the website's own release flow). PRs get
the same checks via `docs-ci.yaml`.

## Local validation

```bash
buf format -d
buf lint
buf breaking --against ".git#branch=origin/main"
buf build
# Additional schema/codec conformance; no SDK generation or server runtime.
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s conformance -p 'test_*.py' -v
# Documentation site content (optional; see "Documentation site" above)
cd website && npm run generate && npm run check
```

Buf checks mirror the buf-ci PR workflow. There is no local `buf generate`
step — code generation happens on the BSR, and docs generation happens in
`website/`.

## Schema inventory

Public contracts live under [`tinkle/v1/`](tinkle/v1/): authentication, accounts,
users, contacts, messaging, channels, bots, stickers, and help APIs. Shared types
are in [`common.proto`](tinkle/v1/common.proto); shared rich-text spans are in
[`entities.proto`](tinkle/v1/entities.proto), and the shared media vocabulary
(metadata, attributes, file variants) is in [`media.proto`](tinkle/v1/media.proto).

[`auth.proto`](tinkle/v1/auth.proto) defines recoverable device-key enrollment:
`SendCode`, `SignIn`, `ResumeEnrollment`, `ActivateEnrollment`, and
`RotateEnrollment`. Clients retain an operation UUID and 32-byte recovery secret
before sign-in, securely persist the staged 32-byte key and 8-byte handle,
acknowledge storage over pinned Bootstrap with the same operation, 32-byte
provisioning capability, and exact candidate tuple, then establish fresh Returning
with the ACTIVE key. STAGED keys cannot pass Returning admission. Activation does
not rebind the live principal. Typed enrollment is `SignInResponse` field 4.
Account session lists use neutral device-session UUIDs. See the
[device-enrollment guide](website/content/device-enrollment.mdx).

[`connection.proto`](tinkle/v1/connection.proto) defines
`ConnectionService.InitConnect`: a full `ClientInfo` snapshot plus a selected
public unary request, returning that method's serialized response, and
`ConnectionService.KeepAlive`: an ACTIVE-authenticated application liveness
request with a channel-local positive `uint64 sequence = 1`, echoed by the
response. Duplicate or reordered sequences cannot extend a presence lease;
current authorization runs before every effect. Runtime bindings own scheduling
and deadlines independently of transport-core heartbeats. The
[connection-initialization guide](website/content/connection-initialization.mdx)
covers validation, authorization, snapshot replacement, binding scope, and liveness.
This is the schema contract; runtime bindings and Chorus adapters are not
implemented here, and schema publication does not imply runtime support.

[`files.proto`](tinkle/v1/files.proto) defines `FilesService`: resumable upload
sessions (`BeginUpload`, `UploadPart`), authoritative snapshot-based status
(`GetUploadStatus`), atomic completion (`CompleteUpload`), best-effort
cancellation (`AbortUpload`), storage metadata (`GetFileInfo`), and byte-range
downloads (`DownloadPart`). Completed files are immutable and referenced by
canonical `file_id` across services. Non-uploaders supply `FileAccessContext`
on both file-read methods, selecting a visible message, retained profile-gallery
entry, usable sticker asset, or current chat photo; authorization and exact file
membership are rechecked on every call. Profile-photo owners may reference
unselected retained entries; nonowners may reference only the selected photo when
privacy permits it.
Chat-photo contexts identify the chat and its current `ChatPhoto.photo_id`;
each read requires current visibility and exact photo-file membership, even for
the uploader. Replacement/removal or lost visibility invalidates the context.
See the file-transfer guide in
`website/content/file-transfers.mdx`.

[`stickers.proto`](tinkle/v1/stickers.proto) unifies user-owned stickers and
custom emoji in `StickersService`: asset creation/update/deletion, batched ID
resolution with fallback text, and same-kind pack authoring, membership/order,
publication, installation, and discovery. Packs hold at most 100 assets, pinning
exact immutable `asset_version` values; `pack_revision` and expected-token CAS
protect authoring from lost updates. ID-only asset resolution discovers usable
heads; `AssetReference` resolves exact versions, including withdrawn versions
scoped to a currently visible message. `StickerKind` and `PackKind` distinguish
usage; format does not determine animation. [`account.proto`](tinkle/v1/account.proto)
owns profile-photo set/list/select/delete with a complete, at-most-10-entry
owner gallery, a private `gallery_revision`, and CAS mutations. Repeated sets of
the same retained file/source reuse its photo ID. Asset and profile-photo sources
reference completed files only
and require the explicit `STRICT_LOSSLESS` validation profile, version 1.
Its accepted formats and bounded validation rules are defined in
[`media.proto`](tinkle/v1/media.proto) and the source-message comments.
General media use separate version 1 `IMAGE`, `VIDEO`, `AUDIO` and `VOICE`
profiles. Clients normalize/upload the main; servers measure physical facts and
generate required lower-pixel thumbnails before owning-object publication.
Raw documents remain raw unless an explicit typed purpose is selected. There
are no file-level encryption options. The [file-transfer guide](website/content/file-transfers.mdx)
defines the processing split, per-purpose thumbnail requirements and readiness.

[`updates.proto`](tinkle/v1/updates.proto) defines `UpdatesService`,
streaming only ephemeral privacy-filtered per-user `ConnectivityChanged`
observations through `ObserveConnectivity`. Durable replay and watch (the
former `ReadUpdates` and `FollowUpdates`, the `Update` envelope, and its
payloads) have been retired from the public contract and remain
implementation-internal.
See the [generated reference](https://tinkle.me/schema/reference) for field and
method semantics.

Public UpdatesService bindings are not implemented in Chorus. Internal
replay, watch, and presence capabilities exist; runtime bindings are documented
in their implementation repositories.

To support clients reconciling without a durable feed,
[`messages.proto`](tinkle/v1/messages.proto) defines `GetMessages` batch fetch by
message ID, a per-conversation ordering and dedup token on
`Message.accept_seq`, `ListMessageChanges` listing authorized retained body,
metadata and removal changes after a mutation acceptance position, and a server-confirmed
`more_available` on `GetHistoryResponse`.
`Message.body_revision` orders complete bodies for the same principal and message;
`edit_date` is only a fallback when a revision is absent. Pin/reaction/poll/private
acknowledgement changes do not manufacture user edit dates. Journal markers carry
their exact `message_revision`, while authorized current-body hydration can be
newer. Resume from the response's stable `last_accept_seq`, not a marker or body
revision: filtering, retention and pending positions prevent assuming continuity.
`MessageChanged` and `TypingChanged` are transport-neutral notification payloads,
not RPCs, replay cursors or receipts; ACK markers/hints are private to their viewer.
They do not extend the connectivity-only `UpdatesService` or define a transport.
`TargetChange.body_invalidated=6` explicitly reports source-authorized nonterminal
body withholding for the canonical caller/target/message identity. It requires
an absent body, a positive revision and a nonterminal kind. Purge cached bodies
and file references at or below that revision and retain a nonterminal revision
floor; reject stale/unknown held responses. A fresh currently authorized body at
the same or newer revision may hydrate. This is not viewer deletion or permission
proof. `MessageChanged.body_invalidated=6` is only a non-authoritative hint:
reconcile with the current source before applying an invalidation or floor.
The 43-method `MessagesService` also carries explicit thread roots in `ReplyInput`,
album identity and scheduling state on returned messages, quiz answer definitions
and caller-relative poll aggregates, and opaque search continuation with an
explicit `more_available` report. An omitted search target means global search
over currently visible conversations; an empty present target is invalid.
Conversation search also supports full-width `offset_message_id`; opaque cursors
remain usable for every search scope. Poll options and quiz answers retain their
opaque byte identifiers, not option indexes.

`GetScheduledMessages` resolves only explicit jobs owned by the authenticated actor
in one conversation. Supply exactly one nonempty collection of 1..100 distinct
positive message IDs or nonzero signed idempotency keys; an empty request never
discovers a list. Unknown, unowned and expired jobs are omitted. `ScheduledMessage`
reports job state separately from accepted-history visibility; status alone proves
neither history acceptance nor peer receipt. `CancelScheduledMessages` takes 1..100
distinct positive message IDs; any album item selects its whole group. Cancellation
reports durable canceled items, not rollback or a batch transaction, and never
deletes accepted history. Recover uncertain or partially applied calls by lookup.
`ClosePoll` closes a currently visible sender-owned poll and returns the same
caller-relative projection as `GetPollResults`. Quiz correctness stays hidden until
the caller votes or the poll closes; it is not a separate answer-key API.

Messaging uses `SendAlbum` with ordered `AlbumItem` entries, `GetChatDetails`,
`ListThreadMessages`, `BatchGetMessageReactions`, `ListMessageReactions`,
`MarkHistoryRead`, `StartBot` and `UpdateChatDescription`. `GetChatDetailsResponse.chat_details`
contains `ChatDetails`; `UpdateChatDescriptionRequest.description` sets the description.
The shared basic entity retains `Chat.about`. Sends use full-width
`int64 idempotency_key`; reply/thread fields use `reply_to_message_id` and
`thread_root_id`. `SetMessagePin.pin_scope` selects shared or caller-private
personal pins; omission selects shared and explicit unspecified is invalid.
Optional `Message.personal_pin` is caller-relative, separate from shared `pinned`;
optional `Message.suppress_link_preview` reports preview suppression.
`ChatPhoto` exposes its main `file_id`, measured metadata and ready variants for
the existing chat-photo read context. Restrictions represent each of text, photo,
video, audio, voice and raw-document sending independently. Favorite-sticker
writes specify desired `is_favorite` membership: true adds and false removes.

`CreateChatRequest.operation_id` is a positive `int64` required when
`ttl_period > 0`; zero permits an unkeyed request only when TTL is absent/zero.
`AddChatParticipantRequest.operation_id` is a positive `int64` required when
`forward_limit > 0`; zero permits an unkeyed add only when the limit is zero.
Negative keys are invalid. These numeric keys, and `EditChatPhoto`'s numeric
publication key, are distinct from the UUID strings used for reaction side
effects and resumable history deletion. Retain the original key and arguments
after uncertain completion.

`SendReaction.operation_id` is a caller-scoped UUID required when `animate` or
`save_to_recents` is true. Absent/false options disable those side effects, not
the reaction update. `GetRecentReactions` returns only the caller's at-most-32
retained exact identities, never current catalog heads or an asset access grant.
`MessageChanged.reaction_effect` carries typed `ReactionEffect` presentation
metadata: deduplicate `(actor_id, operation_id)`, discard expired effects and
never extend the original deadline on retry, delivery or reconnect. Current
recipient visibility still controls delivery; durable hydration is not animation replay.
Render only validated positive actor IDs, canonical operation UUIDs and finite
unexpired deadlines; malformed presentation metadata grants no access or effect.

Send requests carry optional `clear_draft_dialog_id`/`clear_draft_revision` pairs
for the authenticated sender's source-fenced draft clearing on immediate or scheduled
sends in direct conversations and rooms. Preserve the original
pair on retries; never clear a newer source. `Dialog.draft_dialog_id` and
`draft_revision` report the owned pair even with no draft content, including
revision zero for an initialized empty source. Missing tokens mean unknown.
`Dialog.notification_settings` is the owner-resolved scope/target preference;
its absence is unknown, not an enabled default. Optional unread mention/reaction
counts distinguish unknown from zero. Optional `read_outbox_max_id` is a DM
message reference, not an acceptance position; rooms/unknown states omit it.

`DeleteHistory` reports stable `operation_id`, explicit `completed` and cumulative
`processed_count` on its response type.
Clients persist the request ID before sending and retry identical parameters to
continue/recover bounded work; no job service is introduced. History selection
freezes at first acceptance. Revocation removes the caller's own messages for
everyone and incoming messages for the caller only. Cancellation and timeouts
do not imply rollback or completion.
Ordinary deletion leaves the peer's history and read state unchanged. Recovery
retains the original filters and frozen source selection rather than reconstructing
work from a later cache or the peer's history.
`DeleteMessages` authorizes and deletes items independently; an ineligible item
does not prevent deletion of eligible items. Its response reports only the count
newly deleted by that call, without operation identity or progress fields.
Participant views are independent: caller-only deletion removes the caller's view,
not another participant's copy, and proves neither physical byte erasure nor
deletion of unrelated messages.

`Entity` and `EntityType` are shared by help text, message bodies, media captions,
drafts and quotes. Spans count UTF-16 code units and must start and end on Unicode
scalar boundaries. The shared contract defines allowed nesting, rejects crossing
spans, and isolates code/preformatted spans from overlap. Type-specific fields
are meaningful only for their declared type. Custom emoji use `custom_emoji_id`,
an exact positive `asset_version`, and the version's canonical `fallback_text`;
the selected text span must match that fallback exactly. Reactions use the same
asset ID/version with canonical fallback in `emoticon`. Exact asset resolution
uses `GetStickerAssets`; unavailable assets render the retained fallback.

`SearchResponse` is the full-message result shared by server and cache search.
`source` identifies `SERVER` or `CACHE`; `coverage` identifies `INDEXED` or
`CACHED_SUBSET`. Unspecified or absent metadata is unknown. `more_available`
reports continuation only in the selected backend: exhausting a cache never
upgrades its coverage to the server index. Queries are literal case-insensitive
substrings of message text/captions, not regex, wildcard or token expressions;
backend Unicode case handling and available corpora can yield different matches.
Queries are at most 1024 UTF-8 bytes; page size is 1..100, with zero selecting 50.
Within a target/source results follow stable descending source acceptance order,
not edit time or relevance. Global ordering is source-defined and deterministic,
with target/message identity tie-breakers; per-target acceptance positions are
not globally comparable. Use the selected backend's continuation unchanged.
Recovery preserves that source and the original filters; changing either starts
a new search without reusing the cursor.

## BSR resource

- Module: <https://buf.build/tinkle-org/schema>
- Generated SDKs: <https://buf.build/tinkle-org/schema/sdks>
- Documentation: <https://buf.build/tinkle-org/schema/docs>

## Source

- Public proto source of truth: this repository, `tinkle/v1/`.
- Server implementation consumes the published BSR SDK; public schemas are not mirrored there.
