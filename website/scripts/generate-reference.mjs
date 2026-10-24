#!/usr/bin/env node
/**
 * Generate the tinkle.v1 schema reference docs from the protobuf descriptor set.
 *
 * Pipeline:
 *   1. `buf build --as-file-descriptor-set -o -#format=json` — emits a
 *      FileDescriptorSet as JSON, including source comments and locations.
 *   2. Walk every tinkle/ file (imported google.protobuf types are indexed too,
 *      for linking) and emit one Nextra MDX page per service, RPC method,
 *      message and enum, plus an index page and Nextra `_meta.js` files for
 *      sidebar structure.
 *
 * Output targets a Nextra `content/` directory (consumed by the main website
 * at tinkle.me/schema/ — see tinkle-org/tinkle-website-nextjs). Paths:
 *   --out <dir>        content root (default: <repo>/website/content)
 *   --proto-dir <dir>  protobuf source root (default: <repo>)
 *   --repo owner/name  repository slug used for "Source" links
 *
 * Internal links are emitted as `/schema/...` (the site-root path under which
 * the main website mounts this content). Output is deterministic: identical
 * descriptor input produces identical output. Stale generated files are
 * deleted before writing.
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const websiteRoot = path.resolve(scriptDir, '..');

// -- CLI ------------------------------------------------------------------

const argv = process.argv.slice(2);
function arg(name) {
  const i = argv.indexOf(name);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : undefined;
}

const repoRootArg = arg('--proto-dir') ?? process.env.SCHEMA_PROTO_DIR ?? path.resolve(websiteRoot, '..');
const contentRoot =
  arg('--out') ?? process.env.SCHEMA_CONTENT_DIR ?? path.join(websiteRoot, 'content');
const outDocs = path.join(contentRoot, 'reference');
const LINK_BASE = (arg('--link-base') ?? process.env.SCHEMA_LINK_BASE ?? '/schema').replace(/\/+$/, '');

const PACKAGE = 'tinkle.v1';
const PKG_PREFIX = `${PACKAGE}.`;
const WKB_DOCS_URL = 'https://protobuf.dev/reference/protobuf/google.protobuf/';

// ---------------------------------------------------------------------------
// Repository id (for source links)
// ---------------------------------------------------------------------------

function resolveRepo() {
  const fallback = arg('--repo') ?? process.env.DOCS_REPO ?? 'tinkle-org/schema';
  try {
    const raw = execFileSync('git', ['config', '--get', 'remote.origin.url'], {
      cwd: repoRootArg,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    const match = raw.match(/(?:github\.com[/:])([^/]+)\/([^.@/#]+?)(?:\.git)?$/);
    if (match) return `${match[1]}/${match[2]}`;
  } catch {
    /* fall through to fallback */
  }
  return fallback;
}

const REPO = resolveRepo();
const GITHUB_MAIN = `https://github.com/${REPO}/blob/main`;

// ---------------------------------------------------------------------------
// Descriptor input
// ---------------------------------------------------------------------------

