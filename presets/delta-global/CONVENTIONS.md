# Delta-Global conventions encoded by this preset

Every command and workflow in the `delta-global` preset is written against
the facts below, verified against the `platform` and `platform-infra`
repositories on 2026-10-24. When the platform changes, change this file
first, then the commands that cite it. When this file and the platform's own
`CLAUDE.md` / `docs/adr/0000-stack-reference.md` disagree, **the platform
wins** and this file is stale — fix it.

Source of truth inside the platform, in precedence order:
`.specify/memory/constitution.md` → `docs/adr/` (ADR-0000 first) →
`CLAUDE.md` → this file.

---

## 1. Stack

| Layer | What it is | Where |
|---|---|---|
| Web | Next.js 16 App Router, React 19, RSC by default, `next-intl` (en source, fr, es) | `apps/web` — routes under `src/app/[locale]/(dashboard|admin|auth|legal)/` |
| API | Hono 4 + Apollo Server 5 at `/graphql` — **the only API surface** (tRPC removed, spec 024) | `apps/api` |
| Wire contract | GraphQL SDL, field-level auth directives, Codegen with persisted documents | `packages/graphql/schema/NN-<area>.graphql`, generated into `packages/graphql/src/generated/` |
| Validation | Zod v3, single source; Python gets a generated Pydantic mirror | `packages/shared/src/schemas/` · `bun run gen:py-models` |
| DB | Postgres 16 + pgvector, Drizzle ORM, `drizzle-kit generate` | schema `packages/db/src/schema/`, migrations `packages/db/drizzle/`, DB functions `packages/db/src/<area>-dal.ts` |
| Cache | Redis 8 — GraphQL id-list cache, flag cache (`ff:<key>`, 3s), rate limits, pub/sub, locks | never the source of truth; an outage degrades, never takes a surface down |
| Background | Temporal (Postgres backend). **No queue library, no polling loops** | definitions `packages/temporal-workflows/src/`; activities in `apps/workers` (Python 3.12) or `apps/crawler` (TS). Reuse the task queue the worker already polls (e.g. `article-processing`, `apps/workers/src/worker.py`) — CLAUDE.md's `<service>-main` naming is not what runs |
| Auth | BetterAuth 1.7; the graph accepts a bearer JWT only (ADR-0027) — minted at `/api/auth/token`, never a cookie on `/graphql` | |
| Billing | Stripe hosted Checkout + Portal, webhook `POST /webhooks/stripe` (ADR-0032) | plans/prices/entitlements **only** in `packages/shared/src/schemas/billing.ts` |
| Telemetry | OTel → ClickHouse `otel` db → Grafana. App tiers never import a ClickHouse client | errors also to self-hosted GlitchTip via `createErrorReporter` |
| Logs | `@delta-global/logger` (pino) for Node, loguru for Python; `createLogger(deps)` injected, never at module scope in a package | |
| Lint/format | Biome 2 (`bunx biome ci .`) — no ESLint, no Prettier | |
| Package manager | Bun 1.3 (`bun`, `bunx`) — never npm/pnpm/yarn | |
| Secrets | Infisical (project `platform-infra`, path `/app-stack`, env slug = dev/staging/production) → k8s Secret `app-secrets` | local dev: untracked `.env.local`, not `infisical run` |
| Deploy | ArgoCD GitOps from `platform-infra` `charts/app-stack/values-<env>.yaml` | |

## 2. Layering inside `apps/api` (api ADR-0001, amendment 2026-10-16)

| Layer | Path | Rule |
|---|---|---|
| Composition root | `src/index.ts`, `src/graphql/context.ts` | imported by nothing (`api-composition-root-imported-by-none`) |
| Transports | `src/graphql/` (resolvers, directives, plugins, loaders), `src/routes/` | thin: parse, authorize, call a service, map the result |
| Use cases | `src/services/<area>.ts` | transport-agnostic; take `db` / `redis` **as parameters**; no value import of `db`, `cache`, `redis-config`, `env`, `auth`, `cache-aside`, `clients/temporal` (`check:composition-root`) |
| Gateways | `src/dal/`, `src/clients/` | transport-agnostic |
| Entities | `packages/shared`, `packages/db` | |

Admin DB access lives in `packages/db/src/admin-dal.ts` / `apps/api/src/graphql/admin-dal.ts` and is never imported from the web or the reader request path (`scripts/guard-admin-dal-isolation.sh`).

