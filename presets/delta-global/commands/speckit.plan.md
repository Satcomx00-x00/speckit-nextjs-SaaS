---
description: Delta-Global planning command. Decomposes a feature into Drizzle schema, Zod contracts, tRPC procedures (orgScopedProcedure), DAL (server-only, ioredis), pure services (Result<T,E>), RSC page (SDK createCaller), client components (@trpc/react-query), BullMQ/Temporal side effects, RBAC matrix, feature flag, cache strategy, and observability plan — all tagged with phase and criticality.
handoffs:
  - label: Generate tasks
    agent: speckit.tasks
    prompt: Generate Delta-Global implementation tasks from this plan. Sequence by dependency order.
  - label: Scaffold the route
    agent: speckit.scaffold.route
    prompt: Scaffold the RSC page and route segments for the feature in this plan.
  - label: Scaffold the DAL
    agent: speckit.scaffold.dal
    prompt: Scaffold the DAL module described in this plan.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check this plan for RFC drift, RBAC gaps, and hard constraint violations.
---

## User Input

```text
$ARGUMENTS
```

Parse the user's description to extract:
- Feature name / slug (kebab-case)
- Data shape (entities, fields, relationships) — infer from context if not stated
- Auth requirement — `none` / `required` / `required + ownership`
- RBAC roles involved — `owner / admin / member / viewer`
- Background work — `none` / `bullmq` / `temporal`
- Analytics — `none` / `clickhouse`
- Migration needed — `yes / no`

If critical fields are missing and cannot be reasonably inferred, ask one clarifying question before proceeding.

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_plan`. Apply standard hook-processing: skip `enabled: false`, skip non-empty `condition`, surface optional, auto-execute mandatory.

---

## Outline

Produce a structured plan using the template below. Omit any sub-section that is not applicable; add a one-line note explaining why.

---

```
# Plan: <Feature Name>

**Feature slug**: `<feature-name>`
**Feature flag**: `ff-<feature-name>` (default: OFF)
**Phase**: <P1 | P2 | P3 | P4>
**Auth**: <none | required | required + RBAC>
**Migration**: <yes | no>
**Background work**: <none | bullmq | temporal>
**Analytics**: <none | clickhouse>

---

## 1. Drizzle Schema

**Package**: `packages/db/src/schema/<feature-name>.ts`

| Table | Key columns | Indexes | Relations |
|---|---|---|---|
| `<feature_snake>` | `id uuid pk`, `organizationId uuid fk`, `createdAt`, `updatedAt` | `(organizationId, createdAt desc)` | `→ organizations` |

**Migration notes**:
- Forward-compatible: <yes — add-only / no — requires two-step>
- Rollback plan: <flag OFF → behavior unchanged / describe steps>
- `drizzle-kit generate` only — no handwritten SQL

---

## 2. Zod Contracts

**Package**: `packages/shared/src/schemas/<feature-name>.ts`

| Schema name | Kind | Used by |
|---|---|---|
| `Create<Feature>Input` | input | `<feature>.create` procedure |
| `Update<Feature>Input` | input | `<feature>.update` procedure |
| `Get<Feature>Input` | input | `<feature>.get` procedure |
| `List<Feature>Input` | input | `<feature>.list` procedure |
| `<Feature>Dto` | output | all queries |
| `<Feature>ListDto` | output | list query |
| `<Feature>ErrorCode` | const literal | procedures + services |

**Hard rules**: no `z.any()`, `z.unknown()`, `z.record(z.any())` — Biome fails on these.
`organizationId` is absent from all input schemas (extracted from BetterAuth session in procedures).

---

## 3. tRPC Procedures

**File**: `apps/api/src/routers/<feature-name>.ts`

| Procedure | Type | Input schema | Output schema | Min role | Flag guard |
|---|---|---|---|---|---|
| `<feature>.get` | query | `Get<Feature>Input` | `<Feature>Dto` | viewer | yes |
| `<feature>.list` | query | `List<Feature>Input` | `<Feature>ListDto` | viewer | yes |
| `<feature>.create` | mutation | `Create<Feature>Input` | `<Feature>Dto` | member | yes |
| `<feature>.update` | mutation | `Update<Feature>Input` | `<Feature>Dto` | member | yes |
| `<feature>.delete` | mutation | `Get<Feature>Input` | void | admin | yes |

**All procedures use `orgScopedProcedure`** — `organizationId` extracted from BetterAuth session, NEVER from input.

**Hono routes**: only for webhooks / mobile clients / streaming — not for internal tRPC calls.

---

## 4. DAL Functions

