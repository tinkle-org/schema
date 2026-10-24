# Schema docs content

Hand-written pages + generators producing the Nextra content for the
`tinkle.v1` protobuf contract docs, rendered by the main website
(`tinkle-org/tinkle-website-nextjs`) at **https://tinkle.me/schema/**.

## Layout

- `content/` — the Nextra content directory. This is what the website
  build consumes.
  - Hand-written (committed): `index.mdx` landing, `introduction.mdx`,
    plus `_meta.js` files (page titles; sidebar/pagination disabled).
  - Generated (git-ignored): `reference/`, `guides/` and their
    `_meta.js` files.
- `scripts/generate-reference.mjs` — descriptor set → reference pages.
- `scripts/sync-docs.mjs` — canonical `REALTIME.md` /
  `conformance/realtime.md` → guides.
- `scripts/check-content.mjs` — link + structure validation.

## Commands

```bash
npm run generate   # regenerate content/reference/ + content/guides/
npm run check      # validate internal /schema/... links + structure
```

No npm dependencies — the scripts use only Node built-ins (plus `buf`
for the descriptor set, which must be on `PATH`).

## Cross-repo contract

The website repo fetches this repo (default ref `main`, overridable via
`SCHEMA_DOCS_REF`) at its build time and runs the same generator scripts
with `--out content` and `--proto-dir <checkout>`. Internal links are
emitted with the `/schema` prefix — that is the path under which the
website mounts this content. Changing the prefix requires updating the
website's `contentDirBasePath` too.
