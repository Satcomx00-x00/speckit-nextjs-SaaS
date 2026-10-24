---
description: Delta-Global gate runner. Evaluates a checklist (inline items, a file, or a named preset — scope, rfc, pre-merge, security, observability, release, migration) against the artifacts and the repository, and returns PASS/FAIL/WARN/SKIP per item with cited evidence and a gate verdict. Used by the saas-feature, hotfix and migration-only workflows at their gates; also runnable standalone.
handoffs:
  - label: Fix failing items
    agent: speckit.tasks
    prompt: Generate one fix task per failing checklist item, FAIL before WARN, each citing its CL-<N>.
  - label: Investigate drift
    agent: speckit.analyze
    prompt: Run a full cross-artifact analysis to investigate the checklist failures in depth.
  - label: Run the audit
    agent: speckit.audit
    prompt: Run the codebase audit for rule-level detail on the failing items.
---

## User Input

```text
$ARGUMENTS
```

The argument is a **checklist definition**, one of:

1. **Inline bullet list** — items passed in the text (what the workflow engine sends).
2. **File reference** — a markdown file of items (e.g. `specs/NNN-slug/checklists/requirements.md`).
3. **Named preset** — `preset:<name>` from the table below; several may be combined (`preset:pre-merge preset:security`).

Inline items and presets can be mixed: expand the presets, then append the
inline items. If the argument is empty, ask for the items and stop.

### Built-in presets

| Preset | Gate it serves |
|---|---|
| `preset:scope` | after `/speckit.specify` — is the spec testable and complete? |
| `preset:rfc` | after `/speckit.plan` — is the design compliant before code? |
| `preset:pre-merge` | before the PR is opened/merged |
| `preset:security` | features touching auth, money, PII, admin, or new external surfaces |
| `preset:observability` | before rollout — are signals, alerts and runbooks real? |
| `preset:release` | before pinning staging / production |
| `preset:migration` | any change under `packages/db/` |

The full item list of each preset is in **Appendix A**.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_checklist` and apply standard hook-processing.

Run `.specify/scripts/bash/check-prerequisites.sh --json --paths-only` (or
the PowerShell equivalent) to locate `FEATURE_DIR` when the items concern a
feature. Read `.specify/presets/delta-global/CONVENTIONS.md` if present —
paths and commands below follow it; the platform's constitution, ADRs and
`CLAUDE.md` take precedence when they disagree.

## The evidence rule

**A checked box is a claim, not proof.** Every verdict — including PASS —
cites what you observed: a `path:line`, a command and the relevant line of its
output, or an artifact section. Ignore the `[x]` state of any existing
checklist or tasks file; re-derive it. An item you could not observe is
`WARN` (non-binary) or `FAIL` (binary) — never PASS by assumption.
The platform's history is full of "16/16 checked" checklists over features
whose flags were never registered; this command exists to not repeat that.

## Outline

### 1. Parse the checklist

Normalise each item to:

```
{ id: "CL-<N>", text, category: Spec | Schema | Migration | GraphQL | Service | Flag | Cache |
  Security | Privacy | Observability | Tests | Web | Release | Process, blocking: true }
```

`blocking` defaults to true unless the item says "track", "advisory" or "warn".

### 2. Resolve where to look

| Topic | Inspect |
|---|---|
| Spec / ACs / thresholds | `specs/NNN-slug/spec.md` (header Status/Verified, `AC-###`, Rollback Thresholds, GDPR) |
| Plan sections | `specs/NNN-slug/plan.md` §1–§14, File Map, Service Interaction Map |
| Tasks | `specs/NNN-slug/tasks.md` (`T###`, `[US#]`, `(AC-###)`) |
| Drizzle schema / migrations | `packages/db/src/schema/`, `packages/db/drizzle/` |
| DB functions | `packages/db/src/<area>-dal.ts`, `apps/api/src/dal/` |
| Zod contracts | `packages/shared/src/schemas/` |
| GraphQL SDL | `packages/graphql/schema/NN-*.graphql`, `specs/NNN-slug/contracts/schema.graphql` |
| Resolvers / directives | `apps/api/src/graphql/resolvers/`, `apps/api/src/graphql/directives/` |
| Services | `apps/api/src/services/` |
| Feature flags | `packages/shared/src/schemas/feature-flags.ts`, `apps/workers/src/infrastructure/feature_flags.py`, `packages/db/src/seeds/feature-flags.ts`, `apps/api/src/services/<slug>-flag.ts` |
| Temporal | `packages/temporal-workflows/src/`, `packages/temporal-workflows/test/histories/`, `apps/workers/`, `apps/crawler/` |
| Web | `apps/web/src/app/[locale]/`, `apps/web/src/lib/server/`, `apps/web/src/lib/<area>-api.ts`, `apps/web/src/graphql/`, `apps/web/messages/{en,fr,es}.json` |
| Tests | `apps/api/test/<slug>/`, colocated `*.test.ts(x)`, `apps/web/e2e/`, `apps/workers/tests/` |
| Env / secrets | `apps/api/src/env.ts`, `apps/web/src/env.ts`, `.env.example`, Infisical `/app-stack` (ask the human — not readable from the repo) |
| CI reality | `.github/workflows/ci.yml`, `e2e.yml`, `release.yml`, `.pre-commit-config.yaml` |
| Infra (sibling repo `platform-infra`) | `charts/app-stack/values-<env>.yaml`, `charts/grafana/alerting/`, `charts/grafana/dashboards/`, `charts/network-policies/values.yaml` |
| Runbooks | `docs/runbooks/` |

