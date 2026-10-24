---
description: Delta-Global cross-artifact drift detector. Cross-checks spec ↔ plan ↔ tasks ↔ code for the real stack — GraphQL SDL ↔ resolver ↔ service ↔ packages/db DAL, field auth directives, @audited admin mutations, Zod ↔ SDL inputs, id-list cache invalidation, RBAC (owner/admin/member + platform admin), declared tenancy predicate, DB-backed flag registration, expand-only migrations, Service Interaction Map, FR/AC ↔ T### coverage, and the CLAUDE.md forbidden patterns. Read-only; reports CRITICAL/HIGH/MEDIUM/LOW findings.
handoffs:
  - label: Fix the findings
    agent: speckit.tasks
    prompt: Add one task per CRITICAL and HIGH finding from the analysis report, ordered by severity, each citing the finding ID.
  - label: Run a gate checklist
    agent: speckit.checklist
    prompt: Run preset:pre-merge against this feature.
  - label: Verify with evidence
    agent: speckit.verify
    prompt: Verify the feature end-to-end with evidence.
---

## User Input

```text
$ARGUMENTS
```

The input selects the **scope** and may add specific checks (the workflow
engine passes extra instructions this way — honour them in addition to the
checks below):

| Input | Scope |
|---|---|
| empty / feature slug | the current feature: `specs/NNN-<slug>/` artifacts + the code they name |
| `--artifacts-only` | spec.md ↔ plan.md ↔ tasks.md only (before implementation) |
| `--code` | artifacts **and** the implementation diff vs `origin/main` (default once tasks have `[X]`) |
| a path | restrict code checks to that path |

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_analyze` and apply standard hook-processing (skip
`enabled: false`, skip non-empty `condition`, surface optional hooks, execute
mandatory ones and wait).

Run `.specify/scripts/bash/check-prerequisites.sh --json --include-tasks`
(PowerShell: `.specify/scripts/powershell/check-prerequisites.ps1 -Json -IncludeTasks`)
and parse `FEATURE_DIR`. If `spec.md` is missing, stop and point at
`/speckit.specify`.

## Ground rules

- **Read-only.** Never edit a file. Output is the report.
- **Evidence or it did not happen.** Every finding cites `file:line` (or the
  artifact section) and, where you ran a command, the command and the relevant
  output line. "Looks fine" is not a finding and not an all-clear.
- Sources of truth, in precedence order: `.specify/memory/constitution.md` →
  `docs/adr/` (ADR-0000 first) → `CLAUDE.md` → the preset's `CONVENTIONS.md`
  (`.specify/presets/delta-global/CONVENTIONS.md`). If two of them disagree,
  report the contradiction as a finding (category `DOC_DRIFT`) — do not pick
  silently.
- Prefer the repo's own machine checks over reading: when a check below names a
  script, run it and quote the result. Only fall back to grep/reading when the
  script does not cover the case.

## Outline

### 1. Load the artifacts

From `FEATURE_DIR`: `spec.md` (header: slug, flag, Status, Verified; stories,
`AC-###`, `FR-###`, Rollback Thresholds, GDPR), `plan.md` (§1–§14, File Map,
Service Interaction Map), `tasks.md` (`T###`), and when present `research.md`,
`data-model.md`, `contracts/schema.graphql`, `verify-report.md`,
`follow-ups.md`.

Note any artifact the phase requires that is missing (plan without spec,
tasks without plan, `[X]` tasks without `verify-report.md` …) under
**Missing artifacts**.

### 2. Run the checks

Each check produces findings with an ID `<CHECK>-<n>` and a severity.

#### 2a. Requirement coverage (spec ↔ tasks)

- Every `FR-###` and every `AC-###` is referenced by at least one `T###`
  (tasks cite ACs as `(AC-012)`). Uncovered AC → **HIGH**; uncovered FR → **MEDIUM**.
- Every `T###` traces to a story (`[US#]`) or to Setup/Foundational/Polish.
  Orphan task → **LOW**.
- tasks.md is grouped by user story with *Tests first* before
  *Implementation* in each story (Constitution III). A story whose
  implementation tasks precede its tests → **HIGH**.
