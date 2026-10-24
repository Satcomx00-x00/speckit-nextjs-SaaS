# Implementation Plan: [FEATURE NAME]

**Feature slug**: `[feature-name]`
**Feature flag**: `[feature-name]` (default: OFF, global — ADR-0015) | none: [reason]
**Branch**: `feat/[feature-name]-[short-id]`
**Date**: [DATE]
**Spec**: [spec.md] · **Research**: [research.md R1…Rn] · **Brief**: [docs/research/… | none]
**Tenancy model**: owner-scoped | org-scoped — [one line why]
**ADR**: none — [why no trigger applies] | ADR-NNNN: [title]
**Constitution**: v[x.y.z] — principles touched: [I, III, IV, V…]; deviations in §14

**Note**: Filled by `/speckit.plan`. Section numbers are stable (1–14) — other
commands, tasks and verify reports cite them. A section that does not apply
stays, with one line saying why.

---

## Summary

[Primary requirement + chosen approach in 2–3 sentences. The one design decision a reviewer must not miss.]

---

## Stack Reference

Delta-Global stack as pinned by ADR-0000 — list only the layers this feature touches, with the exact package/path. Anything not in ADR-0000 is a deviation (→ ADR).

| Layer | Technology | Path |
|---|---|---|

---

## File Map

```text
packages/
├── shared/src/schemas/[feature-name].ts          ← Zod inputs/DTOs/error codes (single source)
├── shared/src/schemas/feature-flags.ts           ← + key in FEATURE_FLAG_KEYS and FEATURE_FLAG_METADATA
├── db/src/schema/[feature-name].ts               ← Drizzle table(s)
├── db/drizzle/NNNN_*.sql                         ← generated (+ --custom RLS block)
├── db/src/[feature-name]-dal.ts                  ← DB functions (scope predicate, projection)
├── db/src/seeds/feature-flags.ts                 ← + flag row (OFF)
└── graphql/schema/NN-[area].graphql              ← SDL with @public/@auth/@selfOnly/@audited/@cost

apps/api/src/
├── services/[feature-name].ts                    ← use cases; db/redis as parameters
├── services/[feature-name]-flag.ts               ← is[Feature]Enabled()
└── graphql/resolvers/[feature-name].ts           ← thin transport
apps/api/test/[feature-name]/
├── services.test.ts · dal.test.ts · resolvers.test.ts · authz.test.ts (@critical)

apps/web/
├── messages/{en,fr,es}.json                      ← new keys, parity
├── src/graphql/[feature-name].graphql            ← operations → codegen
├── src/lib/server/[feature-name].ts              ← RSC reads (server-only)
├── src/lib/[feature-name]-api.ts                 ← imperative seam via getBrowserClient()
├── src/app/[locale]/(dashboard)/[feature-name]/  ← page.tsx · loading.tsx (error.tsx at group level)
├── src/components/[feature-name]/*.tsx (+ *.test.tsx with installDom())
└── e2e/[feature-name].spec.ts                    ← @smoke subset

packages/temporal-workflows/src/[feature-name].ts ← workflow + signals (if any)
apps/workers/src/…  |  apps/crawler/src/…         ← activities (if any)

platform-infra/
├── charts/grafana/alerting/[NNN]-[feature-name].json
├── charts/grafana/dashboards/[NNN]-[feature-name].json
└── charts/network-policies/values.yaml           ← only if new egress
```

---

## Service Interaction Map

> Mandatory sweep — one row per platform service, explicit verdict. "No"
> needs a one-line reason; no blank rows. Every "yes" is reflected in §1–§13
> and gets a failure-mode test in §11. `/speckit.verify` checks this map
> against the diff in both directions.

| Service | Touched? | Interaction | Changes | If down / slow |
|---|---|---|---|---|
| Web (Next.js, RSC + Apollo client) | | | | |
| API (Hono + Apollo `/graphql`) | | | | |
| Postgres (`platform-pg`) | | | | |
| Redis (id-list cache, flags, rate limits, pub/sub, locks) | | | | must degrade, never take the surface down |
| Temporal | | | | |
| Python workers (`apps/workers`) | | | | |
| Crawler (`apps/crawler`) | | | | |
| SSE subscriptions (ADR-0021) | | | | |
| BetterAuth / JWT (`/api/auth/token`) | | | | |
| Stripe (`apps/api` only) | | | | |
| OpenRouter (workers; api catalog only) | | | | timeout / retry / fallback / cost cap |
| Object storage (ADR-0010) | | | | |
| Telemetry (OTel → ClickHouse → Grafana) / GlitchTip | | | | never blocks a request |
| Other external host | | | | **new egress → ADR + NetworkPolicy** |