## 3. GraphQL rules

- Every field carries exactly one of `@public` (= any **authenticated** caller), `@auth(role: MEMBER|ADMIN|SUPERADMIN)` (SUPERADMIN aliases ADMIN), `@selfOnly`. Unannotated = denied **and** fails `check:field-auth`.
- Every admin-realm mutation carries `@audited(action: "<area>.<verb>", reason: REQUIRED|OPTIONAL)`; `reason` must be a **top-level argument** of the mutation, or the mutation can never succeed (F-50). `check:field-audit`.
- Expensive fields declare `@cost(weight:, multipliers:)`.
- SCREAMING SDL enums are returned as their NAME, never a lowercase DTO value.
- Lists are cached as **ordered id arrays**, never payloads; paginated lists order by a column **plus an `id` tiebreak**.
- Reader queries project columns (pattern: `articleListColumns()`), never the `articles` table object (embedding + content: 340.7 KB vs 9.1 KB/page).
- Web: one Apollo client per browser session. RSC reads via `src/lib/server/<area>.ts` → `lib/apollo/rsc.ts`; hooks only inside `(dashboard)` and `(admin)/admin`; imperative calls through the surface seam (`src/lib/<area>-api.ts`) via `getBrowserClient()`. Never `new ApolloClient(`. Singletons need `keyFields` or a Save shows stale data (F-43).
- Operations live in `apps/web/src/graphql/<area>.graphql`; `bun --filter='@delta-global/web' codegen` regenerates, `codegen:check` fails on drift.
- A second browser-reachable surface needs an ADR (standing exceptions: `GET /public/share/:token` ADR-0029, `POST /webhooks/stripe` ADR-0032).
- No Server Actions.

## 4. Tenancy & authorization

- **Default model: owner-scoped.** Domain rows carry `owner_id` (`ownerId`); isolation is a DAL predicate on the session's user id, plus a visibility/role gate (e.g. `isPublic`, curated, `role === "admin"`). Org-scoped (`organizationId`, BetterAuth organization plugin, `PUBLIC_ORG_ID` default) exists but is thin — a plan **must declare** which model it uses (Constitution IV).
- The scope key comes from the session/JWT claims, **never from input**.
- Roles: platform `user.role` (`admin` or not) ↔ GraphQL `Role` MEMBER/ADMIN/SUPERADMIN; tenant `member.role` = `owner | admin | member`. **There is no `viewer` role.**
- Admin is a tenant role re-checked server-side on every call (ADR-0013 Addendum 1); the admin UI is `src/app/[locale]/(admin)/admin`.
- RLS: every new table gets a hand-written `drizzle-kit generate --custom` block — RLS on + `app_full_access` policy `TO app USING (true)` guarded by `IF EXISTS pg_roles 'app'` (precedent: migration 0057). RLS is **not** the isolation mechanism; the DAL predicate is. Hand-written SQL must be justified in plan §14 (Complexity Justification).

## 5. Feature flags (ADR-0015)

- Registry: `packages/shared/src/schemas/feature-flags.ts` — add the key to `FEATURE_FLAG_KEYS` **and** `FEATURE_FLAG_METADATA` (compile error otherwise). Python mirror: `apps/workers/src/infrastructure/feature_flags.py`. Seed: `packages/db/src/seeds/feature-flags.ts` (`bun --filter @delta-global/db seed:flags`).
- Key: plain kebab-case, **no `ff-` prefix** — by default the feature slug (`sector-source-overrides`).
- DB-backed (`feature_flags` table), Redis cache 3s, **global boolean only** (per-org overrides deferred in ADR-0015). Plans justify "global" against Principle V's "narrowest granularity". There is no percentage or per-tenant rollout.
- Read: api `isFlagEnabled(key)` wrapped per feature in `apps/api/src/services/<slug>-flag.ts` → `is<Pascal>Enabled()`; RSC `serverFeatureFlag(key)` + `flagAllows()`; client `useFeatureFlag(key)`.
- Toggle: admin mutation `@audited(action: "flags.set")` with a required reason — per environment.
- Defaults OFF and **OFF at merge**. Fails closed on DB/Redis outage — so a flag must never gate whether the graph serves at all (`reader-surface.test.ts`).
- A flag is a real kill switch only if OFF restores today's behaviour exactly — never materialise state that survives flag-OFF.