- Every AC is binary (EARS or Given/When/Then). Words like "should",
  "ideally", "fast", "intuitive" without a number → **MEDIUM**.
- UI criteria a human must click through are listed under *Manual
  Verification*. Missing → **MEDIUM**.

#### 2b. GraphQL surface (plan §3 ↔ SDL ↔ resolvers ↔ services)

- Every operation in plan §3 exists in `packages/graphql/schema/NN-*.graphql`
  (and in `contracts/schema.graphql`), and every new SDL field appears in the
  plan. Drift either way → **HIGH**.
- **Every field carries exactly one of `@public` / `@auth(role:)` /
  `@selfOnly`.** Run `bun run check:field-auth`. Any failure →
  **CRITICAL** (deny-by-default is invisible *and* permissive when missing).
- `@public` on a field the spec describes as user-private → **CRITICAL**
  (`@public` = any authenticated caller, ADR-0027).
- **Every admin-realm mutation carries `@audited(action:, reason:)` and
  `reason` is a top-level argument.** Run `bun run check:field-audit`. Failure
  → **CRITICAL** (F-50: the mutation can never succeed).
- Every resolver in `apps/api/src/graphql/resolvers/<area>.ts` is thin: it
  parses, authorizes, calls one `apps/api/src/services/` function, maps the
  result. Business logic or DB access in a resolver → **HIGH**.
- Services are transport-agnostic and take `db`/`redis` as parameters. Run
  `bun run check:composition-root`; failure → **HIGH**.
- SCREAMING SDL enum returned as a lowercase DTO value → **HIGH**.
- Expensive list/search fields without `@cost` → **MEDIUM**.
- Web operations for the feature live in `apps/web/src/graphql/<area>.graphql`
  and `bun --filter='@delta-global/web' codegen:check` is clean. Drift →
  **HIGH**.
- A new browser-reachable route outside `/graphql` without an ADR → **CRITICAL**.
- Any tRPC reference (`bun run check:trpc-removal`) → **CRITICAL**.

#### 2c. Data (plan §1/§4 ↔ schema ↔ DAL ↔ services)

- Every table in plan §1 exists in `packages/db/src/schema/<area>.ts`, is
  read or written by a function in `packages/db/src/<area>-dal.ts` (or
  `apps/api/src/dal/`), and that function is used by a service. Table with no
  reader → **MEDIUM**; DAL function with no caller → **LOW**.
- Reader queries project columns explicitly (pattern `articleListColumns()`);
  selecting a wide table object (`articles`: embedding + content) in a list →
  **HIGH**.
- Paginated lists order by a column **plus an `id` tiebreak**; missing → **HIGH**.
- N+1: a DAL call inside a loop or a resolver per row without a loader →
  **HIGH**.
- Admin DB functions (`admin-dal.ts`) imported from `apps/web` or the reader
  request path → **CRITICAL** (run `bash scripts/guard-admin-dal-isolation.sh`).
- Raw SQL in app code outside `packages/db` → **CRITICAL**.

#### 2d. Contracts (Zod ↔ SDL ↔ Drizzle)

- Every SDL input type has a Zod schema in `packages/shared/src/schemas/<area>.ts`
  parsed in the resolver/service boundary, with matching field names,
  optionality and limits (`.max`, enum members). Mismatch → **HIGH**.
- A TS interface duplicating a `z.infer` type → **MEDIUM**.
- Zod field vs Drizzle column type/nullability disagreement → **HIGH**.
- If a schema is read by `apps/workers`, `bun run check:py-models` is clean;
  drift → **HIGH**.
- `z.any()`, `z.unknown()` without narrowing, `z.record(z.any())` → **HIGH**.

#### 2e. Tenancy & RBAC (plan §7 ↔ enforcement)

- plan.md **declares the tenancy model** (owner-scoped — the default — or
  org-scoped; preset default `{{ var.tenancy_model }}` on
  `{{ var.tenancy_column }}`). Undeclared → **HIGH** (Constitution IV).
- Every read and write DAL function on a scoped table filters by the scope key
  taken from the session/JWT — never from input. Missing predicate or scope key
  read from GraphQL args → **CRITICAL**.
