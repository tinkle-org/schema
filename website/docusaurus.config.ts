import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import Search from '@easyops-cn/docusaurus-search-local';
import sidebars from './sidebars';

/*
 * Hosting model
 * ─────────────
 * The site is built for the canonical URL https://tinkle.me/schema/ and is
 * deployed by the main website (tinkle-org/tinkle-website-nextjs), which
 * serves this build artifact under the /schema/ path.
 *
 * - Production: url 'https://tinkle.me', baseUrl '/schema/' — every asset,
 *   link and canonical URL carries the /schema prefix.
 * - Local dev: `npm run dev` serves the same layout at
 *   http://localhost:3000/schema/.
 *
 * Docs-only mode: the docs plugin owns all routes (routeBasePath '/'); there
 * is no separate pages plugin. The landing page is website/docs/index.md.
 */
const repoUrl = 'https://github.com/tinkle-org/tinkle-proto';

const docsPreset: Preset.Options = {
  blog: false,
  pages: false,
  docs: {
    routeBasePath: '/',
    sidebarPath: './sidebars.ts',
    showLastUpdateTime: false,
    editUrl: ({ docPath }: { docPath: string }) =>
      // Generated pages (reference + synced guides) have no editable source
      // under website/docs; narrative pages do.
      /^(index\.md|introduction\.md|getting-started\/)/.test(docPath)
        ? `${repoUrl}/edit/main/website/docs/${docPath}`
        : undefined,
  },
};

const config: Config = {
  title: 'Tinkle Schema',
  tagline: 'tinkle.v1 — the Protobuf contract for the Tinkle messaging API',
  url: 'https://tinkle.me',
  baseUrl: '/schema/',
  trailingSlash: true,

  favicon: 'img/tinkle.svg',

  onBrokenLinks: 'throw',
  onDuplicateRoutes: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [ ['classic', docsPreset] ],

  themes: [
    [
      Search,
      {
        hashed: true,
        docsRouteBasePath: '/',
        language: ['en'],
        indexBlog: false,
      },
    ],
  ],

  themeConfig: {
    announcementBar: {
      id: 'prerelease',
      content:
        'The tinkle.v1 contract is <b>pre-release</b>: breaking restructuring is expected and carries no external compatibility commitment.',
      backgroundColor: '#fde68a',
      textColor: '#78350f',
      isCloseable: true,
    },
    navbar: {
      title: 'Tinkle Schema',
      logo: { alt: 'Tinkle logo', src: 'img/tinkle.svg' },
      items: [
        { type: 'doc', docId: 'index', position: 'left', label: 'Overview' },
        { type: 'doc', docId: 'introduction', position: 'left', label: 'Introduction' },
        { type: 'doc', docId: 'getting-started/consuming-sdks', position: 'left', label: 'SDKs' },
        { type: 'doc', docId: 'reference/index', position: 'left', label: 'Reference' },
        { type: 'doc', docId: 'guides/realtime', position: 'left', label: 'Realtime' },
        {
          href: 'https://buf.build/tinklecorp/tinkle-proto',
          position: 'right',
          label: 'Buf Registry',
        },
        {
          href: repoUrl,
          position: 'right',
          className: 'header-github-link',
          'aria-label': 'GitHub repository',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Contract',
          items: [
            { label: 'Schema reference', to: '/reference' },
            { label: 'Realtime binding', to: '/guides/realtime' },
          ],
        },
        {
          title: 'Distribution',
          items: [
            { label: 'Buf Schema Registry', href: 'https://buf.build/tinklecorp/tinkle-proto' },
            { label: 'BSR documentation', href: 'https://buf.build/tinklecorp/tinkle-proto/docs' },
          ],
        },
        {
          title: 'Source',
          items: [
            { label: 'Repository', href: repoUrl },
            { label: 'Proto source', href: `${repoUrl}/tree/main/tinkle/v1` },
          ],
        },
      ],
      copyright: 'Built from the protobuf source of truth in tinkle-org/tinkle-proto.',
    },
    prism: {
      theme: prismThemes.dracula,
      darkTheme: prismThemes.dracula,
    },
  },
};

export default config;
