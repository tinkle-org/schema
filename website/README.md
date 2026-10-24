# Schema docs site

Docusaurus site for the `tinkle.v1` protobuf contract, published at
**https://tinkle.me/schema/** — the main website repo
(`tinkle-org/tinkle-website-nextjs`) consumes the `tinkle-schema-site`
build artifact and serves it under `/schema/`.

## Layout

- `docs/` — hand-written pages (`index.md` landing, `introduction.md`,
  `getting-started/`).
- `docs/reference/` — **generated** by `scripts/generate-reference.mjs`
  from the protobuf descriptor set. Do not edit; git-ignored.
- `docs/guides/` — **generated** by `scripts/sync-docs.mjs` from the
  canonical `REALTIME.md` and `conformance/realtime.md` at the repo root.
  Do not edit; git-ignored.

## Commands

```bash
npm install
npm run generate   # descriptor set → docs/reference/ + synced guides
npm run dev        # dev server at http://localhost:3000/schema/
npm run build      # generate + production build (broken links fail)
npm run build:site # production build only (uses existing generated pages)
npm run typecheck
```

The build targets `url: https://tinkle.me` / `baseUrl: /schema/` (see
`docusaurus.config.ts`). Docs-only mode: the docs plugin owns all routes;
there is no `src/pages/` plugin.