- The RBAC matrix uses the real roles only: tenant `owner | admin | member`
  and platform admin (`@auth(role: ADMIN)`). A `viewer` column or any invented
  role → **MEDIUM** (`DOC_DRIFT`).
- Every matrix row maps to an enforcement site (directive, ownership check, or
  `can<Feature>(role, action)` service) and vice versa. Unenforced row →
  **CRITICAL**; enforcement with no row → **MEDIUM**.
- Every mutation has an api integration test whose name contains `@critical`
  covering cross-owner/cross-org access (`apps/api/test/<slug>/authz.test.ts`
  or similar). Missing → **CRITICAL**.

#### 2f. Cache (plan §8 ↔ invalidation)

- Lists are cached as **ordered id arrays**, not payloads (FR-017); a payload
  cache keyed on arguments × selection → **HIGH**.
- Every cache key family in plan §8 has an invalidation site in every mutation
  that changes its contents; state the blast radius (what one write
  invalidates). Missing invalidation → **HIGH**; one write invalidating every
  user's cache → **MEDIUM** with the measured/estimated fan-out.
- Redis unreachable must degrade to the DB, not fail the request. A cache read
  without a fallback → **HIGH** (F-08).

#### 2g. Feature flag (plan §6 ↔ registry)

The key is plain kebab-case with no `ff-` prefix (`ff-` → **MEDIUM**,
`DOC_DRIFT`). It must be present in **all four** places:

1. `packages/shared/src/schemas/feature-flags.ts` — `FEATURE_FLAG_KEYS` **and**
   `FEATURE_FLAG_METADATA`;
2. `apps/workers/src/infrastructure/feature_flags.py` (if workers read it);
3. `packages/db/src/seeds/feature-flags.ts`;
4. at least one guard site: api `apps/api/src/services/<slug>-flag.ts`, RSC
   `serverFeatureFlag`/`flagAllows`, client `useFeatureFlag`.

Declared in the spec but absent from the registry → **CRITICAL** (seven flags
were once declared and never added). Also:

- Granularity other than **global** → **MEDIUM** (only global exists, ADR-0015).
- A flag gating whether the graph serves at all → **CRITICAL**.
- Flag-OFF does not restore today's behaviour exactly (materialised state
  that survives OFF) → **HIGH**.
- Flag default not OFF, or not OFF at merge → **HIGH**.

#### 2h. Migrations

- Generated by drizzle-kit (`packages/db/drizzle/`). Hand-written SQL only as
  `--custom` RLS/trigger/REVOKE/`CHECK NOT VALID` blocks, each justified in
  plan §14. Unjustified → **HIGH**.
- Run `bun run check:migration-expand-contract origin/main` and
  `bun run check:migration-immutability origin/main`. Any unexplained finding →
  **CRITICAL**; a contract statement carried by an `Allow-Contract-Migration:`
  trailer must name the release that stopped using it, else **HIGH**.
- Every new table has its RLS block (`app_full_access` policy guarded by
  `IF EXISTS pg_roles 'app'`). Missing → **HIGH**.
- Migration number collides with another branch/main → **HIGH**.

#### 2i. Background work & external calls

- Side effects that must survive a crash use Temporal (definition in
  `packages/temporal-workflows/src/`, activities in `apps/workers` or
  `apps/crawler`); a polling loop or ad-hoc queue → **HIGH**.
- Workflow IDs are deterministic (derived from the resource id). Random →
  **HIGH**.
- Changed workflow code without `patched()` or with a regenerated replay
  history → **CRITICAL**.
- Every outbound HTTP/LLM call has a timeout, retry budget and fallback; LLM
  calls via OpenRouter with a cost cap. Missing → **HIGH**.
- A new outbound host absent from CLAUDE.md *Approved External Services*, or
  without ADR + `charts/network-policies` entry → **CRITICAL**.

#### 2j. Observability & privacy

- plan §10 lists spans/logs/metrics; each appears at a call site. Planned but
  absent → **HIGH**.
- Metric labels with unbounded cardinality (user/tenant/article id, URL, raw
  query, trace/session id) → **CRITICAL**.
