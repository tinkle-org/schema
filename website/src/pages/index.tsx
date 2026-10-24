import React from 'react';
import Link from '@docusaurus/Link';
import clsx from 'clsx';
import Grid, { Col } from '@site/src/components/SiteGrid';
import schemaSummary from '@site/src/lib/schema-summary.json';

type ServiceSummary = {
  name: string;
  slug: string;
  file: string;
  methodCount: number;
  summary: string | null;
};

type SchemaSummary = {
  repository: string;
  counts: {
    services: number;
    methods: number;
    messages: number;
    enums: number;
    files: number;
  };
  services: ServiceSummary[];
};

const summary = schemaSummary as SchemaSummary;

const features = [
  {
    title: 'Schema reference',
    href: '/docs/reference',
    description:
      'Every service, RPC method, message and enum in tinkle.v1 — generated from descriptor sets with comments, deprecations and reserved definitions.',
    cta: 'Browse reference',
  },
  {
    title: 'Consume the SDKs',
    href: '/docs/getting-started/consuming-sdks',
    description:
      'Generated Go and Rust SDKs are published by the Buf Schema Registry and gated to schema releases.',
    cta: 'Get started',
  },
  {
    title: 'Realtime binding',
    href: '/docs/guides/realtime',
    description:
      'The Syntra-only realtime application binding: batched durable updates, cursor rules and conformance checks.',
    cta: 'Read the guide',
  },
];

export default function Home() {
  return (
    <main>
      <header className="hero hero--primary margin-top--lg" style={{ borderRadius: '0.75rem' }}>
        <div className="container text--center">
          <h1 className="hero__title">Tinkle Schema</h1>
          <p className="hero__subtitle">
            tinkle.v1 · Protobuf · {summary.counts.services} services · {summary.counts.methods}{' '}
            methods · {summary.counts.messages} messages · {summary.counts.enums} enums
          </p>
          <div className="margin-bottom--sm" style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
            <Link className="button button--secondary button--lg" to="/docs/reference">
              Browse the reference
            </Link>
            <Link
              className="button button--outline button--lg button--light"
              to="/docs/getting-started/consuming-sdks"
            >
              Get the SDKs
            </Link>
          </div>
        </div>
      </header>

      <section className="container margin-vert--xl">
        <div className="text--center margin-bottom--lg">
          <p>
            The <code>tinkle.v1</code> contract is <strong>pre-release</strong>: intentional
            restructuring is expected and carries no external compatibility commitment. The
            reference below is generated from the authoritative <code>.proto</code> source in{' '}
            <Link href={`https://github.com/${summary.repository}`}>{summary.repository}</Link>.
          </p>
        </div>

        <Grid className="margin-vert--lg">
          {features.map((f, i) => (
            <Col key={i} oneThird>
              <div className={clsx('card', 'siteCard')}>
                <div className="card__header">
                  <h2 className="margin-bottom--sm text--md">{f.title}</h2>
                  <p className="text--muted">{f.description}</p>
                </div>
                <div className="card__footer">
                  <Link className="button button--primary button--sm" href={f.href}>
                    {f.cta} →
                  </Link>
                </div>
              </div>
            </Col>
          ))}
        </Grid>

        <h2 className="margin-top--xl">Services</h2>
        <Grid>
          {summary.services.map((svc) => (
            <Col key={svc.name} oneHalf>
              <Link
                className="card padding--md"
                to={`/docs/reference/services/${svc.slug}`}
                style={{ color: 'inherit', textDecoration: 'none' }}
              >
                <h3 className="margin-bottom--xs no-margin-top" style={{ display: 'inline' }}>
                  {svc.name}
                </h3>{' '}
                <span className="badge badge--secondary">{svc.methodCount} methods</span>
                {svc.summary && (
                  <p className="text--muted margin-bottom--none">{svc.summary}</p>
                )}
              </Link>
            </Col>
          ))}
        </Grid>
      </section>
    </main>
  );
}
