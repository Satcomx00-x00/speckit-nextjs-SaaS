---
description: "Task list template for Delta-Global feature implementation"
---

# Tasks: [FEATURE NAME]

**Feature slug**: `[feature-name]`
**Feature flag**: `ff-[feature-name]` (must be OFF at merge)
**Plan ref**: `[link to plan.md]`
**Spec ref**: `[link to spec.md]`
**Phase**: [P1 | P2 | P3 | P4]

**Prerequisites**: plan.md (required), spec.md (required for acceptance criteria)

**Note**: Tasks below are SAMPLE TASKS. The `speckit.tasks` command replaces them with
actual tasks derived from the plan and spec. Do not keep sample tasks in the generated file.

**Organization**: Tasks are grouped by layer in dependency order, not by user story.
The `@critical` tenant-isolation E2E tests MUST pass before the PR is opened.

---

## Format: `[ID] [P?] Description`

- **[P]**: Can run in parallel with other [P]-marked tasks (different files, no dependencies)
- Include exact file paths in every task description
- Acceptance criteria are binary (yes/no) — no "should" or "ideally"

---

## Path Conventions (Delta-Global monorepo)

| Layer | Path |
|---|---|
| Zod contracts | `packages/shared/src/schemas/[feature-name].ts` |
| Drizzle schema | `packages/db/src/schema/[feature-name].ts` |
| Migration | `packages/db/drizzle/` (via `drizzle-kit generate`) |
| DAL | `apps/api/src/dal/[feature-name].ts` |
| Services | `apps/api/src/services/[feature-name].ts` |
| tRPC router | `apps/api/src/routers/[feature-name].ts` |
| BullMQ worker | `apps/api/src/workers/[feature-name].worker.ts` |
| Temporal workflow | `packages/temporal-workflows/src/workflows/[feature-name].ts` |
| RSC page | `apps/web/app/(app)/[workspace]/[feature-name]/page.tsx` |
| Client components | `apps/web/components/features/[feature-name]/` |
| DAL tests | `apps/api/test/[feature-name]/dal.test.ts` |
| Services tests | `apps/api/test/[feature-name]/services.test.ts` |
| Procedures tests | `apps/api/test/[feature-name]/procedures.test.ts` |
| E2E | `apps/web/tests/e2e/[feature-name]/` |

---

<!--
  ============================================================================
  IMPORTANT: The tasks below are SAMPLE TASKS for illustration only.
  The speckit.tasks command MUST replace these with actual tasks derived from:
  - The feature plan (plan.md)
  - The feature spec (spec.md)
  DO NOT keep these sample tasks in the generated tasks.md file.
  ============================================================================
-->

## Phase 1 — Foundation (unblocks everything)

### TASK-001 — [P] Declare feature flag `ff-[feature-name]`
*File*: flag service config
- [ ] Register `ff-[feature-name]` with `default: false`, org granularity, kill-switch < 5s
- [ ] Flag evaluates to `false` on a clean environment

### TASK-002 — [P] Implement Zod schemas in `packages/shared/src/schemas/[feature-name].ts`
- [ ] Input schemas: `Create[Feature]Input`, `Update[Feature]Input`, `Get[Feature]Input`, `List[Feature]Input`
- [ ] Output schemas: `[Feature]Dto`, `[Feature]ListDto`
- [ ] `[Feature]ErrorCode` as `const` literal
- [ ] No `z.any()`, `z.unknown()`, `z.record(z.any())`
- [ ] `organizationId` absent from all input schemas
- [ ] Export from barrel; `bun run typecheck` passes

### TASK-003 — Implement Drizzle schema `packages/db/src/schema/[feature-name].ts`
*Depends on*: TASK-002
- [ ] `uuid().primaryKey().defaultRandom()` on `id`
- [ ] `organizationId` FK → `organizations.id`
- [ ] Timestamps with `withTimezone: true`
- [ ] Index on `(organizationId, createdAt desc)`
- [ ] `InferSelectModel` / `InferInsertModel` types exported

### TASK-004 — Generate and review migration
*Depends on*: TASK-003
- [ ] `bun --filter @delta-global/db drizzle-kit generate` produces clean SQL
- [ ] Migration reviewed line-by-line (no NOT NULL without default, no DROP without plan)
- [ ] `bun --filter @delta-global/db drizzle-kit migrate` applies cleanly locally

