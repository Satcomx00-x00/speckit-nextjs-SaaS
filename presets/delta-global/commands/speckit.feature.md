---
description: Full vertical-slice scaffold for the Delta-Global platform — Zod contract in packages/shared → Drizzle table (+ RLS --custom block) → packages/db DAL functions → transport-agnostic service (db/redis as parameters) → SDL with field-level auth directives → thin resolver → codegen → RSC read through lib/server and client writes through hooks/seams → Temporal side effects → flag, observability, i18n — tests first at every layer, one commit per phase.
handoffs:
  - label: Plan the feature
    agent: speckit.plan
    prompt: Generate the full feature plan (14 sections + Service Interaction Map) for the feature described in $ARGUMENTS.
  - label: Scaffold the GraphQL slice
    agent: speckit.scaffold.graphql
    prompt: Scaffold the SDL, resolvers and web operations for this feature.
  - label: Scaffold the route
    agent: speckit.scaffold.route
    prompt: Scaffold the App Router route segment for this feature.
  - label: Scaffold the DAL
    agent: speckit.scaffold.dal
    prompt: Scaffold the packages/db DAL functions and the service for this feature.
  - label: Scaffold Temporal workflow
    agent: speckit.scaffold.temporal
    prompt: Scaffold the Temporal workflow and activities for this feature's async side effects.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check the scaffolded feature against spec and plan for drift, RBAC gaps and hard-constraint violations.
---

## User Input

```text
$ARGUMENTS
```

Extract (ask **one** grouped question if anything decisive is missing, then proceed on stated assumptions):

| Field | Values | Default |
|---|---|---|
| slug | kebab-case | required |
| entities | tables, fields, relations | inferred |
| tenancy model | owner-scoped (`{{ var.tenancy_column }}`) · org-scoped (`organizationId`) | `{{ var.tenancy_model }}` |
| audience | reader (`(dashboard)`) · admin (`(admin)/admin`, `@auth(role: ADMIN)` + `@audited`) · both | reader |
| background work | none · Temporal workflow (workers / crawler) | none |
| external services | OpenRouter / Stripe / other (other = ADR + egress) | none |
| flag | plain kebab-case key, no `ff-` prefix | the slug |

