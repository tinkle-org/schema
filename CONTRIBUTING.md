# Contributing to tinkle-proto

## Source of truth

The `.proto` files under `tinkle/v1/` are maintained **directly in this
repository**. There is no mirror: do not open PRs against other
repositories to change the contract.

## How a proto change flows to consumers

1. PR against `main` editing `tinkle/v1/*.proto`. CI runs
   `build`/`lint`/`format`/`breaking` and posts a summary comment.
2. Merge to `main`. **Nothing is published to the BSR yet** — plain
   merges validate only. The docs site artifact rebuilds automatically
   from the merge (`docs-build` workflow).
3. release-please maintains a Release PR containing
   `version.txt` and `CHANGELOG.md` bumps, assembled from Conventional
   Commits since the last release.
4. **Merging the Release PR publishes:** the release workflow checks
   out the released commit, validates it (`buf build`, `buf lint`),
   and `buf push`es it to
   [buf.build/tinklecorp/tinkle-proto](https://buf.build/tinklecorp/tinkle-proto)
   labeled with the release tag (and the `main` default label).
   Consumers then pick up regenerated Go/Rust SDKs via `go get @latest`
   or `cargo add --registry buf`.

## Conventional Commits

Releases are driven by [Conventional Commits](https://www.conventionalcommits.org/).
Use standard prefixes so release-please picks the right bump:

| Prefix | SemVer bump | Notes |
|---|---|---|
| `feat:` | MINOR | New RPC, new message, new field |
| `fix:` | PATCH | Behavior-preserving contract fix |
| `feat!:` / `BREAKING CHANGE:` | MAJOR (pre-1.0: minor, via `bump-minor-pre-major`) | Pre-release restructuring intended |
| `perf:` | PATCH | — |
| `docs:` / `chore:` / `ci:` / `refactor:` / `test:` / `style:` / `build:` | — (no release) | Never trigger a release |

## Documentation site

The [docs content](website/) — rendered at `https://tinkle.me/schema/` by
the main website — generates its API reference from the protobuf
descriptor set on every build — **do not hand-write reference pages**. To
change reference content, edit the `.proto` doc comments (every message,
field, enum value, service and method's leading `//` comment) or, for
generator behavior, `website/scripts/generate-reference.mjs`.

Narrative documents stay canonical at the repo root (`REALTIME.md`,
`conformance/realtime.md`) and are synced into the content at build time;
edit them there. Hand-written site pages live in `website/content/`.

Content commands (from `website/`; no dependencies to install):

```bash
npm run generate   # descriptor set → content/reference/ + synced guides
npm run check      # internal /schema/... links resolve; structure is sane
```

To preview the rendered result, build the website repo locally
(`tinkle-org/tinkle-website-nextjs`) — it fetches this repo and runs the
same generators before its own build.

Generated outputs are git-ignored and rebuilt on every build — do not
commit them.

## Cutting a release

1. **Do not push release tags manually.** release-please owns tags.
2. Once enough `feat:`/`fix:`/`perf:` commits land on `main`,
   release-please opens or updates a Release PR (`chore: release X.Y.Z`)
   bumping `version.txt` and `CHANGELOG.md`.
3. Review and merge the Release PR. The release workflow then:
   - tags the release,
   - checks out the released sha,
   - validates (`buf build`, `buf lint`),
   - publishes to the BSR with the release tag label.
4. Consumers pick up new SDK versions from the BSR; the docs site
   reference is already updated (it follows `main`, not releases).

## Hotfixing a release

To force a specific version, push an empty commit with a
`Release-As: X.Y.Z` trailer so release-please opens a Release PR at that
version:

```bash
git commit --allow-empty -m "chore: release X.Y.Z" -m "Release-As: X.Y.Z"
git push origin HEAD
```

## Common tasks

| Task | Where |
|---|---|
| Add/change an RPC or message | `tinkle/v1/*.proto` here |
| Docs content generation/checks | `website/scripts/*.mjs` |
| Narrative/protocol docs | `REALTIME.md`, `conformance/realtime.md` |
| Add conformance checks | `conformance/test_realtime_schema.py` |
| Adjust release behavior | `release-please-config.json`, `.github/workflows/release-please.yaml` |
| Docs styling/navigation | `tinkle-org/tinkle-website-nextjs` (not this repo) |