### TASK-005 — [P] Add seed data in `scripts/seed.ts`
*Depends on*: TASK-004
- [ ] At least 2 organizations with non-overlapping data
- [ ] Idempotent (safe to run multiple times)
- [ ] Realistic data — no "test1", "foo"

---

## Phase 2 — Backend

### TASK-006 — Implement DAL `apps/api/src/dal/[feature-name].ts`
*Depends on*: TASK-003
- [ ] `import 'server-only'` as first non-comment line
- [ ] `get[Feature]ById`, `list[Feature]s`, `create[Feature]Record`, `update[Feature]Record`, `delete[Feature]Record`
- [ ] Every read: `getSession()` → `assertMembership()` → `eq(table.organizationId, orgId)` in every `where`
- [ ] `organizationId` required parameter on every write — never optional
- [ ] ioredis cache: key `[feature]:org:{orgId}:{id}`, TTL 5m
- [ ] Explicit column selection — no `SELECT *`
- [ ] Sensitive fields excluded from DTO mapper return

### TASK-007 — [P] DAL tests `apps/api/test/[feature-name]/dal.test.ts`
*Depends on*: TASK-006
- [ ] Testcontainers ephemeral Postgres — no shared test DB
- [ ] Cross-org isolation: org A cannot read org B data
- [ ] No session → `UNAUTHORIZED`
- [ ] No membership → `FORBIDDEN`
- [ ] Cursor pagination works (page 1, advance cursor, last page)
- [ ] `bun test apps/api/test/[feature-name]/dal.test.ts` passes

### TASK-008 — [P] Implement services `apps/api/src/services/[feature-name].ts`
*Depends on*: TASK-002
- [ ] Zero imports from `db`, `auth`, `redis`, `Hono`, `tRPC`, `Next`, `headers`, `cookies`
- [ ] `buildCreate[Feature]Payload(input, { now })` → `Result<DBPayload>`
- [ ] `can[Feature](role, action)` → `boolean` pure RBAC lookup
- [ ] `Result<T,E>` — no `throw` on business errors
- [ ] Nesting depth < 2

### TASK-009 — [P] Services tests `apps/api/test/[feature-name]/services.test.ts`
*Depends on*: TASK-008
- [ ] 100% branch coverage
- [ ] Every `[Feature]ErrorCode` value asserted in at least one test
- [ ] Edge cases: empty string, max-length, 0, -1, Unicode, emoji
- [ ] Total runtime < 100ms
- [ ] No mocks

### TASK-010 — Implement tRPC router `apps/api/src/routers/[feature-name].ts`
*Depends on*: TASK-006, TASK-008
- [ ] `orgScopedProcedure` on every procedure
- [ ] `.input()` + `.output()` schemas from `@delta-global/shared` — never inlined
- [ ] `.meta({ name: '[feature].[action]' })` for OTel
- [ ] Feature flag check (`flagService.isEnabled`) in every procedure
- [ ] RBAC check (`can[Feature](ctx.member.role, action)`) in every mutation
- [ ] Rate limit (`rl:[feature].[action]:{userId}`) via ioredis on writes
- [ ] Wired into `appRouter`

### TASK-011 — [P] Procedures tests `apps/api/test/[feature-name]/procedures.test.ts`
*Depends on*: TASK-010
- [ ] Testcontainers (Postgres + Redis)
- [ ] No session → `UNAUTHORIZED`; no membership → `FORBIDDEN`; wrong role → `FORBIDDEN`
- [ ] Invalid input → ZodError formatted to fields
- [ ] Idempotency: 2× same create → no duplicate row
- [ ] Rate limit: N+1 call → `TOO_MANY_REQUESTS`
- [ ] Cache invalidation: correct Redis key absent after mutation
- [ ] `bun test apps/api/test/[feature-name]/procedures.test.ts` passes

### TASK-012 — BullMQ worker OR Temporal workflow (if background work)
*Depends on*: TASK-010
- [ ] Idempotent job/workflow processing
- [ ] Failure captured to GlitchTip
- [ ] Worker/workflow tests pass

---

## Phase 3 — Frontend

### TASK-013 — Scaffold RSC page and route segments
*Depends on*: TASK-010
- [ ] `apps/web/app/(app)/[workspace]/[feature-name]/page.tsx` — async RSC, `generateMetadata`, flag guard, `createCaller`
- [ ] `loading.tsx` — skeleton, no `'use client'`
- [ ] `error.tsx` — `'use client'`, GlitchTip capture, "Réessayer" button
- [ ] `await params` before any use (Next.js 15)
- [ ] No `fetch('/api/...')` — only `createCaller`
- [ ] `bun run typecheck` passes