If the sibling `platform-infra` checkout is not reachable, infra items are
`WARN` with "verify in platform-infra: <path>".

### 3. Evaluate

| Verdict | Meaning |
|---|---|
| `PASS ✓` | observed evidence satisfies the item |
| `FAIL ✗` | evidence contradicts the item, or a binary item has no evidence |
| `WARN ⚠` | partially satisfied, or a non-binary/process item that could not be observed |
| `SKIP —` | not applicable — reason required |

- **Binary items** (present/absent, declared/missing, exits 0): PASS or FAIL only.
- **Threshold items** (`<`, `>`, `%`, ms, KB): PASS within threshold, FAIL beyond, WARN when unmeasured.
- **Command items**: run the command; PASS only on exit 0, quoting the last relevant line. Run from the platform repo root.
- **Process items** (reviews, human click-through, Infisical): WARN unless an artifact records it (PR link, `verify-report.md`, spec *Verified* line).
- **Hard constraints** (items saying "never", "must not", "CRITICAL"): blocking regardless of the flag.
- **Claimed CI gates**: before trusting "CI enforces X", find X in `.github/workflows/ci.yml`. Not there → FAIL with `GATE_MISSING_FROM_CI`. Note that GitHub Free has no required checks (ADR-0006): "CI green" means you looked at the run.

### 4. Report

```markdown
# Checklist Report — <presets / source> — <feature> — <date>

**Items**: <total> (pass p · fail f · warn w · skip s)
**Gate**: PASS ✓ | FAIL ✗ | WARN ⚠   (any blocking FAIL ⇒ FAIL)

## Failing (blocking)
- [CL-<N>] ✗ **<item>**
  Evidence: <what was observed / which command exited non-zero, with the line>
  Fix: <one actionable sentence>

## Warnings
- [CL-<N>] ⚠ **<item>** — Evidence: … — Human must confirm: …

## Passing
- [CL-<N>] ✓ <item> — `<path:line>` | `<command>` → `<line>`

## Skipped
- [CL-<N>] — <item> — Reason: …

## Gate verdict
PASS — proceed.  |  FAIL — resolve before continuing: 1. [CL-<N>] … 2. …
```

When the input was a file under `specs/`, also rewrite that file's boxes to
match the verdicts **and** append the evidence after each item, so the file
stops being a rubber stamp. Never tick a box you did not verify.

### 5. Self-check

- Every PASS has evidence; every FAIL has evidence and a fix; every SKIP a reason.
- The verdict is computed from the items, not from impression.

---

## Appendix A — preset item lists

### `preset:scope`
1. Spec header complete: slug, flag (plain kebab-case, no `ff-`), branch `<type>/<desc>-<id>`, Created, Status, Verified, ADR/RFC decision.
2. Every user story has priority (P1…) and at least one `AC-###`; ACs numbered globally.
3. Every AC is binary (EARS `WHEN … THE SYSTEM SHALL …` or Given/When/Then); none contains "should", "ideally", "if possible", "fast", "intuitive" without a number.
4. Non-Goals listed.
5. Edge cases cover empty, max length, Unicode, concurrent edit, outage of each touched dependency.
6. RBAC roles use only `owner | admin | member` and platform admin — no `viewer`.
7. Tenancy model stated (owner-scoped default, or org-scoped with reason).
8. Success Metrics have a number and a measurement source.
9. Rollback Thresholds numeric (error rate, p95) and named per signal.
10. Marginal Cost Estimate includes Postgres rows, Redis keys, Temporal executions, OpenRouter calls/€, and "ClickHouse events: N".
11. GDPR table: each data class, lawful basis, retention (ADR-0034), DSAR/erasure impact.
12. Plan/entitlement impact stated (Free/Basic/Pro, via `packages/shared/src/schemas/billing.ts`) or "none".
13. Manual Verification section lists every UI criterion a human must click through.
14. If a research brief exists (`docs/research/…/brief.md`), its recommendation and open questions are carried or explicitly rejected.

