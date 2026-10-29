# Changelog

## 1.0.1 (2026-10-29)


### ⚠ BREAKING CHANGES

* **files:** add FilesService and *Source media construction types ([#53](https://github.com/tinkle-org/schema/issues/53))
* **updates:** replace batched binding with individual updates and trunk-based publishing ([#49](https://github.com/tinkle-org/schema/issues/49))
* **realtime:** pre-release removal of legacy JSON WebSocket messages with no compatibility commitment.
* **auth:** SignInResponse shape changed; RenewToken RPC removed.
* migrate to monorepo with release-please and release-branch model

### Features

* **account:** add app_build field to Session message for client reporting ([#40](https://github.com/tinkle-org/schema/issues/40)) ([9e36a25](https://github.com/tinkle-org/schema/commit/9e36a256fb8e5f40cbc5f6886603a11c61ed98c2))
* **account:** add GetSessions RPC ([#39](https://github.com/tinkle-org/schema/issues/39)) ([59b8b86](https://github.com/tinkle-org/schema/commit/59b8b8688396747340274391c5442f896ee6ea8f))
* **account:** add logout and session revocation rpcs ([#37](https://github.com/tinkle-org/schema/issues/37)) ([686a84c](https://github.com/tinkle-org/schema/commit/686a84c81735b788b421a8a4e14d3340c9e42131))
* add bin/release-please-bump.sh helper script ([aaa7411](https://github.com/tinkle-org/schema/commit/aaa7411e43a6aee773b4f4e7d810c8561218835f))
* **auth:** add verification_id to auth and phone-change contracts ([#41](https://github.com/tinkle-org/schema/issues/41)) ([69b7868](https://github.com/tinkle-org/schema/commit/69b786821245b5d41582974dbd5da2291117d8de))
* **auth:** replace id/refresh tokens with opaque session token ([#36](https://github.com/tinkle-org/schema/issues/36)) ([33817c5](https://github.com/tinkle-org/schema/commit/33817c577bd1c15af586650b50a65508751aaf7a))
* **connection:** add ConnectionService.InitConnect wrapper ([#55](https://github.com/tinkle-org/schema/issues/55)) ([ae413d5](https://github.com/tinkle-org/schema/commit/ae413d5eec043bd7da626a6743bbcc3f56ee59a8))
* **files:** add FilesService and *Source media construction types ([#53](https://github.com/tinkle-org/schema/issues/53)) ([5397633](https://github.com/tinkle-org/schema/commit/5397633d914da690b245722c9446b46a8baecb1c))
* **files:** tighten production file-transfer contract ([#54](https://github.com/tinkle-org/schema/issues/54)) ([59166e3](https://github.com/tinkle-org/schema/commit/59166e34046dd7624bc96acf593f2c1cc0af06dc))
* **messages:** add cursor pagination to GetDialogs ([#43](https://github.com/tinkle-org/schema/issues/43)) ([afab5f1](https://github.com/tinkle-org/schema/commit/afab5f10ee84f96e94a135a0fd1457f87dabf034))
* migrate to monorepo with release-please and release-branch model ([793a387](https://github.com/tinkle-org/schema/commit/793a387119dd9a6aad3818799c190e97b135e7be))
* monorepo migration with release-please and release-branch model ([34f6f5e](https://github.com/tinkle-org/schema/commit/34f6f5e2a4f00fc0ef6ca0768c2c91a85913d0cd))
* Nextra docs content and BSR module rename to tinkle-org/schema ([#46](https://github.com/tinkle-org/schema/issues/46)) ([334a0c5](https://github.com/tinkle-org/schema/commit/334a0c5e97f9784644741ea72a73c53efbebd7f7))
* **realtime:** add batched Syntra application binding ([#44](https://github.com/tinkle-org/schema/issues/44)) ([44c2dad](https://github.com/tinkle-org/schema/commit/44c2dadd3b622448796e4d8ac65b60d7683081d5))
* **realtime:** add native receive-only websocket protocol ([#42](https://github.com/tinkle-org/schema/issues/42)) ([fd2531f](https://github.com/tinkle-org/schema/commit/fd2531fb147241afa98a7cfe5cb3c8d936ab4138))
* **realtime:** remove legacy websocket leaving Syntra-only binding ([#45](https://github.com/tinkle-org/schema/issues/45)) ([747210b](https://github.com/tinkle-org/schema/commit/747210b22775ba620b3a8c436d8a075959e59959))
* **release:** support per-component version bumps for multi-major setup ([1d20e12](https://github.com/tinkle-org/schema/commit/1d20e123c6941121ae4b877909c142edaf9f3509))
* **updates:** explicit bounded recovery ([#50](https://github.com/tinkle-org/schema/issues/50)) ([56088ea](https://github.com/tinkle-org/schema/commit/56088eaf60e23a1faa408e49545f3ce91de1cfb8))
* **updates:** replace batched binding with individual updates and trunk-based publishing ([#49](https://github.com/tinkle-org/schema/issues/49)) ([e1c3069](https://github.com/tinkle-org/schema/commit/e1c306907aead5194d45334044f2500ee50e411a))


### Bug Fixes

* **account:** document session RPCs against Ory Kratos opaque token ([#38](https://github.com/tinkle-org/schema/issues/38)) ([a1a5dd4](https://github.com/tinkle-org/schema/commit/a1a5dd49ca6281a84cea824a32d4928bebb18935))
* **ci:** add workflow_dispatch to release.yml; escape GITHUB_TOKEN-silenced tag push ([#31](https://github.com/tinkle-org/schema/issues/31)) ([d76f580](https://github.com/tinkle-org/schema/commit/d76f580dba065d4879d63907ef03a6745fa4a66b))
* **ci:** bump Elixir 1.15 -&gt; 1.16 and Go 1.22 -&gt; 1.25 to match current toolchain ([c0f686c](https://github.com/tinkle-org/schema/commit/c0f686cd98e371d068bbfcf1ae1e72be6be099d0))
* **ci:** disable cache in setup-go@v6 in release.yml ([479f6b4](https://github.com/tinkle-org/schema/commit/479f6b433eb755d1472af87c7eed80b1a7643c14))
* **ci:** drop nonexistent grpc_elixir escript; use plugins=grpc in protoc-gen-elixir ([ccb7eff](https://github.com/tinkle-org/schema/commit/ccb7eff8e1448f251305c629680494173519f707))
* **ci:** install all buf plugins in release.yml for every language ([#17](https://github.com/tinkle-org/schema/issues/17)) ([a17c945](https://github.com/tinkle-org/schema/commit/a17c94596e8e8438cb7c65c951f41b151249ddce))
* **ci:** install Go to $HOME/.local/go (Permission denied on /usr/local) ([91fb507](https://github.com/tinkle-org/schema/commit/91fb507133963698b6924591b01637a3e112c42d))
* **ci:** install Go via tarball instead of actions/setup-go@v6 in release ([c97c50e](https://github.com/tinkle-org/schema/commit/c97c50ebe8479469ac4578cf745b00a3ecc0e21d))
* **ci:** per-language build jobs need all 3 buf plugins on PATH ([54d4632](https://github.com/tinkle-org/schema/commit/54d463240cdc46f70342c90b90bc5225da0ab0dc))
* **ci:** per-language build jobs need protoc + correct working dir for buf generate ([e502b4f](https://github.com/tinkle-org/schema/commit/e502b4f78a364881f4653c37ab5873ff12ced949))
* **ci:** remove pre-existing /usr/local/go before extracting Go tarball ([6d12059](https://github.com/tinkle-org/schema/commit/6d12059cd105b227db0b42db74ca1b7e245a6814))
* **ci:** use git add -f to include gitignored generated files in release ([4ba3195](https://github.com/tinkle-org/schema/commit/4ba3195c25288d8e3cec392995b0e35843e6103f))
* **ci:** use refs/heads/ prefix in release branch push refspec ([0d112f9](https://github.com/tinkle-org/schema/commit/0d112f95671c38852ea843305d8563e36bc0dfcd))
* **dependabot:** drop bogus 'buf' ecosystem entry ([8f32460](https://github.com/tinkle-org/schema/commit/8f32460790d949736b40c7f83b0c002b3f789456))
* **elixir:** re-apply grpc ~&gt; 1.0 update reverted by 1.0.0 release PR ([#25](https://github.com/tinkle-org/schema/issues/25)) ([e814ea1](https://github.com/tinkle-org/schema/commit/e814ea1951b72fc31d2d7d53829ad20ea057b18d))
* **rs:** bump tonic/prost to 0.14 and migrate to tonic-prost-build ([#16](https://github.com/tinkle-org/schema/issues/16)) ([ab9be02](https://github.com/tinkle-org/schema/commit/ab9be02c03ebd796389b3873db77a7c5f8fcc368))


### Miscellaneous Chores

* bootstrap release 1.0.0 ([2ee117a](https://github.com/tinkle-org/schema/commit/2ee117a323c817d530b836963e30e39b21df3ea5))
* force release 1.0.1 ([#30](https://github.com/tinkle-org/schema/issues/30)) ([886de66](https://github.com/tinkle-org/schema/commit/886de66bc7b1a167b9677736acbde57e52177d67))
