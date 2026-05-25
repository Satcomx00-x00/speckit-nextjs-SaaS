---
description: Delta-Global task generation. Converts a feature plan into a dependency-ordered, constitution-compliant task list with Delta-Global-shaped titles, acceptance criteria referencing stack constraints, and explicit phase tags. Covers Zod contracts → Drizzle schema → DAL → services → tRPC procedures → RSC page → client components → BullMQ/Temporal → bun:test + Playwright.
handoffs:
  - label: Open plan
    agent: speckit.plan
    prompt: Produce a Delta-Global feature plan so tasks can be generated from it.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check the generated tasks against the RFC for drift or missing coverage.
---

## User Input

```text
$ARGUMENTS
```

- If a plan path is supplied (e.g. `.specify/plans/<feature-name>.md`), read it and derive tasks from it.
- If the argument is a freeform feature description, derive tasks directly from the description.
- If empty, look for the most recent plan under `.specify/plans/` and generate tasks from it.

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. Look for hooks under `hooks.before_tasks`. Apply standard hook-processing.

---

## Outline

### 1. Parse the plan

Extract from the plan document (or derive from the description):

- Feature slug (kebab-case)
- Feature flag name: `ff-<feature-slug>`
- Drizzle tables + columns
- Zod schemas (input + output)
- tRPC procedures (name, type, input/output, min role)
- DAL functions
- Service functions
- Background jobs (BullMQ queue name or Temporal workflow name)
- RSC page path
- Client components
- E2E test paths
- Phase target (P1–P4)
- Auth requirement
- Migration needed (yes/no)

### 2. Produce the task list

Generate tasks using the template below. Follow this **dependency order** — tasks must appear in this sequence:

1. Feature flag declaration
2. Zod contracts (`packages/shared`)
3. Drizzle schema + migration (if needed)
4. Seed data (if migration)
5. DAL module (`apps/api/src/dal/`)
6. DAL tests
7. Services module (`apps/api/src/services/`)
8. Services tests
9. tRPC procedures (`apps/api/src/routers/`)
10. Procedures tests
11. BullMQ worker or Temporal workflow (if background work)
12. RSC page + route segments (`apps/web/app/`)
13. Client components (`apps/web/components/features/`)
14. UI component tests
15. E2E happy path tests
16. E2E `@critical` tenant-isolation tests
17. Quality gates check

Within each group, order by dependency (e.g. `get` before `create`).

---

