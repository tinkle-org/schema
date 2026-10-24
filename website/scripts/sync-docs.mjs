#!/usr/bin/env node
/**
 * Publish the canonical repo-level narrative documents as Docusaurus pages.
 *
 * REALTIME.md and conformance/realtime.md stay canonical at the repo root;
 * this script copies them at build time into website/docs/guides/, keeping
 * their relative layout, and rewrites links to files that live outside the
 * docs tree (proto sources, scripts, README) to their GitHub location.
 *
 * The copies are generated artifacts: website/docs/guides/ is git-ignored.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { execFileSync } = require('node:child_process');

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const websiteRoot = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(websiteRoot, '..');
const outGuides = path.join(websiteRoot, 'docs', 'guides');

function gitRepo() {
  const fallback = process.env.DOCS_REPO ?? 'tinkle-org/tinkle-proto';
  try {
    const raw = execFileSync('git', ['config', '--get', 'remote.origin.url'], {
      cwd: repoRoot,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    const match = raw.match(/(?:github\.com[/:])([^/]+)\/([^.@/#]+?)(?:\.git)?$/);
    if (match) return `${match[1]}/${match[2]}`;
  } catch {
    /* fall through */
  }
  return fallback;
}

const REPO = gitRepo();
const GITHUB_MAIN = `https://github.com/${REPO}/blob/main`;

// --------------------------------------------------------------- utilities

function mdEscape(text) {
  return String(text)
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part) =>
      part.startsWith('`')
        ? part
        : part
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/{/g, '&#123;'),
    )
    .join('');
}

/** Strip the first top-level `# heading`; return {title, description, body}. */
function splitTitle(source, title, description) {
  const lines = String(source).split('\n');
  let start = 0;
  while (start < lines.length && lines[start].trim() === '') start += 1;
  if (start < lines.length && lines[start].startsWith('# ')) start += 1;
  const body = lines.slice(start).join('\n').replace(/^\n+/, '');
  return { title, description, body };
}

/** Turn repo-relative source-file links into GitHub links, escape MDX. */
function preprocess(body, { sourceDir }) {
  const rewritten = String(body).replace(
    /\]\(([^)#\s]+)\)/g,
    (match, target) => {
      if (
        /^https?:\/\//.test(target) ||
        target.startsWith('#') ||
        target.startsWith('mailto:')
      ) {
        return match;
      }
      const resolved = path.posix.normalize(path.posix.join(sourceDir, target));
      if (resolved === 'REALTIME.md') {
        return '](/guides/realtime/)';
      }
      if (resolved === 'conformance/realtime.md') {
        return '](/guides/conformance/realtime/)';
      }
      if (resolved.startsWith('tinkle/') || /\.(py|toml|ya?ml|json|txt)$/.test(resolved)) {
        return `](${GITHUB_MAIN}/${resolved})`;
      }
      return match;
    },
  );
  return mdEscape(rewritten);
}

function writeFile(rel, front, content) {
  const file = path.join(outGuides, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, front + content, 'utf8');
}

// ----------------------------------------------------------------- actions

function main() {
  fs.rmSync(outGuides, { recursive: true, force: true });
  fs.mkdirSync(outGuides, { recursive: true });

  fs.writeFileSync(
    path.join(outGuides, '_category_.json'),
    JSON.stringify({ label: 'Guides', position: 6, link: { type: 'doc', id: 'guides/realtime' } }, null, 2) + '\n',
    'utf8',
  );

  const realtime = fs.readFileSync(path.join(repoRoot, 'REALTIME.md'), 'utf8');
  const conformance = fs.readFileSync(
    path.join(repoRoot, 'conformance', 'realtime.md'),
    'utf8',
  );

  const rt = splitTitle(
    realtime,
    'Realtime application binding',
    'The Syntra-only realtime application binding: normative requirements.',
  );
  writeFile(
    'realtime.mdx',
    '---\n' +
      `title: "${String(rt.title).replace(/"/g, '\\"')}"\n` +
      `description: "${String(rt.description).replace(/"/g, '\\\\"')}"\n` +
      'sidebar_position: 1\n' +
      '---\n',
    preprocess(rt.body, { sourceDir: '.' }),
  );

  const cf = splitTitle(
    conformance,
    'Realtime schema conformance',
    'Implementation checks for the batched realtime binding.',
  );
  writeFile(
    'conformance/realtime.mdx',
    '---\n' +
      `title: "${String(cf.title).replace(/"/g, '\\"')}"\n` +
      `description: "${String(cf.description).replace(/"/g, '\\\\"')}"\n` +
      'sidebar_position: 2\n' +
      '---\n',
    preprocess(cf.body, { sourceDir: 'conformance' }),
  );

  console.log(`sync-docs: published REALTIME.md and conformance/realtime.md into docs/guides/ (repo ${REPO})`);
}

main();