### `preset:rfc`
1. plan.md declares the tenancy model and the scope predicate for every table.
2. Every new table: `owner_id`/scope FK + index, `created_at`/`updated_at` timestamptz, explicit unique/check constraints, soft/hard-delete decision, RLS `--custom` block planned.
3. Every new SDL field has `@public` / `@auth(role:)` / `@selfOnly` chosen per field with a reason for `@public`.
4. Every admin mutation has `@audited(action: "<area>.<verb>")` and a top-level `reason` argument.
5. Every operation has a Zod input schema in `packages/shared`, a thin resolver and a named service in `apps/api/src/services/`.
6. Services take `db`/`redis` as parameters — no composition-root imports.
7. List reads project columns, paginate with an `id` tiebreak, and cache id arrays (not payloads); every cache family has invalidation sites and a blast-radius statement.
8. Flag: key, registry (`FEATURE_FLAG_KEYS` + `FEATURE_FLAG_METADATA` + Python mirror + seed), guard sites, global granularity justified, OFF restores today's behaviour, planned removal date.
9. Background work is Temporal with deterministic workflow IDs; activities placed in workers (Python) or crawler (TS).
10. Service Interaction Map: an explicit row for web, api, Postgres, Redis, Temporal, workers, crawler, Stripe, OpenRouter, storage, auth, realtime SSE, telemetry, GlitchTip — reason on every "no".
11. Every external call: timeout, retry budget, fallback, cost cap; any new host has an ADR + CLAUDE.md row + `charts/network-policies` entry.
12. Migrations are expand-only for this release; any contract step is planned for a later release.
13. Observability: spans/logs/metrics named, metric labels bounded, ClickHouse events stated, each rollback threshold has a planned alert.
14. Testing plan: a `@critical` api integration test per mutation, a failure-mode test per touched service, DOM tests for interactive components, `@smoke` E2E for the happy path.
15. Any MUST deviation (incl. hand-written SQL) has a §14 Complexity Justification.

### `preset:pre-merge`
1. `bunx biome ci .` exits 0.
2. `bun run typecheck` exits 0 (includes `check:field-auth`, `check:field-audit`, `check:log-hygiene`, `check:contrast`).
3. `bun run depcruise` and `bun run check:composition-root` exit 0.
4. `bun run check:trpc-removal` exits 0.
5. `bun --filter='@delta-global/web' codegen:check` exits 0.
6. `bun run check:py-models` exits 0.
7. `bun run check:migration-immutability origin/main` and `bun run check:migration-expand-contract origin/main` exit 0 (or every finding is covered by an `Allow-Contract-Migration:` trailer naming the release that stopped using it).
8. `bun run scripts/i18n-parity.ts` and `bun run scripts/i18n-scan.ts` exit 0.
9. `bun run check:svg-assets` exits 0.
10. `bun run test` passes against a real Postgres/Redis (`INTEGRATION_DB_URL` set) and `bun run check:integration-skip` exits 0 — no silent skip.
11. Every mutation has a passing api test named `@critical`.
12. Python touched → `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest tests/` pass in `apps/workers`.
13. Temporal workflow touched → replay tests pass without a regenerated history.
14. Web touched → `bun run turbo run build --filter=@delta-global/web && bun --filter=@delta-global/web perf:budget` exits 0.
15. `gitleaks detect --source . --redact --no-banner` clean; `bash scripts/guard-admin-dal-isolation.sh` clean.
16. Flag registered in all four places and **OFF** by default.
17. `verify-report.md` exists with overall PASS (or every FAIL owned in `follow-ups.md`).
18. New env vars in `env.ts` + `.env.example`; secrets confirmed at Infisical `/app-stack` for staging and production.
19. `bun.lock` committed if dependencies changed; no `package-lock.json`/`pnpm-lock.yaml`/`yarn.lock`.
20. Branch matches `^(feat|fix|chore|docs|refactor|perf|test|build|ci|release)/[a-z0-9-]+-[a-z0-9]{4,}$`.
21. Commits are Conventional with an allowed scope; for phased features, one commit per phase.
22. PR body states migration · flag · env vars · egress · rollback plan.
23. Diff reviewable (< ~600 changed lines excluding generated files) or split by phase.