**File**: `apps/api/src/dal/<feature-name>.ts`

| Function | Input | Returns | Cache |
|---|---|---|---|
| `get<Feature>ById` | `id, orgId` | `Result<<Feature>DTO \| null>` | `<feature>:org:{orgId}:{id}` TTL 5m |
| `list<Feature>s` | `List<Feature>Input, orgId` | `Result<<Feature>ListDTO>` | `<feature>s:org:{orgId}` TTL 5m |
| `create<Feature>Record` | `data, orgId` | `Result<<Feature>DTO>` | invalidates `<feature>s:org:{orgId}*` |
| `update<Feature>Record` | `id, orgId, data` | `Result<<Feature>DTO>` | invalidates `<feature>:org:{orgId}:*` |
| `delete<Feature>Record` | `id, orgId` | `Result<void>` | invalidates `<feature>:org:{orgId}:*` |

**Hard rules**:
- `import 'server-only'` as first line
- `organizationId` required parameter on every function — never optional
- `eq(table.organizationId, orgId)` in every `where` clause
- Cursor-based pagination only — no `OFFSET`
- Explicit column selection — no `SELECT *`
- Sensitive fields excluded from returned rows

---

## 5. Services (Pure Logic)

**File**: `apps/api/src/services/<feature-name>.ts`

| Function | Input | Returns | Purpose |
|---|---|---|---|
| `buildCreate<Feature>Payload` | `Create<Feature>Input, { now }` | `Result<DBPayload>` | validate + transform |
| `can<Feature>` | `role, action` | `boolean` | pure RBAC lookup |
| `validate<Feature>State` | `current, next` | `Result<void>` | state machine guard |

**Hard rules**: zero imports from `db`, `auth`, `redis`, `Hono`, `tRPC`, `Next`, `headers`, `cookies`.
`now` and `rng` injected as parameters. `Result<T,E>` returned — no `throw` on business errors.

---

## 6. Feature Flag

| Property | Value |
|---|---|
| Name | `ff-<feature-name>` |
| Default | `OFF` |
| Granularity | `org` (per-organization) |
| Kill switch | < 5s (flag service hot-reload) |
| Guard locations | tRPC procedures (TRPCError FORBIDDEN) + RSC page (redirect) |
| Planned removal | <date or "after stable 100% rollout"> |

---

## 7. Cache Strategy

| Key pattern | Data | TTL | Invalidated by |
|---|---|---|---|
| `<feature>:org:{orgId}:{id}` | Single DTO | 5m | `update`, `delete` |
| `<feature>s:org:{orgId}` | List (first page only) | 5m | `create`, `update`, `delete` |

**React Query keys** (client-side, aligned with server cache):
- `[['<featureCamel>', 'get'], { input: { id }, type: 'query' }]`
- `[['<featureCamel>', 'list'], { input: { limit: 20 }, type: 'query' }]`

Invalidation call: `queryClient.invalidateQueries({ queryKey: [['<featureCamel>', 'list']] })` on mutation success.

---

## 8. Background Jobs

| Side effect | Tool | Worker/Workflow ID | Trigger |
|---|---|---|---|
| <describe side effect> | BullMQ / Temporal | `<feature>-{id}` | `<feature>.create` mutation |

**BullMQ** — fire-and-forget, at-least-once delivery.
**Temporal** — durable, resumable, time-gated; use when failure recovery or multi-step coordination is required.

Workflow IDs must be idempotent: derived from the resource ID (e.g. `<feature>-${row.id}`), not `crypto.randomUUID()`.

---

## 9. RBAC Matrix

| Action | owner | admin | member | viewer | public |
|---|---|---|---|---|---|
| read | ✓ | ✓ | ✓ | ✓ | — |
| create | ✓ | ✓ | ✓ | — | — |
| update | ✓ | ✓ | ✓ | — | — |
| delete | ✓ | ✓ | — | — | — |

Role extracted from `ctx.member.role` (BetterAuth session) — never from procedure input.
Evaluated by the `can<Feature>` service function — not inline in the procedure.

---

## 10. RSC / Client Boundary

**Server boundary**: `apps/web/app/(app)/[workspace]/<feature-name>/page.tsx` — all RSC
**Client islands**:
- `Create<Feature>Form` — user interaction, form state, tRPC mutation
- `<Feature>List` — React Query `useQuery` with `initialData` hydration

**Discipline**:
- `'use client'` only at interactive leaves — never on page or layout
- RSC fetches via `createCaller` — not `fetch()`, not React Query
- Client receives typed `initialData` from RSC — no re-fetch on mount

