#!/usr/bin/env node
/**
 * Validate the generated docs content before it is consumed by the main
 * website (tinkle.me/schema/):
 *
 *   1. Every internal `/schema/...` link resolves to an actual content file.
 *   2. The content tree is structurally sane (root index exists; every
 *      directory that appears in the sidebar has a `_meta.js` file).
 *
 * Run after `npm run generate`. Exits non-zero on the first class of errors.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const websiteRoot = path.resolve(scriptDir, '..');
const contentRoot =
  process.env.SCHEMA_CONTENT_DIR ?? path.join(websiteRoot, 'content');

const MOUNT = '/schema';

const errors = [];
const warnings = [];

function* walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else if (/\.(mdx?|md)$/.test(entry.name)) yield full;
  }
}

function resolveLink(href) {
  // /schema          → content/index.mdx
  // /schema/foo/bar  → content/foo/bar.mdx or content/foo/bar/index.mdx
  let rest = href.slice(MOUNT.length);
  if (rest === '' || rest === '/') return path.join(contentRoot, 'index.mdx');
  rest = rest.replace(/\/+$/, '');
  const base = path.join(contentRoot, rest);
  if (fs.existsSync(`${base}.mdx`)) return `${base}.mdx`;
  if (fs.existsSync(`${base}.md`)) return `${base}.md`;
  if (fs.existsSync(path.join(base, 'index.mdx'))) return path.join(base, 'index.mdx');
  return null;
}

function collectLinks(file) {
  const source = fs.readFileSync(file, 'utf8');
  // Skip fenced code blocks so link-like strings in code samples are ignored.
  const outsideFences = source.split(/(```[\s\S]*?```)/g).map((part, i) =>
    i % 2 === 1 ? '' : part,
  ).join('');
  const links = [];
  const re = /\]\(([^)\s]+)\)/g;
  let match;
  while ((match = re.exec(outsideFences))) {
    links.push(match[1]);
  }
  return links;
}

function checkLinks() {
  let checked = 0;
  for (const file of walk(contentRoot)) {
    for (const href of collectLinks(file)) {
      if (/^https?:\/\//.test(href) || href.startsWith('mailto:')) continue;
      if (href.startsWith('#')) continue;
      const [pathPart] = href.split('#');
      if (!pathPart.startsWith(MOUNT) || pathPart === MOUNT && href.length > MOUNT.length && !href.startsWith(`${MOUNT}/`)) {
        // Only enforce site-mounted links; anything else that is neither
        // absolute-external nor an anchor is suspicious.
        errors.push(`${path.relative(contentRoot, file)}: unexpected link target "${href}"`);
        continue;
      }
      if (pathPart === MOUNT || pathPart.startsWith(`${MOUNT}/`)) {
        checked += 1;
        if (!resolveLink(pathPart)) {
          errors.push(`${path.relative(contentRoot, file)}: broken link "${href}"`);
        }
      }
    }
  }
  return checked;
}

function checkStructure() {
  if (!fs.existsSync(path.join(contentRoot, 'index.mdx'))) {
    errors.push('content/index.mdx (landing page) is missing');
  }
  if (!fs.existsSync(path.join(contentRoot, '_meta.js'))) {
    errors.push('content/_meta.js (root sidebar structure) is missing');
  }
  for (const section of ['reference', 'guides']) {
    if (!fs.existsSync(path.join(contentRoot, section))) {
      warnings.push(`content/${section}/ has not been generated yet (run npm run generate)`);
      continue;
    }
    if (!fs.existsSync(path.join(contentRoot, section, '_meta.js'))) {
      errors.push(`content/${section}/_meta.js is missing`);
    }
  }
}

function main() {
  if (!fs.existsSync(contentRoot)) {
    console.error(`check-content: content directory not found at ${contentRoot}`);
    process.exit(1);
  }
  checkStructure();
  const checked = checkLinks();

  for (const w of warnings) console.warn(`check-content: warning: ${w}`);
  if (errors.length) {
    console.error(`check-content: ${errors.length} error(s):`);
    for (const e of errors) console.error(`  ${e}`);
    process.exit(1);
  }
  console.log(`check-content: ok (${checked} internal links resolved across ${contentRoot})`);
}

main();
