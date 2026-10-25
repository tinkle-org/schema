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
`introduction.mdx`) and are committed; generated
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
are in [`common.proto`](tinkle/v1/common.proto).

[`updates.proto`](tinkle/v1/updates.proto) defines `UpdatesService`:
`ReadUpdates` returns a bounded replay page, `FollowUpdates` streams individual
durable updates, progress, and rebuild signals, and `ObserveConnectivity` streams
ephemeral per-user `ConnectivityChanged` events. Each `Update` has one payload:
`MessageRefresh`, `SendAttemptFailed`, `ContentOmitted`, or `ReadStateInvalidated`.
Message effects, hydration, and order hints belong to the message constructor.
`ReadUpdates` resumes strictly after the caller's applied cursor with `limit`
and an optional `max_replay_distance` catch-up threshold; responses report the
replay floor, observed head, and whether more replay remains.
See the [generated reference](https://tinkle.me/schema/reference) for field and
method semantics.

Public UpdatesService bindings are not implemented in Chorus. Internal
replay, watch, and presence capabilities exist; runtime bindings are documented
in their implementation repositories. Room continuation stays fail-closed unless
the implementation can establish continuity; current authorization and a saved
numeric cursor alone are not sufficient.

## BSR resource

- Module: <https://buf.build/tinkle-org/schema>
- Generated SDKs: <https://buf.build/tinkle-org/schema/sdks>
- Documentation: <https://buf.build/tinkle-org/schema/docs>

## Source

- Public proto source of truth: this repository, `tinkle/v1/`.
- Server implementation consumes the published BSR SDK; public schemas are not mirrored there.