**Prefer the plan.** If `specs/<NNN>-<slug>/plan.md` exists, its File Map and sections 1–12 are the contract: scaffold what it lists, in its order, and report any divergence instead of improvising. Without a plan, say so and recommend `/speckit.plan` for anything beyond a small slice.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_feature`. Apply standard hook-processing: skip `enabled: false`, skip non-empty `condition`, surface optional hooks, execute mandatory hooks and wait for them.

Read `.specify/memory/constitution.md`, `CLAUDE.md` (*How to Add a Feature*, *Forbidden Patterns*, *Approved External Services*) and `docs/how-to/database-migrations.md`. The `delta-global` preset's `CONVENTIONS.md` summarises them; the platform files win on conflict.

Stop with a CRITICAL note — do not scaffold around it — if the feature as described would need any of: a second API surface, a Server Action, a ClickHouse client in `apps/api`/`apps/web`, a queue library or polling loop, a flag that gates whether the graph serves, a non-expand migration in the same release, a new outbound host without an ADR, or prices/entitlements outside `packages/shared/src/schemas/billing.ts`.

## How the slice is delivered

- **Tests first, every phase** (Constitution III): write the tests → run them → see them fail → implement → see them pass. A phase is not done on green typecheck alone.
- **One phase = one commit**, Conventional Commit with a real scope (`feat(shared): …`, `feat(db): …`, `feat(api): …`, `feat(web): …`, `feat(workers): …`). A phase does not start before the previous phase's acceptance criteria pass.
- Branch `feat/<slug>-<short-id>` (≥ 4 chars id). Never commit to `main`.
- The flag exists from Phase 0 and is **OFF at merge**.

## Phases

### Phase 0 — Flag & contracts (`packages/shared`)

1. Flag: add `"<slug>"` to `FEATURE_FLAG_KEYS` **and** `FEATURE_FLAG_METADATA` in `packages/shared/src/schemas/feature-flags.ts`; mirror it in `apps/workers/src/infrastructure/feature_flags.py` if workers read it; seed it in `packages/db/src/seeds/feature-flags.ts` (`bun --filter @delta-global/db seed:flags`). Add `apps/api/src/services/<slug>-flag.ts`:

   ```ts
   import { isFlagEnabled } from "./feature-flags";
   /** <Feature> flag (spec NNN). OFF serves today's behaviour exactly — say why that holds. */
   export function is<Pascal>Enabled(): Promise<boolean> {
     return isFlagEnabled("<slug>");
   }
   ```

   The flag is global (one boolean). Document in the JSDoc what OFF means and that it fails closed — and why closed is safe for this feature.

2. Zod: `packages/shared/src/schemas/<slug>.ts` — one input schema per mutation/argument set, DTO types via `z.infer`, error codes as `as const` + union, branded ids where the domain has them. Export from `packages/shared/src/index.ts`. Never redefine an existing schema. If Python reads it: `bun run gen:py-models` and commit `generated.py`.

Tests: `packages/shared/src/schemas/<slug>.test.ts` — accepts valid, rejects each constraint (empty, max length + 1, Unicode, emoji).

### Phase 1 — Schema & migration (`packages/db`)

1. `packages/db/src/schema/<area>.ts` (or the existing area file): `snake_case` plural table, `{{ var.tenancy_column }}` FK + index for owner-scoped data, `created_at`/`updated_at` with timezone, explicit unique/check constraints, an index serving every list predicate + order (`(… , created_at desc, id)`). Export row/insert types.
2. `bun run db:generate` — never hand-write the generated SQL. Read the output: it must be **expand-only** (new table, nullable column, column with a constant default). Anything else follows the recipes in `docs/how-to/database-migrations.md` across two releases.
3. RLS block for a **new table** — `bunx drizzle-kit generate --custom --name=enable_rls_<table>` (run in `packages/db`), filled with the 0057 shape:

   ```sql
   DO $$
   DECLARE
     has_app BOOLEAN := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app');
   BEGIN
     ALTER TABLE public.<table> ENABLE ROW LEVEL SECURITY;
     IF has_app THEN
       DROP POLICY IF EXISTS app_full_access ON public.<table>;
       CREATE POLICY app_full_access ON public.<table>
         FOR ALL TO app USING (true) WITH CHECK (true);
     END IF;
   END $$;
   ```

   This is the one sanctioned hand-written SQL; record it in plan §14 *Complexity Justification*. RLS is not the isolation mechanism — the DAL predicate is.
4. `bun run db:migrate` against the local/test database; `bun run check:migration-immutability origin/main && bun run check:migration-expand-contract origin/main`.
5. Seed data that makes isolation testable: **two owners** with data each, realistic values (no `foo`/`test1`), Unicode and max-length rows — in the feature's test fixtures, and in `packages/db/src/seeds/` only if dev needs it.

### Phase 2 — DB functions & service (`packages/db`, `apps/api/src/services`)

Follow `/speckit.scaffold.dal`. In short:

- `packages/db/src/<slug>-dal.ts`: one function per use case, `db: DbExecutor` first, scope predicate from the caller's viewer id on every scoped query, projected columns, cursor + `id` tiebreak, no N+1. Export from `packages/db/src/index.ts`.
- `apps/api/src/services/<slug>.ts`: receives `db` / `redis` / Temporal client **as parameters** (`check:composition-root`), owns authorization (`can<Feature>(role, action)` or an ownership gate), the flag check, rate limits on writes, cache-tag invalidation (`cache-tags.ts` + `invalidateTags()`), and typed errors (`class <Feature>Error extends Error { code }`). Lists cache ordered id arrays; a Redis failure falls back to the DB.

Tests (`apps/api/test/<slug>/`): `dal.test.ts` and `authz.test.ts` under `describeIntegration(... — @critical)` — owner A vs owner B on every read and write, non-admin vs admin, a smuggled scope id ignored; `services.test.ts` with fakes for injected stores. Every **mutation** has at least one `@critical` isolation test.

### Phase 3 — GraphQL surface (`packages/graphql`, `apps/api/src/graphql`)

Follow `/speckit.scaffold.graphql`. In short:

- SDL in `packages/graphql/schema/NN-<area>.graphql`: every field `@public` | `@auth(role: …)` | `@selfOnly`; admin mutations `@audited(action: "<area>.<verb>")` with `reason: String!` as a top-level argument; `@cost` on list fields; SCREAMING enums returned by NAME.
- Resolver `apps/api/src/graphql/resolvers/<slug>.ts`: parse with the Zod schema, `requireViewer(ctx)` / `viewerIsAdmin(ctx)`, one service call, typed `GraphQLError` codes — never raw DB text. Register in `resolvers/index.ts`.
- Web operations `apps/web/src/graphql/<slug>.graphql`, then `bun --filter='@delta-global/web' codegen` and `codegen:check`.

Tests: `resolvers.test.ts`, `audit.test.ts` for admin mutations (row written with action + reason; the mutation succeeds with a reason). Gates: `bun run check:field-auth && bun run check:field-audit`.

### Phase 4 — Background work (only if the plan has it)

Follow `/speckit.scaffold.temporal`: deterministic workflow in `packages/temporal-workflows/src/workflows/<area>.ts`, activities in `apps/workers` (Pydantic-validated) or `apps/crawler`, idempotent workflow id from the business key, bounded retries and timeouts, BENIGN for expected failures, start/complete/fail events, a recorded replay history. The API service starts it; the workflow never reads the flag.

### Phase 5 — Web (`apps/web`)

Follow `/speckit.scaffold.route`. In short:

- Read path: async RSC `page.tsx` under `src/app/[locale]/(dashboard)/<slug>/` (or `(admin)/admin/<slug>/`), localized `generateMetadata` title, `Suspense` around the data, reads through `src/lib/server/<slug>.ts` returning `Result` — a failed read degrades, never throws across the RSC wire.
- Write path: `'use client'` leaf components using `useMutation` (inside `(dashboard)`/`(admin)`) or the seam `src/lib/<slug>-api.ts`; the form schema is the shared Zod schema; server error codes map to fields; submit disabled while pending; cache updated through Apollo (`keyFields` on singletons, `refetchQueries` or cache `modify` on lists) — no second client, no `fetch('/graphql')`.
- Flag: `serverFeatureFlag("<slug>")` + `flagAllows()` in RSC, `useFeatureFlag("<slug>")` in client leaves; OFF renders today's UI.
- Four states (loading skeleton · empty with CTA · `RouteError` with `retry()` · success), WCAG 2.2 AA, 44×44 px targets, keyboard complete, `aria-live` for async results.
- i18n: every string in `apps/web/messages/<locale>.json` for each of {{ var.locales }}; `scripts/i18n-parity.ts` and `scripts/i18n-scan.ts` clean.
- Images via `next/image` + `httpsImageUrl()`; heavy client components through `next/dynamic`.

Tests: DOM tests `*.test.tsx` with `installDom()` for each state and the flag-OFF render; `src/app/route-conventions.test.ts` green; an E2E `apps/web/e2e/<slug>.spec.ts` tagged `@smoke` for the primary path (it runs nightly; it does not gate the PR — say so in the PR).

### Phase 6 — Observability, cost & operability

- Spans carry `user.id`, `graphql.operation.name`/`type` (added by the GraphQL plugin — verify the resolver runs inside an active span), `org.id` where an org exists. Logs through `@delta-global/logger` with `userId` + `trace_id`; never a body, header, cookie or raw email (`check:log-hygiene`).
- Metrics only with bounded labels (≤ 500 series per name; no user/sector/article ids). Admin actions → `audit_log` via `@audited`, never stdout.
- Analytics events: ClickHouse only through `apps/workers` / an analytics job — otherwise state "ClickHouse events: 0".
- Unexpected errors reported with `createErrorReporter` beside the existing handling.
- If the plan has rollback thresholds: the alert rules and dashboard are a `platform-infra` change (`charts/grafana/alerting/<NNN>-<slug>.json`, `charts/grafana/dashboards/<NNN>-<slug>.json`, `runbook_url` → `docs/runbooks/<slug>.md`, no templates in annotations). Write the runbook here; list the infra PR as a follow-up if it is not opened in this run.
- New secrets: Infisical `/app-stack` for each of dev/staging/production + `env.ts` validation + `.env.example`. New outbound host: ADR + *Approved External Services* row + `charts/network-policies/values.yaml` entry.

## Ship checklist (print it filled in)

```markdown
- [ ] Flag `<slug>` in FEATURE_FLAG_KEYS + METADATA (+ Python mirror, seed) — default OFF
- [ ] Migrations expand-only; RLS block for every new table; immutability + expand-contract checks clean
- [ ] Every mutation has an `@critical` isolation test against a real Postgres
- [ ] Every new field annotated; every admin mutation `@audited` with top-level `reason`
- [ ] codegen:check clean; no `new ApolloClient(`; no Server Action; no tRPC reference
- [ ] i18n parity + scan clean for {{ var.locales }}
- [ ] Gate battery green (lint, depcruise, composition-root, typecheck, codegen, py-models, tests, integration-skip, bundle budget, python, gitleaks)
- [ ] Runbook written; alert/dashboard infra PR opened or listed as follow-up
- [ ] PR body: migration · flag · env vars · egress · rollback plan (flag OFF, or pin back)
```

## Post-Scaffold Verification

Run and report each command with its exit code — a failure is reported, never worked around:

```bash
bunx biome ci .
bun run depcruise && bun run check:composition-root && bun run check:trpc-removal
bun run typecheck
bun --filter='@delta-global/web' codegen:check
bun run check:py-models
bun run check:migration-immutability origin/main && bun run check:migration-expand-contract origin/main
bun run scripts/i18n-parity.ts && bun run scripts/i18n-scan.ts
bun run test && bun run check:integration-skip
bash scripts/guard-admin-dal-isolation.sh
```

## Feature scaffold complete

Summarise: files created per phase, the commit per phase, the flag key and what OFF does, the scope predicate, the tests written (with the `@critical` ones named), and every check result. Then offer `/speckit.verify` — the scaffold is not done until verify has evidence for each acceptance criterion.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_feature`. Apply standard hook-processing.