### TASK-014 — Implement client components
*Depends on*: TASK-013
- [ ] `Create[Feature]Form` — `react-hook-form` + `zodResolver` + `useMutation` + Sonner toast
- [ ] `[Feature]List` — `useQuery` with `initialData`, empty state with CTA
- [ ] `[Feature]ListSkeleton` — `aria-busy`, skeleton matches layout dimensions
- [ ] `queryClient.invalidateQueries` on mutation success
- [ ] Submit disabled while `mutation.isPending`
- [ ] Field-level server errors via `setError`
- [ ] All strings via `next-intl`
- [ ] 44×44px touch targets on mobile
- [ ] `bun run typecheck` passes

### TASK-015 — [P] UI component tests
*Depends on*: TASK-014
- [ ] `Create[Feature]Form` renders; submit disabled on pending
- [ ] `[Feature]List` shows empty state when `items` is empty
- [ ] `[Feature]List` renders items when data is present

---

## Phase 4 — E2E + Quality Gates

### TASK-016 — [P] E2E happy path `apps/web/tests/e2e/[feature-name]/happy.spec.ts`
*Depends on*: TASK-013, TASK-014
- [ ] Pre-authenticated storage state — no re-login per test
- [ ] Login → navigate → create → assert item visible
- [ ] Validation error path: submit invalid form → field error visible
- [ ] No `waitForTimeout` — selector-based waits only
- [ ] `bun run test:e2e --grep [feature-name]` passes

### TASK-017 — ⚠️ @critical E2E tenant isolation `apps/web/tests/e2e/[feature-name]/isolation.spec.ts`
*Depends on*: TASK-013
**MUST PASS BEFORE PR IS OPENED**
- [ ] User A on page of org A → data visible
- [ ] User A on URL of org B → 404
- [ ] User A calls procedure with org B `organizationId` → 403
- [ ] User A on URL with resource ID from org B → 404
- [ ] Tests tagged `@critical`
- [ ] `bun run test:e2e --grep @critical --grep [feature-name]` exits 0

### TASK-018 — Quality gates (all must exit 0)
*Depends on*: all above
- [ ] `bun run lint` (Biome) — no `z.any`, no `analytics-db` imports
- [ ] `bun run typecheck`
- [ ] `bun run knip`
- [ ] `turbo run build --filter=...[HEAD^1]`
- [ ] `gitleaks detect --no-banner`
- [ ] `bun pm audit --severity high`

---

## Phase Gate Summary

| ID | Title | Phase | Criticality | Status |
|---|---|---|---|---|
| TASK-001 | Feature flag declaration | P1 | Critical | ☐ |
| TASK-002 | Zod schemas | P1 | Critical | ☐ |
| TASK-003 | Drizzle schema | P1 | Critical | ☐ |
| TASK-004 | Migration | P1 | Critical | ☐ |
| TASK-006 | DAL | P1 | Critical | ☐ |
| TASK-008 | Services | P1 | High | ☐ |
| TASK-010 | tRPC procedures | P1 | Critical | ☐ |
| TASK-013 | RSC page + route | P1 | High | ☐ |
| TASK-014 | Client components | P1 | High | ☐ |
| TASK-017 | @critical isolation | P1 | **Critical — blocks merge** | ☐ |
| TASK-018 | Quality gates | P1 | Critical | ☐ |
| TASK-007 | DAL tests | P2 | High | ☐ |
| TASK-009 | Services tests | P2 | High | ☐ |
| TASK-011 | Procedures tests | P2 | High | ☐ |
| TASK-016 | E2E happy path | P2 | High | ☐ |

---

## Parallel Execution Opportunities

Tasks marked [P] can run simultaneously (they touch different files):

```
Group A (can all run in parallel after TASK-002/003):
  TASK-007 (DAL tests)
  TASK-008 (Services)
  TASK-011 (Procedures tests) — after TASK-010
  TASK-015 (UI tests) — after TASK-014
  TASK-016 (E2E happy path) — after TASK-013/014

Group B (strictly sequential):
  TASK-002 → TASK-003 → TASK-004 → TASK-006 → TASK-010 → TASK-013 → TASK-017
```

---

## Notes

- `[P]` = different files, no dependencies — safe to parallelize
- Each task is independently committable
- TASK-017 (`@critical`) gates the PR — no exceptions
- Do not open the PR until TASK-018 (all quality gates) passes
