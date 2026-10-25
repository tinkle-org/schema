# Schema docs content

Hand-written pages + generators producing the Nextra content for the
`tinkle.v1` protobuf contract docs, rendered by the main website
(`tinkle-org/tinkle-website-nextjs`) at **https://tinkle.me/schema/**.

Reference prose comes from the `.proto` doc comments via the descriptor set.
Hand-written schema overview pages live under `content/`. Runtime transport
bindings are documented in their implementation repositories.

## Layout

- `content/` — the Nextra content directory. This is what the website
  build consumes.
  - Hand-written (committed): `index.mdx` landing, `introduction.mdx`,
    plus `_meta.js` files (page titles; sidebar/pagination disabled).
  - Generated (git-ignored): `reference/` and its `_meta.js` files.
- `scripts/generate-reference.mjs` — descriptor set → reference pages.
- `scripts/sync-docs.mjs` — compatibility cleanup for website builds that still
  invoke the old second generator directly; it no longer publishes guides.
- `scripts/check-content.mjs` — link + structure validation.

## Commands

```bash
npm run generate   # regenerate content/reference/
npm run check      # validate internal /schema/... links + structure
```

No npm dependencies — the scripts use only Node built-ins (plus `buf`
for the descriptor set, which must be on `PATH`).

## Cross-repo contract

The website repo fetches this repo (default ref `main`, overridable via
`SCHEMA_DOCS_REF`) at its build time and runs the same generator scripts
with `--out content` and `--proto-dir <checkout>`. Internal links are
emitted with the `/schema` prefix — that is the path under which the
website mounts this content. The prefix is set by `SCHEMA_LINK_BASE` or
`--link-base` in the generators (read by `check-content` from the env
var); changing it requires updating the website's
`contentDirBasePath` too.

The package script forwards options to the reference generator:

```bash
npm run generate -- --out <content-dir> --proto-dir <checkout> --repo <owner/name> --link-base <prefix>
```

Environment defaults are `SCHEMA_CONTENT_DIR`, `SCHEMA_PROTO_DIR`,
`DOCS_REPO`, and `SCHEMA_LINK_BASE`; the checker reads `SCHEMA_CONTENT_DIR` and
`SCHEMA_LINK_BASE`.
