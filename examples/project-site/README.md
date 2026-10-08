# ALGHREST project website

موقع تقديمي مستقل داخل `examples/project-site`، مبني باستخدام Next.js 16،
React 19، TypeScript وTailwind CSS 4. يدعم العربية RTL والفرنسية، ويوضح
البنية ومصادر البيانات وحدود الجاهزية وفق وثائق المستودع الحالية.

## Run

Node.js 20.9 or newer is required. From the repository root:

```bash
cd examples/project-site
npm ci
npm run dev
```

Open http://127.0.0.1:3001. Production preview:

```bash
npm run build
npm start
```

The server binds to loopback. Public hosting is not configured or implied.
Do not run `npm start` and `npm run dev` on port 3001 simultaneously.

## Experience

- Interactive decision diagram and three documented architecture modes.
- Searchable, filterable source catalogue with implementation references.
- Clearly labelled synthetic position-sizing illustration; no financial engine.
- Maturity assessment and development criteria, without promised launch dates.
- Six README documents rendered safely as Markdown, with source hashes.
- Eight-chapter presentation mode, arrow keys, Escape and native focus handling.
- Arabic 44-slide PDF/PowerPoint downloads with presenter notes in PowerPoint.
- Locally bundled Arabic/Latin fonts, reduced-motion support and responsive layouts.

## Documentation and privacy

`lib/content-source.mjs` allows only the root, dashboard, research, HMM,
artifacts and docs READMEs. `predev` and `prebuild` save their contents into
`content/docs.json`. A running server reads the six repository files afresh;
the refresh button requests `/api/project` and updates metadata/test evidence.
Document pages always fetch the current allowlisted contents.

If runtime access to repository READMEs is unavailable, the server uses the
bundled snapshot and labels it accordingly. Rebuild from the repository after
documentation changes; do not treat a copied snapshot as automatically current.
Editorial explanations in `lib/site-content.ts` must also be reviewed when
project behaviour changes. The six README files do not define all UI prose.

This site exposes no market stream, account state, credentials, orders, model
calls or operational endpoints. The sliders use fictitious inputs and remain
`WAIT / execution_enabled = false`. Test counts are README-reported local evidence,
not a hosted CI result or proof of trading profitability. Existing dashboard and
advisory API remain separate applications. Private GitHub links require access.

Deployments would expose these six README contents and presentation downloads;
review them before publication. No `.env`, raw logs or financial database is read.

## Validation

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

The lockfile pins dependencies. Build output and `node_modules` are ignored.
The old HTML/CSS/JavaScript site was checkpointed in ignored local
`artifacts/project-site/before/` before its replacement; it is not maintained.