---

## 1. Drizzle Schema

**File**: `packages/db/src/schema/[feature-name].ts` · Tables `snake_case` plural, columns `snake_case`.

| Table | Key columns | Indexes | Relations / onDelete |
|---|---|---|---|
| `[feature_snakes]` | `id` (project PK convention), scope key `{{ var.tenancy_column_snake }}` → `{{ var.tenant_table }}`, `created_at timestamptz`, `updated_at timestamptz` | `({{ var.tenancy_column_snake }}, created_at desc, id)` | |

**Migration** (CONVENTIONS §6):
- Expand-only in this release? yes / no → which recipe, which later release contracts.
- Statements `check:migration-expand-contract` will flag, and whether an `Allow-Contract-Migration:` trailer is justified.
- New table → `--custom` RLS block (RLS on + `app_full_access` TO `app`), justified in §14.
- Large existing table touched → index built `CONCURRENTLY` by hand in staging/prod first.
- Data rewritten/deleted in staging/prod → `pg_dumpall` snapshot first (no backups exist).

---

## 2. Zod Contracts

**File**: `packages/shared/src/schemas/[feature-name].ts` — `z.infer` is the only TS type; no duplicate interfaces.

| Schema | Kind | Used by (resolver / service / worker) |
|---|---|---|

Python reads it? → add to `scripts/gen-py-models.ts`, run `bun run gen:py-models`.

---

## 3. GraphQL Operations

**SDL**: `packages/graphql/schema/[NN]-[area].graphql` · **Resolvers**: `apps/api/src/graphql/resolvers/[feature-name].ts` (thin: parse → authorize → service → map).

| Field | Query/Mutation | Args → Return | Directive(s) | `@cost` | Service fn | Error codes |
|---|---|---|---|---|---|---|

Rules: every field has `@public`/`@auth`/`@selfOnly`; admin mutations `@audited(action: "[area].[verb]")` with `reason` top-level; SDL enums returned as NAMES; lists return ordered ids + a dataloader; typed error codes, never raw DB/server text. Web operations in `apps/web/src/graphql/[feature-name].graphql`; regenerate with `bun --filter='@delta-global/web' codegen`.

---

## 4. DAL

**File**: `packages/db/src/[feature-name]-dal.ts` (admin-only access → `admin-dal.ts`, isolated by `guard-admin-dal-isolation.sh`).

| Function | Params (scope key explicit) | Returns | Projection | Pagination |
|---|---|---|---|---|

Every query carries the scope predicate for the declared tenancy model; explicit column projection (never a wide table object); cursor pagination with `id` tiebreak; batched/`with` fetches — no N+1.

---

## 5. Services

**File**: `apps/api/src/services/[feature-name].ts` — transport-agnostic; `db` / `redis` passed as parameters (`check:composition-root`); `Result<T, E>` at the boundary; `now`/`rng` injected where behaviour depends on them.

| Function | Input | Result | Notes |
|---|---|---|---|

---

## 6. Feature Flag

| Property | Value |
|---|---|
| Key | `[feature-name]` (no prefix) |
| Registry | `packages/shared/src/schemas/feature-flags.ts` (KEYS + METADATA) · python mirror `apps/workers/src/infrastructure/feature_flags.py` (if workers read it) · seed `packages/db/src/seeds/feature-flags.ts` |
| Granularity | global (the only one ADR-0015 offers) — justify against Principle V |
| Guards | api `is[Feature]Enabled()` in the service/resolver; RSC `serverFeatureFlag` + `flagAllows`; client `useFeatureFlag` |
| OFF behaviour | identical to today because [reason] |
| Toggle | `setFeatureFlag` (`@auth(role: SUPERADMIN)`, `@audited(action: "flags.set")`, reason) per env; ≤ 3 s |
| Removal | after [N] weeks stable ON in production → cleanup PR |

---

## 7. RBAC Matrix

| Action (field) | Reader | Resource owner | Org owner/admin/member (if org-scoped) | Platform admin | Enforced by |
|---|---|---|---|---|---|