---

## 11. UI States (Mandatory Four)

| State | File | Implementation |
|---|---|---|
| Loading | `loading.tsx` + `<Feature>ListSkeleton` | Skeleton matching final layout, `aria-busy` |
| Empty | `<Feature>List` empty branch | Illustration + copy + primary CTA |
| Error | `error.tsx` | GlitchTip capture + "Réessayer" button |
| Success | `<Feature>List` populated branch | Data rendered, toast on mutation |

---

## 12. Accessibility Checkpoints

- [ ] `<label>` linked to every input — no placeholder-only labels
- [ ] `aria-invalid` + `aria-describedby` on form errors
- [ ] `:focus-visible` preserved — no `outline: none` without replacement
- [ ] Keyboard navigation: Enter / Escape / Tab for all interactive flows
- [ ] AA contrast (Tailwind 4 tokens — check custom colors)
- [ ] `aria-live` region for async state updates
- [ ] `alt` on images; `aria-hidden` on decorative icons
- [ ] 44×44px minimum touch targets on mobile

---

## 13. Observability Plan

| Signal | What | Where |
|---|---|---|
| OTel span | `org.id`, `user.id`, `procedure.name` | tRPC middleware |
| Structured log | `organizationId`, `userId`, `correlationId`, `durationMs` | procedure boundary |
| Analytics event | `<feature>.created` / `<feature>.updated` etc. | ClickHouse — **not Postgres** |
| Error capture | GlitchTip `captureException` | `error.tsx` + procedure catch |
| Alert | error_rate > 1% / 15m, p95 > threshold / 15m | Grafana Alerting |

---

## 14. Security Checklist

- [ ] `organizationId` extracted from BetterAuth session — never from input
- [ ] `eq(table.organizationId, orgId)` in every DAL query
- [ ] Role checked via `can<Feature>(ctx.member.role, action)` in every mutation
- [ ] ioredis rate limit: `rl:<procedure.name>:{userId}` before writes
- [ ] No raw SQL anywhere (drizzle-kit only)
- [ ] No `@delta-global/analytics-db` imports in `apps/api` or `apps/web`
- [ ] Secrets via `env.ts` + Infisical — never `process.env` directly
- [ ] No sensitive fields in DTO schemas or cache values

---

## 15. Testing Plan

| Test type | File | Tool | Scope |
|---|---|---|---|
| Unit | `apps/api/test/<feature-name>/services.test.ts` | `bun:test` | Pure service functions, 100% branch |
| Integration (DAL) | `apps/api/test/<feature-name>/dal.test.ts` | `bun:test` + Testcontainers | Cross-org isolation, session guards |
| Integration (procedures) | `apps/api/test/<feature-name>/procedures.test.ts` | `bun:test` + Testcontainers | RBAC, rate limit, idempotency |
| E2E (happy path) | `apps/web/tests/e2e/<feature-name>/happy.spec.ts` | Playwright | Login → create → assert visible |
| E2E (@critical) | `apps/web/tests/e2e/<feature-name>/isolation.spec.ts` | Playwright | 4 tenant-isolation assertions |

---

## 16. Open Questions

List any decisions to make before implementation starts:

1. <Question — e.g. soft-delete vs hard-delete?>
2. <Question — e.g. quota limit per org?>
3. *(Delete this section if there are none.)*

---

## 17. Marginal Cost Estimate

| Resource | Per operation | At 10k ops/day |
|---|---|---|
| Postgres rows | +1 per create | ~10k rows/day |
| Redis keys | +2 per create (one + list) | negligible |
| BullMQ jobs | +1 per create | ~10k jobs/day |
| ClickHouse events | +1 per action | ~30–50k events/day |

Rollback threshold: revert flag if error rate > <N>% over 15m OR p95 > <Nms>.

```

---

## Post-Plan Checks

After producing the plan:

1. Verify every procedure in §3 has an entry in the RBAC matrix in §9.
2. Verify every cache key in §7 has a corresponding invalidation site listed.
3. Verify every analytics event in §13 routes to ClickHouse — never Postgres.
4. Verify the feature flag in §6 is listed with a kill-switch < 5s.
5. If any hard constraint is violated (raw SQL, analytics-db import, orgId from input), flag it as CRITICAL before outputting the plan.

After completing these checks, offer:

```
## Next Steps

Run `/speckit.tasks <feature-name>` to generate ordered implementation tasks, or
run `/speckit.scaffold.route <feature-name>` to scaffold the route structure now.
```

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_plan` entries and apply standard hook-processing.
