# AGENTS

This file is the entrypoint for AI coding agents working in this
repository. Read it fully before making any non-trivial change.

## TL;DR

- **`tinkle-org/schema`** is the source of truth for the
  `tinkle.v1` Protobuf contract. The repo contains the `.proto`
  files, Buf config, and the schema docs content (Nextra-rendered).
- The schema is published to the Buf Schema Registry at
  **`buf.build/tinkle-org/schema`** (public). The BSR
  generates and serves **Go** and **Rust** SDKs to consumers; no
  language-specific code lives in this repo.
- **BSR publication is release-gated.** Everyday merges only
  validate. `buf push` runs exclusively when a release-please
  Release PR is merged (see `release-please.yaml`).
- The `.proto` files are **maintained directly in this repo** under
  `tinkle/v1/`. There is no upstream mirror; this is the only place
  the contract is edited.
- **No release-please per-language tags, no generated SDK code in
  the tree.** Bump the schema version by merging a Release PR;
  consumers update via `go get @latest` or `cargo add --registry buf`.
- The **docs content** lives in `website/` and is rendered at
  **`https://tinkle.me/schema/`** by the main website repo
  (`tinkle-org/tinkle-website-nextjs`, Nextra). This repo is the content
  source: hand-written pages in `website/content/`, generated reference
  pages built from the descriptor set at website-build time. The website
  repo runs these generators — it does not edit content.

## Architecture

```
tinkle-org/schema (this repo)   proto source + Buf config + docs site
├── tinkle/v1/*.proto                 proto source (owned here)
├── conformance/                      schema/codec conformance checks
├── buf.yaml                          v2 single-module workspace
│                                     name: buf.build/tinkle-org/schema
├── buf.lock                          generated
├── version.txt                       schema release version (release-please)
├── release-please-config.json
├── .release-please-manifest.json
├── CHANGELOG.md                      maintained by release-please
├── LICENSE                           required at module root for pkg.go.dev
├── README.md
├── website/                          docs content sources (tinkle.me/schema/)
├── .github/workflows/buf-ci.yaml     bufbuild/buf-action: validate only
├── .github/workflows/release-please.yaml  Release PRs + gated buf push
├── .github/workflows/docs-ci.yaml    docs content validation on PRs
├── .github/workflows/docs-build.yaml     content build + website dispatch on main
└── AGENTS.md
```

The BSR takes care of everything else: published module, generated
SDKs, version history, generated documentation, and dependency
resolution. See <https://buf.build/tinkle-org/schema> for the
live state.

The server (`tinklehq/tinkle-server`) and any other microservice
that talks to the API consume the BSR-published Go SDK — they do
not edit or mirror `.proto` files from this repo.

## Consumer dependencies

| Language | Command |
|----------|---------|
| Go       | `go get buf.build/gen/go/tinkle-org/schema/protocolbuffers/go` |
| Go (gRPC) | `go get buf.build/gen/go/tinkle-org/schema/grpc/go` |
| Rust     | `cargo add --registry buf tinkle-org_schema_bufbuild_community_tonic-prost` |

Versions are `{plugin-version}-{module-commit-timestamp}-{module-commit-id}.{plugin-revision}`
(e.g. `v1.36.11-20260617120000-abc123def456.1`). Pin with
`@vX.Y.Z-…`, `@<commit-id>`, or `@<label>`.

## Conventions for agents

1. **Edit `.proto` files in place under `tinkle/v1/`.** This repo is
   the only place the contract is maintained. There is no mirror
   from `tinklehq/tinkle-server` (or anywhere else) — proto changes
   land here directly. Keep the Protobuf `package tinkle.v1;` and
   the `option go_package = "github.com/tinklehq/tinkle-proto/tinkle/v1;tinklev1";`
   line consistent across all files in the package.
2. **`buf push` is release-gated, not automatic.** `buf-ci.yaml`
   validates only (`push: false`). Publication runs exclusively in
   `release-please.yaml` when a Release PR merge creates a release:
   checkout the released sha, `buf build` + `buf lint`, then
   `buf push --label <tag> --label main`. Do not push manually to
   the BSR; ordinary merges must not touch the registry.