### `preset:security`
1. Scope key read from the session/JWT only; no GraphQL argument carries an owner/org id used for authorization.
2. Every DAL read and write on a scoped table filters by the scope key.
3. Every field's auth directive matches the spec's audience; no `@public` on private data.
4. Admin UI and admin fields unreachable for non-admins (server-side re-check, not only UI hiding).
5. Every admin mutation `@audited` with top-level `reason`; audit never written to stdout.
6. Inputs parsed with Zod at every untrusted boundary (GraphQL args, route params, webhooks, Temporal signals, env).
7. Rate limit on write mutations and on any expensive `@cost` field.
8. User-supplied URLs fetched server-side go through the SSRF guard (no private/internal addresses).
9. No raw server/DB error text returned to readers; errors are typed codes.
10. Logs carry no bodies, headers, cookies or raw emails.
11. Billing: no price id/amount/return URL accepted from the client; Stripe events trigger a re-fetch, never applied as state.
12. Secrets only via Infisical + `env.ts`; nothing in committed `.env.*`.
13. Post-auth redirects go through `safeInternalPath()`.
14. No new outbound host without ADR + CLAUDE.md row + network-policy entry.
15. Sign-out → sign-in as another account in the same tab shows no data of the first account (F-39).

### `preset:observability`
1. Spans carry `user.id`, `graphql.operation.name`, `graphql.operation.type` (and `org.id` where an org exists) at the feature's call sites.
2. Logs via `@delta-global/logger` (`createLogger(deps)` injected) or loguru, with `trace_id` absent-not-empty outside a trace.
3. Async operations emit start / complete / fail with duration.
4. Metric labels bounded (≤ 500 series per metric); no ids, URLs or raw queries as labels.
5. Unexpected errors reported via `createErrorReporter` beside the existing handling; client/source-caused failures not reported.
6. Every rollback threshold has an alert rule in `platform-infra/charts/grafana/alerting/<NNN>-<slug>.json`, scoped to `deployment.environment='production'`, with `severity` (page/ticket/info), `service`, and `runbook_url`.
7. No templates (`{{ }}`, `$labels`, `$values`) in alert annotations or labels.
8. A runbook exists at `docs/runbooks/<slug>.md` (debug, kill switch, rollback = pin).
9. Dashboard JSON at `platform-infra/charts/grafana/dashboards/<NNN>-<slug>.json` (unique filename).
10. After the infra PR synced, Grafana was restarted (`kubectl -n observability rollout restart deploy/grafana`) and the rules are visible — authored but not loaded counts as missing.

### `preset:release`
1. `uv run scripts/ship.py plan` reviewed: the apps to release and what their migrations do.
2. Apps derived from changed packages (shared → all four; db → api, crawler; graphql → api, web; ui → web; temporal-workflows → api, crawler; connectors/config → crawler).
3. If a migration ships, `api` is released and pinned first.
4. Release commits are empty `release(<app>): <lowercase subject>`, one push per app, via `scripts/release.sh` (the CI release gate passed).
5. Images exist: `ghcr.io/delta-global/platform/<app>:<semver>` and tag `<app>-v<semver>`.
6. Staging pin committed in `platform-infra/charts/app-stack/values-staging.yaml` (`<app>.image.tag`) as `chore(deploy): pin staging to <app> <ver>`.
7. On staging: `db-migrate` init container logs clean, `build_info` from inside the pods matches, **the feature itself** exercised (not just pods healthy), `ship.py verify --env staging` clean.
8. Flag toggled on staging via the audited `flags.set` mutation with a reason, and the AC smoke passed.
9. Production pins exactly the versions verified on staging; `argocd app diff app-stack-production` reviewed before `argocd app sync app-stack-production`.
10. Explicit human OK recorded before the production sync.
11. Rollback plan = previous pin (`ship.py promote --env production --to <prev>`) and/or flag OFF, with the previous versions written down.

### `preset:migration`
1. Schema change generated by `bun run db:generate`; any hand-written SQL is a `--custom` block justified in plan §14.
2. `bun run check:migration-expand-contract origin/main` clean, or each finding covered by an `Allow-Contract-Migration:` trailer naming what is removed and the release that stopped using it.
3. `bun run check:migration-immutability origin/main` clean — no edited, renamed or deleted migration on main; number does not collide.
4. The previous release keeps working against the new schema (all pending migrations run in one transaction while it serves).
5. No index built on a large existing table in the migration itself — built `CONCURRENTLY` by hand on staging/production first, migration uses `IF NOT EXISTS`.
6. New tables carry the RLS block (`app_full_access` `TO app`, guarded by `IF EXISTS pg_roles 'app'`).
7. Data-rewriting steps are idempotent, batched by cursor, dry-runnable, and have a consistency query.
8. A `pg_dumpall` snapshot of the target env is taken and its file name recorded before any data-rewriting or destructive step (there are no automated backups).
9. Applied cleanly to a fresh local/test database (`drizzle-kit migrate` output recorded).
10. Migration record written (what ran, where, when, row counts before/after, snapshot ref, down-path or IRREVERSIBLE sign-off).
11. Follow-up created for the later contract step with its earliest date and verification query.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_checklist` entries and apply
standard hook-processing.