## 6. Migrations

- `bun run db:generate` (drizzle-kit) — never hand-written, except `--custom` blocks for RLS/triggers/REVOKE/`CHECK … NOT VALID`, justified in plan §14.
- They run in the api `db-migrate` init container (`bun dist/migrate.js`, advisory lock), **all pending migrations in one transaction, while the previous release still serves**. A failed migration blocks the api from starting. So: **expand only** in the release that ships the code.
- `check:migration-expand-contract origin/main` flags DROP TABLE/COLUMN, RENAME, ALTER TYPE, SET NOT NULL, ADD COLUMN NOT NULL without DEFAULT, CREATE INDEX on a pre-existing table, CREATE INDEX CONCURRENTLY. Escape hatch: commit trailer `Allow-Contract-Migration: <migration> <what is removed>; unused since <app> v<x> (#PR), live in staging and production`.
- `check:migration-immutability origin/main`: a migration already on main is never edited, renamed or deleted (renumbering broke dev in 026 → 0056/0057).
- Recipes (`docs/how-to/database-migrations.md`): remove = stop using in N, drop in N+1 with trailer; rename = never (add, dual-write, backfill, switch, remove); retype = new column + dual-write; NOT NULL on existing = backfill in N, `CHECK NOT VALID` + `VALIDATE` in N+1, then `SET NOT NULL`; index on a large existing table = build `CONCURRENTLY` by hand in staging and production first, migration `IF NOT EXISTS` + trailer.
- **There are no database backups** (no barman, no ScheduledBackup, no VolumeSnapshot). Before any migration that rewrites or deletes data in staging/production, take `kubectl -n <env> exec platform-pg-1 -- pg_dumpall -U postgres > backup-<env>-<date>.sql` and record it.
- The api must ship first when a release carries a migration.

## 7. Tests (Constitution III — non-negotiable)

- Order inside each phase: **tests written → tests fail → implement**.
- Runner `bun test` (not vitest); Python `pytest` via `uv run`. Integration tests hit a real, per-run Postgres/Redis (ADR-0023): gate with `describeIntegration` / `itIntegration` (`apps/api/test/helpers/integration.ts`, copied verbatim per package) and `requireRedis()`; any other skip idiom fails `check:integration-skip`, and under `CI` a skip fails.
- Local integration runs: port-forward `svc/platform-pg-test-rw` (`platform` ns) to 15432, `drizzle-kit migrate`, set `INTEGRATION_DB_URL`.
- API tests: `apps/api/test/<slug>/{services,dal,resolvers,authz,audit}.test.ts`. Other packages colocate `foo.test.ts`.
- **`@critical`** = a substring in the test name of api integration tests covering isolation/authorization (every mutation needs one). It is **not** an E2E tag here.
- Web DOM tests: `*.test.tsx` calling `installDom()` (`apps/web/test/dom.ts`, happy-dom + Testing Library), run with `bun test --parallel`.
- E2E: Playwright in `apps/web/e2e/<slug>.spec.ts`, tag `@smoke` for the PR subset; runs **nightly** (`e2e.yml`) and does not gate PRs.
- Temporal: every registered workflow type has a replay history in `packages/temporal-workflows/test/histories/`; a failing replay means `patched()`, **never** a regenerated fixture.
- Never `quit()` the shared Redis client in an api test file.
- Coverage: TS lcov + `diff-cover`; the 70 %-of-changed-lines gate is due 2026-10-24 — check `ci.yml` before claiming it is enforced.

## 8. Gate battery (what CI actually runs)

| Gate | Command |
|---|---|
| Lint | `bunx biome ci .` |
| Dependency rules | `bun run depcruise` |
| Composition root | `bun run check:composition-root` |
| tRPC stays gone | `bun run check:trpc-removal` |
| Typecheck (+ `check:field-auth`, `check:field-audit`, `check:log-hygiene`, `check:contrast` via turbo deps) | `bun run typecheck` (CI: `typecheck:affected`) |
| GraphQL codegen drift | `bun --filter='@delta-global/web' codegen:check` |
| Python model drift | `bun run check:py-models` |
| Migrations | `bun run check:migration-immutability origin/main && bun run check:migration-expand-contract origin/main` |
| SVG | `bun run check:svg-assets` |
| i18n | `bun run scripts/i18n-parity.ts && bun run scripts/i18n-scan.ts` |
| Tests | `bun run test` (CI: `test:affected --coverage`) then `bun run check:integration-skip` |
| Web bundle budget | `bun run turbo run build --filter=@delta-global/web && bun --filter=@delta-global/web perf:budget` |
| Python | `cd apps/workers && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest tests/` |
| Secrets | `gitleaks detect --source . --redact --no-banner` |
| Admin DAL isolation (pre-commit only — not in CI) | `bash scripts/guard-admin-dal-isolation.sh` |
| Build | `bun run build` |

