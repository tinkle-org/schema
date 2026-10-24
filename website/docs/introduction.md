---
title: Introduction
description: The tinkle.v1 protobuf contract, how it is published, and how this documentation site relates to the Buf Schema Registry.
sidebar_position: 1
---

The `tinkle.v1` package is the public Protobuf contract of the Tinkle messaging
API. Its single source of truth lives in this repository under
[`tinkle/v1/`](https://github.com/tinkle-org/tinkle-proto/tree/main/tinkle/v1) —
there is no upstream mirror; every contract change is authored here.

## What is published where

| Layer | Location | Rebuilt on |
| --- | --- | --- |
| Protobuf source | `tinkle/v1/*.proto` in this repo | Commit |
| Validation (lint/format/breaking/build) | GitHub Actions on every PR | Every push |
| Schema distribution (Go/Rust SDKs) | [Buf Schema Registry](https://buf.build/tinklecorp/tinkle-proto) | Release PR merge |
| This documentation site | GitHub Pages reference generated from descriptors | Every merge to `main` |

Key properties:

- **Contracts change only here.** The Buf CI workflow validates every PR and posts
  a summary, but it does not publish. Publication to the BSR happens exclusively
  when a [release-please](https://github.com/googleapis/release-please) release PR
  is merged, so the registry and its generated SDKs move only on versioned
  releases.
- **Documentation is generated, not copied.** The [schema reference](/reference)
  pages are produced from the protobuf descriptor set — including source comments,
  deprecations and reserved definitions — on every site build. Editing prose about
  the contract means editing the `.proto` shebang comments or the narrative guides.
- **Realtime is an application binding, not a gRPC service.**
  [`tinkle/v1/realtime.proto`](https://github.com/tinkle-org/tinkle-proto/blob/main/tinkle/v1/realtime.proto)
  defines Syntra-application messages carried inside the Syntra
  `Notification.payload`; the [Realtime guide](/guides/realtime) documents
  those dispatcher method bindings, with [conformance](/guides/conformance/realtime)
  notes for implementers.

## Repository layout

```
tinkle/v1/        authoritative .proto sources
conformance/      schema + codec checks (pure Python, no bindings)
buf.yaml          v2 module config
REALTIME.md       normative realtime binding doc (canonical)
website/          this Docusaurus site (independent from the Next.js site)
.github/          workflows: buf-ci (validate), release-please, docs-ci, docs-deploy
```

## Status

The contract is **pre-release**. `buf.yaml` disables builtin breaking checks for
`tinkle.v1` restructuring; the intended stable policy is `breaking: FILE`, to be
re-enabled at the first stable release. Until then, structural churn and no
external compatibility commitment are expected. Narrative docs that rely on
this sites’ generated pages always display the current schema.