3. **`BUF_TOKEN` is required for publication.** A BSR API token for
   the `tinkle-org` org (repository secret). `RELEASE_PLEASE_TOKEN`
   (a PAT) is recommended so Release PRs trigger the repo's CI —
   PRs created with the default token do not run workflows.
4. **Write proto doc comments for humans.** Every message, field,
   enum value, service and method's leading `//` comment becomes the
   generated API reference on the docs site. No separate reference
   prose is maintained anywhere else.
5. **Lint before pushing.** Run `buf format -d` and `buf lint`
   locally; the `buf-ci.yaml` action will run them on every PR and
   fail the build on findings.
6. **Breaking is disabled for pre-release.** `buf.yaml` sets
   `breaking.disable_builtin: true`, so restructuring `tinkle/v1/`
   does not fail CI or local `buf breaking`. Re-enable on first
   stable release by setting it to `false` (intended stable policy
   is `breaking: FILE`). After re-enabling, intentional breaks need
   a `buf skip breaking` label on the PR, and permanent breaks need
   a new package path (`tinkle/v2/`) rather than mutating `tinkle/v1/`.
7. **Releases use Conventional Commits + release-please.**
   `feat:` → minor, `fix:` → patch; `bump-minor-pre-major` is set, so
   pre-1.0 breaking restructuring bumps the minor. The single schema
   version lives in `version.txt`; tags are plain `vX.Y.Z` and the
   publish job also moves the BSR `main` label to the release.
8. **No `buf generate` for SDKs.** Code generation happens on the
   BSR. The only generation in this repo is docs content:
   `cd website && npm run generate` (descriptor set → Nextra content
   under `website/content/`; `REALTIME.md`/conformance synced as
   guides). Generated outputs are git-ignored; the website repo
   regenerates them from this repo at its own build time.

## When asked to "add a new RPC"

1. Open a PR in this repo (`tinkle-org/schema`) editing the
   relevant `tinkle/v1/*.proto`. Add the request/response messages
   and the method to the appropriate `service` block. Keep the
   Protobuf `package` and `option go_package` lines as they are.
2. The buf-ci action on the PR runs `build`, `lint`, `format`, and
   `breaking` (against the base branch) and posts a summary comment.
   Fix any findings.
3. Merge to `main`. The action validates only. To publish, wait for
   release-please to open/update a Release PR and merge it — that is
   the only path a schema change takes to the BSR.

## When asked to "fix generated code"

Don't try to fix generated SDK code in this repo — the BSR generates
Go/Rust SDKs and there is none in the tree. For the docs reference, fix
the `.proto` doc comments or `website/scripts/generate-reference.mjs`,
then `cd website && npm run generate` and commit the script change
(generated outputs are ignored; the website repo regenerates them at
build time). Rendering/layout of the docs UI lives in
`tinkle-org/tinkle-website-nextjs`, not here.

## Local validation

```bash
buf format -d
buf lint
buf breaking --against ".git#branch=origin/main"
buf build
```

These are the same checks the `buf-ci.yaml` action runs on every PR.
There is no local `buf generate` step for SDKs. For the docs site:

```bash
cd website && npm run generate && npm run check   # content + link validation
```

## CI workflow

- `.github/workflows/buf-ci.yaml` runs `bufbuild/buf-action@v1` with
  `push: false`; on every PR it runs `build`, `lint`, `format`, and
  `breaking`, and posts a PR summary comment keyed on
  `<workflow>:<job>`. On `main` it validates only.
- `.github/workflows/release-please.yaml` maintains Release PRs and
  publishes (gated `buf push`) when a Release PR merge creates a
  release. See `release-please-config.json`, `version.txt`, and
  `.release-please-manifest.json`.
- `.github/workflows/docs-ci.yaml` regenerates + validates the docs
  content on PRs (determinism, internal links). `.github/workflows/docs-build.yaml`
  does the same on merges to `main` and dispatches
  `schema-docs-updated` to the website repo
  (`tinkle-org/tinkle-website-nextjs`), which re-validates the site
  build against the fresh content; the rendered site lives at
  `https://tinkle.me/schema/` and updates with website image releases.

## BSR resource

- Module: <https://buf.build/tinkle-org/schema>
- Generated SDKs: <https://buf.build/tinkle-org/schema/sdks>
- Documentation: <https://buf.build/tinkle-org/schema/docs>
