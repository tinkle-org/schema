# AGENTS

This file is the entrypoint for AI coding agents working in this
repository. Read it fully before making any non-trivial change.

## TL;DR

- **`tinklehq/tinkle-proto`** is the source of truth for the
  `tinkle.v1` Protobuf contract. The repo contains the `.proto`
  files and Buf config only.
- The schema is published to the Buf Schema Registry at
  **`buf.build/tinklecorp/tinkle-proto`** (public). The BSR
  generates and serves **Go** and **Rust** SDKs to consumers; no
  language-specific code lives in this repo.
- The `.proto` files are **maintained directly in this repo** under
  `tinkle/v1/`. There is no upstream mirror; this is the only place
  the contract is edited.
- **No release-please, no per-language tags, no generated code in
  the tree.** Bump a version on the BSR by pushing a new commit;
  consumers update via `go get @latest` or `cargo add --registry buf`.

## Architecture

```
tinklehq/tinkle-proto (this repo)    proto source + Buf config
├── tinkle/v1/*.proto                proto source (owned here)
├── buf.yaml                         v2 single-module workspace
│                                    name: buf.build/tinklecorp/tinkle-proto
├── buf.lock                         generated
├── LICENSE                          required at module root for pkg.go.dev
├── README.md
├── .github/workflows/buf-ci.yaml    bufbuild/buf-action:
│                                      build/lint/format/breaking/push
└── AGENTS.md
```

The BSR takes care of everything else: published module, generated
SDKs, version history, generated documentation, and dependency
resolution. See <https://buf.build/tinklecorp/tinkle-proto> for the
live state.

The server (`tinklehq/tinkle-server`) and any other microservice
that talks to the API consume the BSR-published Go SDK — they do
not edit or mirror `.proto` files from this repo.

## Consumer dependencies

| Language | Command |
|----------|---------|
| Go       | `go get buf.build/gen/go/tinklecorp/tinkle-proto/protocolbuffers/go` |
| Go (gRPC) | `go get buf.build/gen/go/tinklecorp/tinkle-proto/grpc/go` |
| Rust     | `cargo add --registry buf tinklecorp_tinkle-proto_bufbuild_community_tonic-prost` |

Versions are `{plugin-version}-{module-commit-timestamp}-{module-commit-id}.{plugin-revision}`
(e.g. `v1.36.11-20260617120000-abc123def456.1`). Pin with
`@vX.Y.Z-…`, `@<commit-id>`, or `@<label>`.

## Conventions for agents

1. **Edit `.proto` files in place under `tinkle/v1/`.** This repo is
   the only place the contract is maintained. There is no mirror
   from `tinklehq/tinkle-server` (or anywhere else) — proto changes
   land here directly. Keep the Protobuf `package tinkle.v1;` and
   the `option go_package = "github.com/tinklehq/tinkle-proto/tinkle/v1;tinklev1";`
   line consistent across all 11 files in the package.
2. **`buf push` is automatic on merge to `main`.** The `buf-ci.yaml`
   workflow uses `bufbuild/buf-action@v1`; on push to `main` it
   publishes every named module in the workspace to the BSR with
   the matching Git metadata.
3. **`BUF_TOKEN` secret is required.** A BSR API token for the
   `tinklecorp` org must be configured as a repository secret
   (Settings → Secrets and variables → Actions) before the first
   merge to `main`, otherwise the initial `buf push` will fail and
   the BSR module will not be created. The action auto-creates the
   BSR repo on first push; `push_create_visibility: public` makes
   that explicit.
4. **Lint before pushing.** Run `buf format -d` and `buf lint`
   locally; the `buf-ci.yaml` action will run them on every PR and
   fail the build on findings.
5. **Breaking is disabled for pre-release.** `buf.yaml` sets
   `breaking.disable_builtin: true`, so restructuring `tinkle/v1/`
   does not fail CI or local `buf breaking`. Re-enable on first
   stable release by setting it to `false` (intended stable policy
   is `breaking: FILE`). After re-enabling, intentional breaks need
   a `buf skip breaking` label on the PR, and permanent breaks need
   a new package path (`tinkle/v2/`) rather than mutating `tinkle/v1/`.
6. **No `buf generate`, no `buf.gen.yaml`.** Code generation
   happens on the BSR. A `buf.gen.yaml` only exists if you need
   to run `buf generate` against a third-party plugin locally;
   in this repo, there is none.

## When asked to "add a new RPC"

1. Open a PR in this repo (`tinklehq/tinkle-proto`) editing the
   relevant `tinkle/v1/*.proto`. Add the request/response messages
   and the method to the appropriate `service` block. Keep the
   Protobuf `package` and `option go_package` lines as they are.
2. The buf-ci action on the PR runs `build`, `lint`, `format`, and
   `breaking` (against the base branch) and posts a summary comment.
   Fix any findings.
3. Merge to `main`. The action runs `buf push`, which publishes a
   new commit to the BSR. The BSR serves the updated Go and Rust
   SDKs lazily — consumers pick them up with `go get @latest` or
   the next `cargo add` (Rust SDKs are generated eagerly, so a new
   crate version is produced immediately on push to the default
   label after the initial `cargo add`).

## When asked to "fix generated code"

Don't try to fix generated code in this repo — there is no
generated code in this repo. Edit the `.proto` source in
`tinkle/v1/` directly; the BUF_CI push run on merge will republish
the schema to the BSR, and consumers will pick up the regenerated
SDKs on their next `go get`/`cargo add`.

## Local validation

```bash
buf format -d
buf lint
buf breaking --against ".git#branch=origin/main"
buf build
```

These are the same checks the `buf-ci.yaml` action runs on every
PR. There is no local `buf generate` step.

## CI workflow

`.github/workflows/buf-ci.yaml` runs `bufbuild/buf-action@v1`,
which on every PR runs `build`, `lint`, `format`, and `breaking`,
and on every push to `main` also runs `buf push` (publishing to
the BSR). On a branch delete, the action archives the matching
BSR label. The action posts a PR summary comment keyed on
`<workflow>:<job>`.

## BSR resource

- Module: <https://buf.build/tinklecorp/tinkle-proto>
- Generated SDKs: <https://buf.build/tinklecorp/tinkle-proto/sdks>
- Documentation: <https://buf.build/tinklecorp/tinkle-proto/docs>