- Logging bodies, headers, cookies or raw emails → **CRITICAL**
  (`bun run check:log-hygiene`).
- An audit record written to stdout → **CRITICAL**.
- Analytics: any ClickHouse client import in `apps/api`/`apps/web` →
  **CRITICAL**; the plan must say "ClickHouse events: 0" when none.
- Every rollback threshold in the spec maps to an alert rule planned for
  `platform-infra/charts/grafana/alerting/<NNN>-<slug>.json` with `runbook_url`.
  Prose-only threshold → **HIGH** (`THRESHOLD_UNWIRED`).
- GDPR table: every *Personal* field has retention (ADR-0034) and a
  DSAR/erasure path task. Missing → **HIGH**.
- Raw server/DB error text reachable by a reader → **HIGH** (F-41).

#### 2k. Web

- `'use client'` on a page or layout → **HIGH**; a second `ApolloClient` →
  **CRITICAL**; Apollo hooks outside `(dashboard)` / `(admin)/admin` → **HIGH**;
  a singleton type without `keyFields` → **MEDIUM**.
- Every user-facing string goes through next-intl with keys in
  `apps/web/messages/{en,fr,es}.json` (`bun run scripts/i18n-parity.ts`,
  `bun run scripts/i18n-scan.ts`). Hardcoded string → **MEDIUM**.
- Four UI states (loading, empty, error with `retry()`, success) present →
  missing state **MEDIUM**. Raw `<img>`, `reset()` instead of `retry()` →
  **MEDIUM**.
- Admin UI reachable/rendered for a non-admin → **CRITICAL** (F-45).

#### 2l. Service Interaction Map (both directions)

- Every service the platform runs has an explicit row: web, api (GraphQL),
  Postgres, Redis, Temporal, Python workers, crawler, Stripe, OpenRouter,
  object storage, auth (BetterAuth/JWT), realtime (SSE over Redis pub/sub),
  telemetry (OTel → ClickHouse/Grafana), GlitchTip. Blank row or "not touched"
  without a reason → **HIGH**.
- Every "yes" row is reflected in plan §1–§12 and has a failure-mode test in
  §11. Missing → **HIGH**.
- In `--code` mode: every service the diff touches (imports of `db`, Redis,
  Temporal client, Stripe, OpenRouter, storage, SSE publisher) appears as a
  "yes" row. Undeclared interaction → **HIGH** (`MAP_DRIFT`).

#### 2m. Forbidden patterns (CLAUDE.md)

Grep the diff (or the files the plan names) for every row of CLAUDE.md
*Forbidden Patterns*; at minimum: `any`, `as T` without a guard, `!`
non-null, `@ts-ignore`, `enum`, `React.FC`, npm/pnpm/yarn commands,
`kubectl apply`, action pinned by tag, Server Actions, Stripe webhook payload
written as state, price/amount/URL accepted from the client, `frozen_at`
filter on `sector_subscriptions`. Each hit → **HIGH** (security-relevant ones
**CRITICAL**).

### 3. Produce the report

```markdown
# Cross-Artifact Analysis — <feature> — <date>

**Scope**: <artifacts-only | artifacts + code vs origin/main>
**Verdict**: BLOCKED (n CRITICAL) | FIX BEFORE REVIEW (n HIGH) | CLEAN
**Machine checks run**: <command → exit code, one per line>

## CRITICAL — blocks merge
### <ID> — <one-line problem>
- Where: `path:line` / artifact §
- Evidence: <quote or command output>
- Rule: <constitution principle / ADR / CLAUDE.md row>
- Fix: <concrete change>

## HIGH — fix before review
## MEDIUM — fix before merge
## LOW — track (follow-ups.md)

## DOC_DRIFT — sources of truth that disagree
| Statement A | Statement B | Which one reality matches |

## Missing artifacts
## Coverage
| AC / FR | Tasks | Test file | Status |

## Prioritized remediation
1. …
```

If nothing is found, still list every check with its evidence line — a clean
report without evidence is not clean.

### 4. Self-check before output

- Every finding has a location and evidence.
- Every severity matches the rules above.
- No finding is about a style preference Biome already enforces.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_analyze` entries and apply
standard hook-processing.