```
# Tasks: <Feature Name>

**Plan ref**: <path or "inline">
**Feature flag**: `ff-<feature-slug>` (must be OFF at merge)
**Phase**: <P1 | P2 | P3 | P4>
**Total tasks**: <N>

---

## Foundation — Feature Flag

### TASK-001 — Declare feature flag `ff-<feature-slug>`
*File*: flag service config
*Phase/Crit*: P1 / Critical · Scope: Both

**What**:
- Register `ff-<feature-slug>` with `default: false`
- Granularity: org-level
- Kill switch < 5s (flag service hot-reload)
- Add planned removal date

**Acceptance criteria**:
- [ ] Flag evaluates to `false` for all orgs before explicit enablement
- [ ] `flagService.isEnabled('ff-<feature-slug>', orgId)` returns `false` on a clean env
- [ ] Flag entry committed to the flag service config

---

## Foundation — Zod Contracts

### TASK-002 — Implement Zod schemas in `packages/shared`
*File*: `packages/shared/src/schemas/<feature-slug>.ts`
*Phase/Crit*: P1 / Critical · Scope: Both

**What**:
- `<Feature>ErrorCode` as `const` literal object
- One input schema per procedure: `Create<Feature>Input`, `Update<Feature>Input`, `Get<Feature>Input`, `List<Feature>Input`
- Output DTO schemas: `<Feature>Dto`, `<Feature>ListDto`
- Precise constraints: `.min`, `.max`, `.uuid()`, `.email()`, `.regex()` on every field
- No `z.any()`, `z.unknown()`, `z.record(z.any())` — Biome will fail
- `organizationId` absent from all input schemas
- Export types and schemas from the package barrel

**Acceptance criteria**:
- [ ] `bun run typecheck` passes with no errors
- [ ] No `z.any` / `z.unknown` / `z.record(z.any)` in the file
- [ ] Every input schema has at least one constraint per field
- [ ] DTO schemas omit sensitive fields (tokens, hashes, secrets)

---

## Foundation — Database (if migration needed)

### TASK-003 — Implement Drizzle schema and generate migration
*Files*: `packages/db/src/schema/<feature-slug>.ts`, migration file
*Phase/Crit*: P1 / Critical · Scope: BE

**What**:
- `uuid().primaryKey().defaultRandom()` on `id`
- `organizationId` FK → `organizations.id`, `onDelete` decision documented
- `createdAt` / `updatedAt` with `timestamp({ withTimezone: true }).notNull().defaultNow()`
- Index on `(organizationId, createdAt desc)` minimum
- Additional composite indexes for frequent filter+sort patterns
- `relations()` declared if joins are needed
- Export `InferSelectModel` and `InferInsertModel` types
- Add to `packages/db/src/schema/index.ts` barrel
- Run `bun --filter @delta-global/db drizzle-kit generate`

**Acceptance criteria**:
- [ ] Every tenant-scoped table has `organizationId` column + index
- [ ] Generated SQL contains no `NOT NULL` on existing table without a default
- [ ] `drizzle-kit generate` produces clean output (no warnings)
- [ ] Migration reviewed line-by-line before applying

### TASK-004 — Add seed data for tenant-isolation tests
*File*: `scripts/seed.ts`
*Phase/Crit*: P1 / High · Scope: BE

**What**:
- Create at least 2 organizations with realistic data each
- Idempotent (safe to run multiple times)
- Include Unicode and max-length edge cases
- No placeholder strings like "test1", "foo"

**Acceptance criteria**:
- [ ] `bun run db:seed` executes without error
- [ ] Re-running seed produces no duplicate key errors
- [ ] At least 2 orgs with non-overlapping data exist after seeding

---

## DAL

### TASK-005 — Implement DAL `apps/api/src/dal/<feature-slug>.ts`
*File*: `apps/api/src/dal/<feature-slug>.ts`
*Phase/Crit*: P1 / Critical · Scope: BE

**What**:
- `import 'server-only'` as the first non-comment line
- `get<Feature>ById` — reads by id, org-scoped, Redis-cached + React `cache()`
- `list<Feature>s` — cursor-based pagination, org-scoped, Redis-cached (first page)
- `create<Feature>Record(data, organizationId)` — inserts + invalidates cache
- `update<Feature>Record(id, orgId, data)` — updates + invalidates cache
- `delete<Feature>Record(id, orgId)` — deletes + invalidates cache
- Every read: `getSession()` → `assertMembership()` → DB query with `eq(table.organizationId, orgId)`
- Cache key pattern: `<feature>:org:{orgId}:{id}` and `<feature>s:org:{orgId}`
- Explicit column selection — no `SELECT *`
- Sensitive fields excluded from returned rows
- `Result<T,E>` return type on every function

**Acceptance criteria**:
- [ ] `import 'server-only'` is the first non-comment line
- [ ] Every query includes `eq(<featureSnake>.organizationId, orgId)` in `where`
- [ ] `organizationId` is a required non-optional parameter on all write functions
- [ ] Cache TTL set, invalidation calls present in all mutation functions
- [ ] `bun run typecheck` passes

### TASK-006 — DAL tests (bun:test + Testcontainers)
*File*: `apps/api/test/<feature-slug>/dal.test.ts`
*Phase/Crit*: P2 / High · Scope: BE

**What**:
- Ephemeral Postgres via Testcontainers — no shared test DB
- Happy path: `get`, `list`, `create`, `update`, `delete`
- **Cross-org isolation**: user of org A querying org B data → `null` / error
- No session → `UNAUTHORIZED`
- No membership → `FORBIDDEN`
- Suspended org → correct behavior per business rule
- Pagination: page 1, cursor advance, last page (empty `nextCursor`)
- Cache hit: 2 identical calls → 1 DB query (Redis intercepts second)

**Acceptance criteria**:
- [ ] Cross-org isolation test passes — org A cannot read org B data
- [ ] No session test throws or returns `UNAUTHORIZED`
- [ ] All tests pass with `bun test apps/api/test/<feature-slug>/dal.test.ts`
- [ ] No real Postgres connection used (Testcontainer only)

---

## Services

### TASK-007 — Implement pure services `apps/api/src/services/<feature-slug>.ts`
*File*: `apps/api/src/services/<feature-slug>.ts`
*Phase/Crit*: P1 / High · Scope: BE

**What**:
- Zero imports from `db`, `auth`, `redis`, `Hono`, `tRPC`, `Next`, `headers`, `cookies`
- `buildCreate<Feature>Payload(input, { now })` → `Result<DBPayload>`
- `can<Feature>(role, action)` → `boolean` (pure RBAC lookup table)
- Additional domain-specific validators / state machine checks
- `Result<T,E>` return type — no `throw` on business errors
- `now` and `rng` injected as parameters — no `Date.now()` / `Math.random()` directly
- Guard clauses at top, happy path at bottom
- Nesting depth < 2

**Acceptance criteria**:
- [ ] No imports from infrastructure packages
- [ ] Every function returns `Result<T,E>` — no raw `throw`
- [ ] `bun run typecheck` passes

### TASK-008 — Services tests
*File*: `apps/api/test/<feature-slug>/services.test.ts`
*Phase/Crit*: P2 / High · Scope: BE

**What**:
- 100% branch coverage
- Every `<Feature>ErrorCode` value is asserted in at least one test
- Edge cases: empty string, max-length string, 0, -1, Unicode, emoji
- No mocks needed (pure functions)
- Total runtime < 100ms

**Acceptance criteria**:
- [ ] All branches covered
- [ ] All error codes tested
- [ ] `bun test apps/api/test/<feature-slug>/services.test.ts` < 100ms
- [ ] No mocks or external dependencies

---

## tRPC Procedures

### TASK-009 — Implement tRPC router `apps/api/src/routers/<feature-slug>.ts`
*File*: `apps/api/src/routers/<feature-slug>.ts`
*Phase/Crit*: P1 / Critical · Scope: BE

**What**:
- Wire `<featureCamel>Router` into `appRouter` in `apps/api/src/routers/index.ts`
- `orgScopedProcedure` on every procedure — `organizationId` from session, NEVER from input
- `.input(schema)` imported from `@delta-global/shared` — never inlined
- `.output(schema)` for typed SDK contracts
- `.meta({ name: '<feature>.<action>' })` for OTel spans + structured logs
- Feature flag check: `flagService.isEnabled('ff-<feature-slug>', ctx.organizationId)` → `FORBIDDEN`
- Role check: `can<Feature>(ctx.member.role, action)` → `FORBIDDEN`
- Rate limit: `rl:<procedure>:{userId}` via ioredis before writes
- `db.transaction()` for multi-table mutations
- Cache invalidation via `invalidate<Feature>Cache` in DAL
- `TRPCError` with generic client message; full stack to GlitchTip + Loki

**Acceptance criteria**:
- [ ] `orgScopedProcedure` used on every procedure
- [ ] Feature flag guard present in every procedure
- [ ] RBAC check present in every mutation
- [ ] Rate limit present on `create`, `update`, `delete`
- [ ] `bun run typecheck` passes

### TASK-010 — Procedures integration tests
*File*: `apps/api/test/<feature-slug>/procedures.test.ts`
*Phase/Crit*: P2 / High · Scope: BE

**What**:
- Testcontainers (Postgres + Redis + Temporal if needed)
- Happy path per procedure
- No session → `UNAUTHORIZED`
- No membership → `FORBIDDEN`
- Insufficient role → `FORBIDDEN`
- Invalid input → ZodError formatted to field errors
- Idempotency: 2× same `create` call → no duplicate row
- Quota exceeded → typed `<Feature>ErrorCode` error
- Cache invalidation: correct Redis key deleted after mutation
- Rate limit: N+1 call → `TOO_MANY_REQUESTS`

**Acceptance criteria**:
- [ ] All role permutations tested
- [ ] Idempotency test passes
- [ ] Cache invalidation verified (assert key absent after mutation)
- [ ] `bun test apps/api/test/<feature-slug>/procedures.test.ts` passes

---

## Background Work (if applicable)

### TASK-011 — Implement BullMQ worker (or Temporal workflow)
*File*: `apps/api/src/workers/<feature-slug>.worker.ts` OR `packages/temporal-workflows/src/`
*Phase/Crit*: P2 / High · Scope: BE

**What** (BullMQ):
- `<featureCamel>Queue` exported for use in procedures
- Worker handles `<feature>-created`, `<feature>-updated` job names
- Idempotent job processing
- `removeOnComplete` and `removeOnFail` configured
- Error captured to GlitchTip on `worker.on('failed')`

**What** (Temporal — use `/speckit.scaffold.temporal <feature-slug>` instead):
- Workflow ID: `<feature>-{resourceId}` — idempotent
- Activities isolate all external effects
- Retry policy + timeouts defined
- `TestWorkflowEnvironment` tests with time skipping

**Acceptance criteria**:
- [ ] Worker/workflow is idempotent
- [ ] Failure captured and alerted
- [ ] `bun test` passes for worker/workflow

---

## UI

### TASK-012 — Scaffold RSC page and route segments
*Files*: `apps/web/app/(app)/[workspace]/<feature-slug>/`
*Phase/Crit*: P1 / High · Scope: FE

**What**:
- `page.tsx` — async RSC, `generateMetadata`, feature-flag guard, SDK `createCaller`
- `loading.tsx` — skeleton matching final layout
- `error.tsx` — GlitchTip capture + "Réessayer" button
- Feature flag redirects to `/${workspace}` if OFF

**Acceptance criteria**:
- [ ] No `'use client'` in `page.tsx`
- [ ] `await params` before any use of params (Next.js 15)
- [ ] Feature flag guard present
- [ ] `createCaller` used — no `fetch('/api/...')`
- [ ] `bun run typecheck` passes

### TASK-013 — Implement client components
*Files*: `apps/web/components/features/<feature-slug>/`
*Phase/Crit*: P1 / High · Scope: FE

**What**:
- `Create<Feature>Form` — `react-hook-form` + `zodResolver` + `useMutation` + Sonner toast
- `<Feature>List` — `useQuery` with `initialData` hydration from RSC
- `<Feature>ListSkeleton` — skeleton matching layout, `aria-busy`
- Server errors mapped to fields via `setError`
- Submit disabled while `mutation.isPending`
- `queryClient.invalidateQueries` on mutation success (aligned with server cache keys)
- All strings via `next-intl` — no hardcoded FR/EN
- 44×44px touch targets, `aria-invalid`, `aria-describedby` on errors

**Acceptance criteria**:
- [ ] No double-submit possible (button disabled while pending)
- [ ] Field-level errors from server displayed
- [ ] Empty state renders illustration + CTA
- [ ] Skeleton dimensions approximate final layout
- [ ] `bun run typecheck` passes

### TASK-014 — UI component tests
*File*: `apps/web/components/features/<feature-slug>/`
*Phase/Crit*: P2 / Medium · Scope: FE

**What**:
- Render `Create<Feature>Form` — verify submit button disabled on pending
- Render `<Feature>List` with empty data — verify empty state shown
- Render `<Feature>List` with data — verify items rendered

---

## E2E Tests

### TASK-015 — E2E happy path
*File*: `apps/web/tests/e2e/<feature-slug>/happy.spec.ts`
*Phase/Crit*: P2 / High · Scope: FE

**What**:
- Pre-authenticated storage state per role (owner, admin, member, viewer) — no re-login
- Login → navigate → create → assert item visible
- Validation error path — submit invalid form → assert field error visible
- No `waitForTimeout` — use selectors

**Acceptance criteria**:
- [ ] Happy path test passes
- [ ] Form validation error test passes
- [ ] `bun run test:e2e --grep <feature-slug>` exits 0

### TASK-016 — E2E @critical tenant isolation
*File*: `apps/web/tests/e2e/<feature-slug>/isolation.spec.ts`
*Phase/Crit*: P1 / Critical · Scope: Both

**What** (all four assertions are required — this test MUST pass to merge):
1. User A on page of org A → data visible
2. User A on URL of org B → 404
3. User A calls procedure with `orgId` of org B → 403
4. User A on URL with resource ID from org B → 404

**Acceptance criteria**:
- [ ] All 4 assertions pass
- [ ] Tests are tagged `@critical`
- [ ] `bun run test:e2e --grep @critical --grep <feature-slug>` exits 0
- [ ] **This test MUST pass before the PR is opened**

---

## Quality Gates

### TASK-017 — Run quality gates
*Phase/Crit*: P1 / Critical · Scope: Both

**What** (all must exit 0 before opening PR):
- `bun run lint` (Biome)
- `bun run typecheck` (tsc --noEmit)
- `bun run knip` (dead exports)
- `turbo run build --filter=...[HEAD^1]`
- `gitleaks detect --no-banner`
- `bun pm audit --severity high`

**Acceptance criteria**:
- [ ] All 6 quality gates exit 0
- [ ] No `z.any` / `z.unknown` / `z.record(z.any)` in Zod schemas (Biome)
- [ ] No `@delta-global/analytics-db` imports in `apps/api` or `apps/web`
- [ ] No raw SQL template literals outside migration files

---

## Phase Gate Summary

Tasks required before opening the PR:

| ID | Title | Phase | Criticality | Status |
|---|---|---|---|---|
| TASK-001 | Feature flag declaration | P1 | Critical | ☐ |
| TASK-002 | Zod contracts | P1 | Critical | ☐ |
| TASK-003 | Drizzle schema + migration | P1 | Critical | ☐ |
| TASK-005 | DAL implementation | P1 | Critical | ☐ |
| TASK-007 | Services | P1 | High | ☐ |
| TASK-009 | tRPC procedures | P1 | Critical | ☐ |
| TASK-012 | RSC page + route | P1 | High | ☐ |
| TASK-013 | Client components | P1 | High | ☐ |
| TASK-016 | @critical isolation tests | P1 | Critical | ☐ |
| TASK-017 | Quality gates | P1 | Critical | ☐ |
| TASK-006 | DAL tests | P2 | High | ☐ |
| TASK-008 | Services tests | P2 | High | ☐ |
| TASK-010 | Procedures tests | P2 | High | ☐ |
| TASK-015 | E2E happy path | P2 | High | ☐ |

*Adjust task IDs and rows to match the actual tasks generated above.*

```

---

## Formatting Rules

- Task IDs are sequential (`TASK-001`, `TASK-002`, …).
- Every task has: *File*, *Phase/Crit/Scope*, **What** (bullets), **Acceptance criteria** (checklist).
- Do not invent paths — use the Delta-Global monorepo layout: `apps/api/`, `apps/web/`, `packages/db/`, `packages/shared/`, `packages/temporal-workflows/`.
- Omit task groups not relevant to the feature (e.g. skip Temporal tasks if `--skip-temporal`).
- The Phase Gate Summary table is always present.
- Flag TASK-016 (`@critical` isolation) as **blocking merge** in the summary.

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_tasks`. Apply standard hook-processing.