GitHub Free: there are no required status checks (ADR-0006). The hard
enforcement points are pre-commit/pre-push hooks and `scripts/ci-release-gate.sh`
at release time. "CI is green" must be checked, not assumed.

## 9. Observability

- Spans: `user.id`, `graphql.operation.name`, `graphql.operation.type`, `org.id` where an org exists. Logs: `userId`, `trace_id`/`span_id` (absent, not empty, with no active trace).
- Three separate systems (ADR-0024): debugging (30 d, sampled) · audit (`audit_log`, 5 y, append-only, never stdout) · KPI (`kpi_daily`).
- Metric labels bounded: ≤ 5,000 active series total, ≤ 500 per metric name; never user/tenant/article id, URL, raw query, trace/session id.
- Never log request bodies, headers, cookies or raw emails (`check:log-hygiene`).
- Analytics events reach ClickHouse only via `apps/workers` or an analytics job; with none, the plan states "ClickHouse events: 0".
- Async operations emit start/complete/fail with duration.
- Errors: report beside existing handling via `createErrorReporter` (never `@sentry/bun`/`@sentry/node`); client- or source-caused failures and Temporal `BENIGN` are not reported.

**As code, in `platform-infra`** (anything built only in the Grafana UI is lost on restart):

- Alert rules: `charts/grafana/alerting/<NNN>-<slug>.json`, Grafana file-provisioning JSON (`{"apiVersion":1,"groups":[…]}`), ClickHouse datasource uid `clickhouse-otel` (Prometheus `prometheus` for cluster/datastore), scoped to `ResourceAttributes['deployment.environment']='production'`.
- Labels `severity` = `page | ticket | info`, `service`; annotation `runbook_url` → `platform/docs/runbooks/<slug>.md`. **No templates in annotations or labels** (`{{ }}`, `$labels`, `$values`) — Discord (ADR-0030); `check-alert-annotations.sh`.
- Dashboards: `charts/grafana/dashboards/<NNN>-<slug>.json` (sub-folder `performance/` for App Performance). Filenames unique across folders.
- SLOs: `charts/grafana/slo/025-slis.yaml` (availability 99.5 %, latency 95 % < 500 ms, ingestion freshness 95 % < 30 min, 30 d) with burn-rate rules; `check-slo-windows.sh`.
- Alert/contact-point changes take effect only after `kubectl -n observability rollout restart deploy/grafana` (ArgoCD shows Synced while the old config runs).

## 10. Secrets, config & egress

- New secret = a key at Infisical `/app-stack` for **each** env slug; no chart change; pods pick it up on restart. Never add an inline chart default for a key Infisical owns (inline `env` wins over `envFrom`).
- Non-secret config: `charts/app-stack/templates/_helpers.tpl` `app-stack.commonEnv` or the per-app template.
- Env vars are validated (`@t3-oss/env-nextjs` web, `@t3-oss/env-core` api) and listed in `.env.example`.
- New outbound host = a row in `CLAUDE.md` *Approved External Services* + an ADR + `charts/network-policies/values.yaml` (`egress.fqdns.<component>` or `ciliumEgress.allowed[]` with `adr`). Policies are not enforced yet (flannel) — write them anyway. A config file that gives a pod a new address counts (the Discord lesson).
- Every outbound call has a timeout and a retry budget; LLM calls go through OpenRouter with a cost cap.

## 11. Delivery