Role from the session/JWT, never from input. Admin is re-checked server-side on every call (ADR-0013 Addendum 1).

---

## 8. Cache Strategy

| Key | Holds (ordered ids, not payloads) | TTL | Invalidated by | Blast radius of one write |
|---|---|---|---|---|

Redis unreachable → [fallback: read-through to Postgres / skip cache]. Apollo client: `keyFields` for singletons, which queries refetch after each mutation.

---

## 9. Background Jobs (Temporal)

| Side effect | Workflow / activity | Where | Workflow ID (deterministic) | Retry / timeouts | BENIGN errors |
|---|---|---|---|---|---|

Or: "None — all work is synchronous within the request (p95 budget: …)". Never a polling loop. Changing an existing workflow → `patched()` + replay history.

---

## 10. Observability Plan

| Signal | Name / attributes (bounded labels only) | Emitted where | Lands in |
|---|---|---|---|
| Span | `graphql.operation.name`, `user.id` | | ClickHouse traces |
| Log | `userId`, `trace_id` — no bodies/headers/emails | | ClickHouse logs (30 d) |
| Audit | `[area].[verb]` | `@audited` | `audit_log` (5 y) |
| KPI | | | `kpi_daily` |
| Metric | | | ClickHouse metrics (≤ 500 series) |
| Error | | `createErrorReporter` | GlitchTip |
| ClickHouse events | 0 (unless written by workers/analytics jobs) | | |

**Alerts** (one per spec rollback threshold) → `platform-infra/charts/grafana/alerting/[NNN]-[feature-name].json`: severity page/ticket/info, `service` label, `runbook_url` → `platform/docs/runbooks/[feature-name].md`, no templating in annotations, scoped to production. **Dashboard** → `charts/grafana/dashboards/[NNN]-[feature-name].json`.

---

## 11. Testing Plan

Tests first in every phase. Integration tests use `describeIntegration`/`itIntegration` and `requireRedis()` on a real Postgres/Redis.

| Test | File | Runner | Covers (AC / failure mode) |
|---|---|---|---|
| Service unit | `apps/api/test/[feature-name]/services.test.ts` | bun test | |
| DB functions | `apps/api/test/[feature-name]/dal.test.ts` | bun test + real PG | |
| Resolvers | `apps/api/test/[feature-name]/resolvers.test.ts` | bun test + real PG/Redis | |
| Isolation / authz — **@critical** | `apps/api/test/[feature-name]/authz.test.ts` | bun test + real PG | another user's rows invisible; non-owner/non-admin FORBIDDEN; scope key from input ignored |
| Audit | `apps/api/test/[feature-name]/audit.test.ts` | | each `@audited` mutation writes one row, reason required |
| Flag OFF | | | behaviour identical to today |
| Dependency down (one per touched service) | | | |
| Web DOM | `apps/web/src/components/[feature-name]/*.test.tsx` | bun test --parallel + installDom() | four UI states, a11y |
| Python | `apps/workers/tests/test_[feature].py` | pytest | |
| Temporal replay | `packages/temporal-workflows/test/histories/` | bun test | |
| E2E `@smoke` | `apps/web/e2e/[feature-name].spec.ts` | Playwright (nightly) | |

---

## 12. Security Checklist

- [ ] Scope key from session/JWT on every query; never from input
- [ ] Every field annotated; admin mutations `@audited`; `check:field-auth` + `check:field-audit` pass
- [ ] Every untrusted boundary Zod-parsed (args, webhooks, Temporal payloads, env)
- [ ] User-supplied URLs cannot reach internal addresses (SSRF)
- [ ] Rate limit / `@cost` on expensive or abusable fields
- [ ] Secrets in Infisical `/app-stack` (each env) + `env.ts` + `.env.example`; no chart default
- [ ] New outbound host: CLAUDE.md table + ADR + `charts/network-policies` entry — or "none"
- [ ] No raw error text to readers; no PII in logs, spans, metric labels
- [ ] Stripe: prices resolved server-side from `BILLING_PLANS`; webhook events are "go and look", never applied as state

---

## 13. Open Questions

1. Q1: …

---

## 14. Complexity Justification

<!-- Every intentional deviation from a constitution MUST (e.g. a hand-written --custom migration, a flag that cannot be narrower than global, a second surface). One row each; "None" if none. -->

| Deviation | Principle | Why needed | Simpler alternative rejected because |
|---|---|---|---|
