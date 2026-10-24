#!/usr/bin/env node
/**
 * Shared helpers for the schema docs generators.
 *
 * `generate-reference.mjs` and `sync-docs.mjs` previously duplicated the
 * CLI/`LINK_BASE` handling, the repository-slug detection, and the MDX
 * escaping. They now import from here so the two generators cannot drift
 * on escaping or link rules.
 */

import { execFileSync } from 'node:child_process';
import path from 'node:path';

/** Return the value following `name` in an argv array, or undefined. */
export function cliArg(argv, name) {
  const i = argv.indexOf(name);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : undefined;
}

/** Explicit repository override from CLI or env, before any Git probing. */
export function explicitRepo(argv) {
  return cliArg(argv, '--repo') ?? process.env.DOCS_REPO;
}

/**
 * Resolve the `owner/name` slug used for Source links.
 * Honors the explicit `--repo` option (and `DOCS_REPO`) before probing
 * Git, so generated Source links can be redirected in a checkout with
 * a remote.
 */
export function resolveRepoSlug({ argv, repoRootArg, fallback = 'tinkle-org/schema' }) {
  const explicit = explicitRepo(argv);
  if (explicit) return explicit;
  try {
    const raw = execFileSync('git', ['config', '--get', 'remote.origin.url'], {
      cwd: repoRootArg,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    const match = raw.match(/(?:github\.com[/:])([^/]+)\/([^/@#]+?)(?:\.git)?$/);
    if (match) return `${match[1]}/${match[2]}`;
  } catch {
    /* fall through to fallback */
  }
  return fallback;
}

/** Link-base prefix for generated `/schema/...` links. */
export function resolveLinkBase(argv) {
  return (cliArg(argv, '--link-base') ?? process.env.SCHEMA_LINK_BASE ?? '/schema').replace(/\/+$/, '');
}

/** Repository root containing the protobuf source. */
export function resolveRepoRoot(argv, websiteRoot) {
  return cliArg(argv, '--proto-dir') ?? process.env.SCHEMA_PROTO_DIR ?? path.resolve(websiteRoot, '..');
}

/** Nextra content root. */
export function resolveContentRoot(argv, websiteRoot) {
  return cliArg(argv, '--out') ?? process.env.SCHEMA_CONTENT_DIR ?? path.join(websiteRoot, 'content');
}

/**
 * Escape text for MDX: protect fenced code blocks and inline code spans,
 * escape characters that MDX would treat as JSX/HTML everywhere else.
 */
export function mdEscape(text) {
  const source = String(text);
  const re = /```[\s\S]*?```|(`+)[^\n]*?\1/g;
  let last = 0;
  let out = '';
  let m;
  const escapePart = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/{/g, '&#123;');
  while ((m = re.exec(source)) !== null) {
    if (m.index > last) out += escapePart(source.slice(last, m.index));
    out += m[0];
    last = m.index + m[0].length;
    if (m[0].length === 0) re.lastIndex += 1;
  }
  if (last < source.length) out += escapePart(source.slice(last));
  return out;
}