- Branches: `/speckit.specify` creates `NNN-<slug>` through the git extension (`branch_numbering: sequential`, as 026 did); hand-made branches follow `<type>/<short-desc>-<short-id>` (`^(feat|fix|chore|docs|refactor|perf|test|build|ci|release)/[a-z0-9-]+-[a-z0-9]{4,}$`, manual-stage hook). Workflows only refuse to run on `main`/`staging`/`production`. Never push to those three.
- Conventional Commits, scopes: web, api, crawler, workers, db, shared, ui, connectors, temporal-workflows, config, infra, ci, deps, release. Squash-merge, PR number in the subject.
- Large features: **one phase = one commit (and PR); a phase does not start before the previous phase's ACs pass** (025 FR-072).
- PR body states: migration · flag · env vars · egress · rollback plan.
- Release: `scripts/release.sh <app…>` → empty `release(<app>): <subject>` commit per app (lowercase subject, one push per app, api first with a migration) → Release workflow (gated by `ci-release-gate.sh`) → image `ghcr.io/delta-global/platform/<app>:<semver>` + tag `<app>-v<semver>` → `platform-released` dispatch pins **dev** (which runs no app pods).
- Staging: `uv run scripts/ship.py promote --env staging <apps>` → commit `chore(deploy): pin staging to <app> <ver>` in `platform-infra` `charts/app-stack/values-staging.yaml` (auto-sync) → verify **the feature**, `db-migrate` logs, `build_info` → `ship.py verify --env staging`.
- Production: explicit human OK, pin exactly what was verified on staging, `argocd app diff app-stack-production`, `argocd app sync app-stack-production` (no auto-sync), `ship.py verify --env production`.
- **Rollback is a pin** (`ship.py promote --env <env> --to <previous>`), not a revert — or flag OFF.
- Per-env switches live in the same values files (`api.migrate.enabled`, `billingMaintenance.enabled`, `telemetry.enabled`, …).

## 12. Spec artifacts (what real specs look like)

- `specs/NNN-<slug>/`: `spec.md`, `plan.md`, `tasks.md`, `research.md` (`R1…`), `data-model.md`, `quickstart.md`, `contracts/schema.graphql`, optional `checklists/`, `verify-report.md`, `follow-ups.md`. Numbers are sequential — check for collisions before creating (026 was used twice).
- Pre-spec research: `docs/research/<YYYY-MM-DD>-<slug>/brief.md` + `sources.md` (`/speckit.research`).
- spec header: Feature slug · Feature flag · Feature branch · Created · **Status** · **Verified** (what automation vs a human verified) · RFC/ADR · Input.
- IDs: `FR-###` (suffixes `FR-007a`, amendments dated inline) · `AC-###` numbered globally, binary, under each story (EARS or Given/When/Then) · `US#` / Story N (P1, P2…) · `T###` tasks as `- [ ] T015 [P] [US1] description — exact/path.ts (AC-012)` · research `R#` · open questions `Q#`.
- tasks.md is grouped **by user story** (Setup → Foundational → US1 🎯 MVP → … → Polish), each story with *Tests first* then *Implementation*.
- plan.md sections 1–14: Drizzle Schema · Zod Contracts · GraphQL Operations · DAL · Services · Feature Flag · RBAC Matrix · Cache Strategy · Background Jobs (Temporal) · Observability Plan · Testing Plan · Security Checklist · Open Questions · Complexity Justification — plus Summary, Stack Reference, File Map, Service Interaction Map.
- Measured facts beat assumptions: write "measured <date> on <env>: …". Never rewrite history — amend with a date.
- Manual Verification: UI acceptance criteria a human must click through are listed and recorded, never silently assumed.

## 13. Recurring failure modes the kit must prevent

1. Gates that look enforced but aren't (silent skips, empty depcruise, lint on 4/12 workspaces).
2. Follow-ups claimed "landed" but never applied (stale templates/docs).
3. Migrations that break the running release (drop in same release, blocking index, edited migration).
4. Merge ≠ deploy; stale pins; prod changing without promotion.
5. Silent data/pipeline loss (jobs failing nightly, work silently skipped).
6. Failure isolation (cache outage takes API down, no timeouts, flags failing closed).
7. Auth/session leaks across accounts in the same tab; admin UI rendering for non-admins.
8. Audit contract mistakes (`reason` not top-level).
9. Web data-layer inconsistency (two Apollo clients, missing `keyFields`).
10. Raw server/DB error text shown to readers.
11. Over-fetching, N+1, bundle bloat.
12. Egress & SSRF (user-submitted URLs reaching internal addresses; egress via config).
13. Unbounded cost and growth (uncapped AI spend, paid retries, no retention — ADR-0034).
14. Secrets/infra hygiene (unrotated keys, no backups).
15. "Implemented" without verification (paths only failing on real data, unclicked UI).