function buildDescriptorSet() {
  const stdout = execFileSync(
    'buf',
    ['build', '--as-file-descriptor-set', '-o', '-#format=json'],
    { cwd: repoRootArg, maxBuffer: 1 << 26, encoding: 'utf8' },
  );
  return JSON.parse(stdout);
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

const registry = new Map(); // fullName -> entry
const files = new Map(); // filename -> {file, comments}
const services = []; // {name, full, file, svc}

function commentMap(fileDescriptor) {
  const map = new Map();
  for (const loc of fileDescriptor.sourceCodeInfo?.location ?? []) {
    // protojson omits empty repeated fields: file-level comments (path []) have
    // no "path" key. Normalize to [].
    map.set((loc.path ?? []).join(','), loc);
  }
  return map;
}

function indexMessages(file, messages, pathPrefix, parentFull) {
  messages.forEach((msg, i) => {
    const commentPath = [...pathPrefix, i];
    const full = `${parentFull}.${msg.name}`;
    const isSynthetic = Boolean(msg.options?.mapEntry);
    registry.set(full, {
      kind: 'message',
      full,
      short: msg.name,
      file: file.name,
      parentFull,
      msg,
      commentPath,
      isSynthetic,
    });
    if (msg.nestedType?.length) {
      indexMessages(file, msg.nestedType, [...commentPath, 3], full);
    }
    (msg.enumType ?? []).forEach((en, j) => {
      const eFull = `${full}.${en.name}`;
      registry.set(eFull, {
        kind: 'enum',
        full: eFull,
        short: en.name,
        file: file.name,
        parentFull: full,
        en,
        commentPath: [...commentPath, 4, j],
      });
    });
  });
}

function index() {
  const image = buildDescriptorSet();
  for (const file of image.file ?? []) {
    files.set(file.name, { file, comments: commentMap(file) });
    indexMessages(file, file.messageType ?? [], [4], file.package);
    (file.enumType ?? []).forEach((en, i) => {
      registry.set(`${file.package}.${en.name}`, {
        kind: 'enum',
        full: `${file.package}.${en.name}`,
        short: en.name,
        file: file.name,
        parentFull: file.package,
        en,
        commentPath: [5, i],
      });
    });
    (file.service ?? []).forEach((svc, i) => {
      const full = `${file.package}.${svc.name}`;
      registry.set(full, {
        kind: 'service',
        full,
        short: svc.name,
        file: file.name,
        parentFull: file.package,
        svc,
        commentPath: [6, i],
      });
      services.push({ name: svc.name, full, file: file.name, svc });
    });
  }
  services.sort((a, b) => a.name.localeCompare(b.name));
}

// ---------------------------------------------------------------------------
// Comment access
// ---------------------------------------------------------------------------

function leading(full, suffixPath) {
  const entry = registry.get(full);
  if (!entry) return '';
  const fmap = files.get(entry.file);
  const loc = fmap?.comments.get([...entry.commentPath, ...suffixPath].join(','));
  if (!loc) return '';
  return (loc.leadingComments ?? '') || (loc.trailingComments ?? '');
}

// ---------------------------------------------------------------------------
// Escaping helpers
// ---------------------------------------------------------------------------

function mdEscape(text) {
  // Protect fenced code blocks and inline code spans; escape characters that
  // MDX would treat as JSX/HTML everywhere else.
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

function cell(text) {
  return mdEscape(text)
    .replace(/\|/g, '\\|')
    .replace(/\r?\n/g, '<br/>');
}

function yamlQuote(text) {
  return String(text)
    .trim()
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\r?\n/g, ' ');
}

const SCALARS = {
  TYPE_DOUBLE: 'double',
  TYPE_FLOAT: 'float',
  TYPE_INT64: 'int64',
  TYPE_UINT64: 'uint64',
  TYPE_INT32: 'int32',
  TYPE_FIXED64: 'fixed64',
  TYPE_FIXED32: 'fixed32',
  TYPE_BOOL: 'bool',
  TYPE_STRING: 'string',
  TYPE_BYTES: 'bytes',
  TYPE_UINT32: 'uint32',
  TYPE_SFIXED32: 'sfixed32',
  TYPE_SFIXED64: 'sfixed64',
  TYPE_SINT32: 'sint32',
  TYPE_SINT64: 'sint64',
};

// ---------------------------------------------------------------------------
// Links and type rendering
// ---------------------------------------------------------------------------

function isOwned(entry) {
  return !entry.file.startsWith('google/');
}

function linkFor(full) {
  const entry = registry.get(full);
  if (!entry) return null;
  if (!isOwned(entry)) {
    return { text: full, url: WKB_DOCS_URL };
  }
  const rest = full.slice(PKG_PREFIX.length);
  return {
    text: rest,
    url: `${LINK_BASE}/reference/${entry.kind === 'enum' ? 'enums' : 'messages'}/${rest}`,
  };
}

function typeLink(full) {
  const entry = registry.get(full);
  const name = full.slice(PKG_PREFIX.length) || full;
  if (!entry) return `\`${name}\``;
  if (!isOwned(entry)) return `[${full}](${WKB_DOCS_URL})`;
  return `[${name}](${linkFor(full).url})`;
}

function inlineScalarOrLink(field) {
  if (field.type === 'TYPE_MESSAGE' || field.type === 'TYPE_ENUM') {
    return typeLink(field.typeName.replace(/^\./, ''));
  }
  return `\`${SCALARS[field.type] ?? field.type}\``;
}

function renderFieldType(field) {
  const repeated = field.label === 'LABEL_REPEATED' || field.label === 3;
  let base;
  if (field.type === 'TYPE_MESSAGE' || field.type === 'TYPE_GROUP') {
    const full = field.typeName.replace(/^\./, '');
    const target = registry.get(full);
    if (target?.isSynthetic) {
      const key = target.msg.field.find((f) => f.number === 1);
      const value = target.msg.field.find((f) => f.number === 2);
      base = `map<${inlineScalarOrLink(key)}, ${inlineScalarOrLink(value)}>`;
    } else {
      base = typeLink(full);
    }
  } else if (field.type === 'TYPE_ENUM') {
    base = typeLink(field.typeName.replace(/^\./, ''));
  } else {
    base = `\`${SCALARS[field.type] ?? field.type}\``;
  }
  const withOptional = field.proto3Optional ? `optional ${base}` : base;
  return repeated ? `repeated ${withOptional}` : withOptional;
}

// ---------------------------------------------------------------------------
// Slugs
// ---------------------------------------------------------------------------

function slugify(name) {
  return (
    name
      .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .toLowerCase()
      .replace(/^-+|-+$/g, '') || 'index'
  );
}

const serviceSlugMap = new Map();
function buildServiceSlugs() {
  const seen = new Map();
  for (const s of services) {
    const base = slugify(s.name.replace(/Service$/, '')) || slugify(s.name);
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    serviceSlugMap.set(s.name, n > 1 ? `${base}-service` : base);
  }
}

function methodSlug(name) {
  return slugify(name);
}

// ---------------------------------------------------------------------------
// Cross references ("Referenced by")
// ---------------------------------------------------------------------------

const refs = new Map(); // targetFull -> [{label, url, note}]

function addRef(targetFull, ref) {
  const target = registry.get(targetFull);
  if (!target || target.isSynthetic) return;
  if (targetFull === ref.sourceFull) return;
  const list = refs.get(targetFull) ?? [];
  list.push(ref);
  refs.set(targetFull, list);
}

function collectRefs() {
  for (const entry of registry.values()) {
    if (entry.kind === 'service' || !isOwned(entry)) continue;
    const ownerBase = `${LINK_BASE}/reference/${entry.kind === 'enum' ? 'enums' : 'messages'}/${entry.full.slice(PKG_PREFIX.length)}`;
    const fields = entry.kind === 'message' ? entry.msg.field ?? [] : [];
    for (const field of fields) {
      if (['TYPE_MESSAGE', 'TYPE_GROUP', 'TYPE_ENUM'].includes(field.type)) {
        const targetFull = field.typeName.replace(/^\./, '');
        addRef(targetFull, {
          label: `${entry.short}.${field.name}`,
          url: ownerBase,
          note: 'field',
          sourceFull: entry.full,
        });
        const target = registry.get(targetFull);
        if (target?.isSynthetic) {
          for (const inner of target.msg.field ?? []) {
            if (['TYPE_MESSAGE', 'TYPE_ENUM'].includes(inner.type)) {
              addRef(inner.typeName.replace(/^\./, ''), {
                label: `${entry.short}.${field.name}`,
                url: ownerBase,
                note: 'field',
                sourceFull: entry.full,
              });
            }
          }
        }
      }
    }
  }
  for (const s of services) {
    const url = `${LINK_BASE}/reference/methods/${serviceSlugMap.get(s.name)}`;
    for (const m of s.svc.method ?? []) {
      const methodUrl = `${url}/${methodSlug(m.name)}`;
      addRef(m.inputType.replace(/^\./, ''), {
        label: `${s.name}.${m.name}`,
        url: methodUrl,
        note: 'request',
        sourceFull: s.full,
      });
      addRef(m.outputType.replace(/^\./, ''), {
        label: `${s.name}.${m.name}`,
        url: methodUrl,
        note: 'response',
        sourceFull: s.full,
      });
    }
  }
}

function referencedBy(full) {
  const list = refs.get(full) ?? [];
  if (!list.length) return '';
  const rows = [...list]
    .sort((a, b) =>
      a.note === b.note
        ? a.label.localeCompare(b.label)
        : a.note.localeCompare(b.note),
    )
    .map((r) =>
      `- [\`${r.label}\`](${r.url})${r.note === 'field' ? '' : ` — **${r.note}**`}`,
    );
  return `### Referenced by\n\n${rows.join('\n')}\n`;
}

// ---------------------------------------------------------------------------
// Emission helpers
// ---------------------------------------------------------------------------

function writePage(rel, { title, description = '', asIndexPage = false }, body) {
  const file = path.join(outDocs, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const front =
    '---\n' +
    `title: "${yamlQuote(title)}"\n` +
    (description ? `description: "${yamlQuote(description)}"\n` : '') +
    (asIndexPage ? 'asIndexPage: true\n' : '') +
    '---\n';
  fs.writeFileSync(file, front + body, 'utf8');
}

/** Emit a Nextra `_meta.js` for sidebar structure/ordering. */
function writeMeta(dir, entries) {
  const file = path.join(outDocs, dir, '_meta.js');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const lines = Object.entries(entries).map(([key, value]) => {
    if (typeof value === 'string') return `  ${JSON.stringify(key)}: ${JSON.stringify(value)},`;
    // Object form: { title, items? }
    const props = [`title: ${JSON.stringify(value.title)}`];
    return `  ${JSON.stringify(key)}: { ${props.join(', ')} },`;
  });
  fs.writeFileSync(
    file,
    `// Generated by website/scripts/generate-reference.mjs — do not edit.\nexport default {\n${lines.join('\n')}\n}\n`,
    'utf8',
  );
}

function firstSentence(text) {
  const clean = String(text ?? '').replace(/\s+/g, ' ').trim();
  const m = clean.match(/^(.{0,240}?[.!?])(?:\s|$)/);
  return m ? m[1] : clean.split('\n')[0] ?? '';
}

function sourceLine(file) {
  return `**Source:** [\`${file}\`](${GITHUB_MAIN}/${file})`;
}

function shortName(full) {
  return full.slice(PKG_PREFIX.length);
}

// ---------------------------------------------------------------------------
// Field tables
// ---------------------------------------------------------------------------

function camel(name) {
  return name.replace(/_([a-zA-Z0-9])/g, (_, c) => c.toUpperCase());
}

function realOneofName(msg, field) {
  if (field.oneofIndex == null || field.proto3Optional) return null;
  const oneof = msg.oneofDecl?.[field.oneofIndex];
  return oneof?.name ?? null;
}

// Build the markdown field table for a message (including oneof usage).
function buildFieldTable(full) {
  const entry = registry.get(full);
  const msg = entry.msg;
  const usesOneof = (msg.field ?? []).some((f) => realOneofName(msg, f));
  const rows = (msg.field ?? []).map((field, fi) => {
    const comment = leading(full, [2, fi]).trim();
    const deprecated = field.options?.deprecated ? ' — **deprecated**' : '';
    const jsonNote =
      field.jsonName && field.jsonName !== camel(field.name)
        ? ` *(json: \`${field.jsonName}\`)*`
        : '';
    const oneofName = realOneofName(msg, field);
    const oneofNote = oneofName ? `<br/>*(oneof \`${oneofName}\`)*` : '';
    return (
      `| ${field.number} | \`${field.name}\`${jsonNote}${oneofNote} | ${renderFieldType(field)} | ${cell(comment)}${deprecated} |`
    );
  });
  const table =
    '| No. | Name | Type | Description |\n| --- | --- | --- | --- |\n' +
    rows.join('\n') +
    '\n';
  return { table, usesOneof };
}

// ---------------------------------------------------------------------------
// Pages: services
// ---------------------------------------------------------------------------

function writeServicePages() {
  services.forEach((service, si) => {
    const slug = serviceSlugMap.get(service.name);
    const body = [];
    const desc = leading(service.full, []).trim();
    body.push(`# ${service.name}\n\n`);
    if (desc) body.push(mdEscape(desc) + '\n\n');
    body.push(sourceLine(service.file) + ' · package `tinkle.v1`\n\n');
    body.push('## RPC methods\n\n');
    body.push('| Method | Request | Response |\n| --- | --- | --- |\n');
    (service.svc.method ?? []).forEach((method) => {
      const methodUrl = `${LINK_BASE}/reference/methods/${slug}/${methodSlug(method.name)}`;
      const reqFull = method.inputType.replace(/^\./, '');
      const respFull = method.outputType.replace(/^\./, '');
      const streaming = [];
      if (method.clientStreaming) streaming.push('client streaming');
      if (method.serverStreaming) streaming.push('server streaming');
      const label = streaming.length ? `${method.name} (${streaming.join(', ')})` : method.name;
      body.push(
        `| [\`${label}\`](${methodUrl}) | ${typeLink(reqFull)} | ${typeLink(respFull)} |\n`,
      );
    });

    writePage(
      `services/${slug}.mdx`,
      {
        title: service.name,
        description: firstSentence(desc) || `The ${PACKAGE}.${service.name} gRPC service.`,
      },
      body.join(''),
    );
  });
}

// ---------------------------------------------------------------------------
// Pages: methods
// ---------------------------------------------------------------------------

function writeMethodPages() {
  services.forEach((service, si) => {
    const slug = serviceSlugMap.get(service.name);
    const methods = (service.svc.method ?? [])
      .map((m, mi) => ({ m, mi }))
      .sort((a, b) => a.m.name.localeCompare(b.m.name));

    methods.forEach(({ m, mi }) => {
      const reqFull = m.inputType.replace(/^\./, '');
      const respFull = m.outputType.replace(/^\./, '');
      const desc = leading(service.full, [2, mi]).trim();

      const body = [];
      body.push(`# ${m.name}\n\n`);
      if (desc) body.push(mdEscape(desc) + '\n\n');
      body.push(
        `**Service:** [\`${service.name}\`](${LINK_BASE}/reference/services/${slug}) · ` +
          sourceLine(service.file) +
          ' · package `tinkle.v1`\n\n',
      );
      const streaming = [];
      if (m.clientStreaming) streaming.push('client-streaming');
      if (m.serverStreaming) streaming.push('server-streaming');
      const streamMark = streaming.length ? `, ${streaming.join(', ')}` : '';
      body.push(
        `\`\`\`proto\nrpc ${m.name}(${shortName(reqFull)}) returns (${shortName(respFull)})${streamMark};\n\`\`\`\n\n`,
      );
      if (m.options?.deprecated) {
        body.push('**Deprecated method.**\n\n');
      }

      body.push(`## Request — ${shortName(reqFull)}\n\n`);
      const reqEntry = registry.get(reqFull);
      if ((reqEntry?.msg.field ?? []).length <= 24) {
        body.push(buildFieldTable(reqFull).table + '\n');
      } else {
        body.push('_Large message — see the full definition below._\n\n');
      }
      body.push(`Full definition: ${typeLink(reqFull)}\n\n`);

      body.push(`## Response — ${shortName(respFull)}\n\n`);
      const respEntry = registry.get(respFull);
      if ((respEntry?.msg.field ?? []).length <= 24) {
        body.push(buildFieldTable(respFull).table + '\n');
      } else {
        body.push('_Large message — see the full definition below._\n\n');
      }
      body.push(`Full definition: ${typeLink(respFull)}\n\n`);

      writePage(
        `methods/${slug}/${methodSlug(m.name)}.mdx`,
        {
          title: `${service.name}.${m.name}`,
          description: firstSentence(desc) || `The ${PACKAGE}.${service.name}.${m.name} RPC.`,
        },
        body.join(''),
      );
    });
  });
}

// ---------------------------------------------------------------------------
// Pages: messages
// ---------------------------------------------------------------------------

function writeMessagePages() {
  const messages = [...registry.values()].filter(
    (e) => e.kind === 'message' && isOwned(e) && !e.isSynthetic,
  );
  messages.sort((a, b) => a.full.localeCompare(b.full));

  messages.forEach((entry) => {
    const rest = entry.full.slice(PKG_PREFIX.length);
    const body = [];
    const desc = leading(entry.full, []).trim();
    const { table, usesOneof } = buildFieldTable(entry.full);

    body.push(`# \`${rest}\`\n\n`);
    if (desc) body.push(mdEscape(desc) + '\n\n');
    if (entry.msg.options?.deprecated) {
      body.push('**Deprecated message.**\n\n');
    }
    body.push(sourceLine(entry.file) + ' · package `tinkle.v1`\n\n');
    body.push('## Fields\n\n');
    body.push(table + '\n');

    if (usesOneof) {
      body.push('### Oneofs\n\n');
      (entry.msg.oneofDecl ?? []).forEach((oneof, idx) => {
        const members = (entry.msg.field ?? []).filter(
          (f) => f.oneofIndex === idx && !f.proto3Optional,
        );
        if (!members.length) return;
        body.push(
          `- **\`${oneof.name}\`:** ${members.map((f) => `\`${f.name}\``).join(', ')}\n`,
        );
      });
      body.push('\n');
    }

    body.push(ReservedSectionFromEntry(entry));

    const nestedMsgs = (entry.msg.nestedType ?? []).filter((m) => !m.options?.mapEntry);
    const nestedEnums = entry.msg.enumType ?? [];
    if (nestedMsgs.length || nestedEnums.length) {
      body.push('### Nested types\n\n');
      for (const m of nestedMsgs) {
        body.push(`- ${typeLink(`${entry.full}.${m.name}`)} — message\n`);
      }
      for (const e of nestedEnums) {
        body.push(`- ${typeLink(`${entry.full}.${e.name}`)} — enum\n`);
      }
      body.push('\n');
    }

    const rb = referencedBy(entry.full);
    if (rb) body.push(rb + '\n');

    writePage(
      `messages/${rest}.mdx`,
      {
        title: rest,
        description: firstSentence(desc) || `The ${entry.full} message.`,
      },
      body.join(''),
    );
  });
}

function ReservedSectionFromEntry(entry) {
  const msg = entry.msg;
  const ranges = (msg.reserved_range ?? msg.reservedRange ?? []).map((r) =>
    r.end != null && r.end - 1 > r.start ? `${r.start}–${r.end - 1}` : `${r.start}`,
  );
  const names = msg.reserved_name ?? msg.reservedName ?? [];
  if (!ranges.length && !names.length) return '';
  const parts = [];
  if (ranges.length) {
    parts.push(`field numbers ${ranges.map((r) => `\`${r}\``).join(', ')}`);
  }
  if (names.length) {
    parts.push(`field names ${names.map((n) => `\`${n}\``).join(', ')}`);
  }
  return `### Reserved\n\nReserved ${parts.join(' · ')} — these tags and identifiers are retired and must never be reused.\n\n`;
}

// ---------------------------------------------------------------------------
// Pages: enums
// ---------------------------------------------------------------------------

function writeEnumPages() {
  const enums = [...registry.values()].filter(
    (e) => e.kind === 'enum' && isOwned(e),
  );
  enums.sort((a, b) => a.full.localeCompare(b.full));

  enums.forEach((entry) => {
    const rest = entry.full.slice(PKG_PREFIX.length);
    const body = [];
    const desc = leading(entry.full, []).trim();
    body.push(`# \`${rest}\`\n\n`);
    if (desc) body.push(mdEscape(desc) + '\n\n');
    body.push(sourceLine(entry.file) + ' · package `tinkle.v1`\n\n');
    body.push('## Values\n\n');
    body.push('| No. | Value | Description |\n| --- | --- | --- |\n');
    (entry.en.value ?? []).forEach((value, vi) => {
      const comment = leading(entry.full, [2, vi]).trim();
      const deprecated = value.options?.deprecated ? ' — **deprecated**' : '';
      body.push(`| ${value.number} | \`${value.name}\` | ${cell(comment)}${deprecated} |\n`);
    });
    body.push('\n');
    const rb = referencedBy(entry.full);
    if (rb) body.push(rb + '\n');

    writePage(
      `enums/${rest}.mdx`,
      {
        title: rest,
        description: firstSentence(desc) || `The ${entry.full} enum.`,
      },
      body.join(''),
    );
  });
}

// ---------------------------------------------------------------------------
// Index page + sidebar structure
// ---------------------------------------------------------------------------

function writeIndexPage() {
  const ownedFiles = [...files.keys()].filter((f) => f.startsWith('tinkle/'));
  const messageCount = [...registry.values()].filter(
    (e) => e.kind === 'message' && isOwned(e) && !e.isSynthetic,
  ).length;
  const enumCount = [...registry.values()].filter(
    (e) => e.kind === 'enum' && isOwned(e),
  ).length;
  const methodCount = services.reduce(
    (sum, s) => sum + (s.svc.method ?? []).length,
    0,
  );

  const body = [];
  body.push('# Schema reference\n\n');
  body.push(
    mdEscape(
      'Generated from the tinkle.v1 protobuf source. Every page here is derived ' +
        'from the descriptor set, including doc comments, deprecations and reserved definitions.',
    ) +
      '\n\n',
  );
  body.push(
    `**${services.length}** services · **${methodCount}** RPC methods · **${messageCount}** messages · **${enumCount}** enums · **${ownedFiles.length}** source files.\n\n`,
  );
  body.push('## Services\n\n');
  for (const s of services) {
    const slug = serviceSlugMap.get(s.name);
    const count = (s.svc.method ?? []).length;
    body.push(
      `- [${s.name}](${LINK_BASE}/reference/services/${slug}) — ${count} method${count === 1 ? '' : 's'}\n`,
    );
  }
  body.push('\n');
  body.push(
    'Every service, message and enum has its own page; method pages inline ' +
      'compact field tables for request and response types.\n\n',
  );
  body.push(
    mdEscape(
      'This reference regenerates on every site build from the protobuf source of truth and reflects the current schema. Published SDK changes are gated to schema releases (see the introduction).',
    ) +
      '\n',
  );

  writePage(
    'index.mdx',
    {
      title: 'Schema reference',
      description:
        'Generated tinkle.v1 API reference: services, RPC methods, messages and enums.',
      asIndexPage: true,
    },
    body.join(''),
  );
}

function writeSidebarMeta() {
  // Note: the folder index page (reference/index.mdx, `asIndexPage: true`)
  // is represented by the parent-level `reference` key, not an `index`
  // child item — Nextra validates meta keys against folder children.
  writeMeta('', {
    services: { title: 'Services' },
    methods: { title: 'Methods' },
    messages: { title: 'Messages' },
    enums: { title: 'Enums' },
  });
  writeMeta('methods', Object.fromEntries(
    services.map((s) => [serviceSlugMap.get(s.name), { title: s.name }]),
  ));
}

// ---------------------------------------------------------------------------

function main() {
  index();
  buildServiceSlugs();
  collectRefs();

  fs.rmSync(outDocs, { recursive: true, force: true });
  fs.mkdirSync(outDocs, { recursive: true });

  writeIndexPage();
  writeServicePages();
  writeMethodPages();
  writeMessagePages();
  writeEnumPages();
  writeSidebarMeta();

  const methodCount = services.reduce((sum, s) => sum + (s.svc.method ?? []).length, 0);
  const messageCount = [...registry.values()].filter(
    (e) => e.kind === 'message' && isOwned(e) && !e.isSynthetic,
  ).length;
  const enumCount = [...registry.values()].filter(
    (e) => e.kind === 'enum' && isOwned(e),
  ).length;

  console.log(
    `generate-reference: wrote ${1 + services.length + methodCount + messageCount + enumCount} reference pages (${services.length} services, ${methodCount} methods, ${messageCount} messages, ${enumCount} enums) to ${path.relative(process.cwd(), outDocs) || outDocs}`,
  );
}

main();
