# Implementation Plan: [FEATURE NAME]

**Feature slug**: `[feature-name]`
**Feature flag**: `ff-[feature-name]` (default: OFF)
**Branch**: `feat/[feature-name]`
**Date**: [DATE]
**Spec**: [link to spec.md]
**RFC PR**: [link — must be merged before implementation PR is opened]

**Note**: This template is filled in by the `speckit.plan` command.

---

## Summary

[Extract from feature spec: primary requirement + chosen technical approach in 2–3 sentences.]

---

## Stack Reference

| Layer | Technology | Package / Path |
|---|---|---|
| Runtime | Bun + Turborepo | monorepo root |
| API | Hono + tRPC v11 | `apps/api` |
| Web | Next.js 15 (App Router) | `apps/web` |
| DB schema | Drizzle ORM + Postgres | `packages/db` |
| Zod contracts | Zod v3 | `packages/shared` |
| Auth | BetterAuth | `apps/api/src/lib/auth` |
| Cache | ioredis | `apps/api/src/lib/redis` |
| Queue | BullMQ (fire-and-forget) | `apps/api/src/workers/` |
| Durable async | Temporal | `packages/temporal-workflows` |
| Observability | OpenTelemetry + Grafana + GlitchTip | platform-infra |
| Deploy | ArgoCD + Kustomize | platform-infra |
| Secrets | Infisical | env.ts + Infisical Operator |

---

## File Map

```text
packages/
├── db/src/schema/[feature-name].ts          ← Drizzle table(s)
├── shared/src/schemas/[feature-name].ts     ← Zod contracts + DTOs + error codes

apps/api/src/
├── routers/[feature-name].ts                ← tRPC procedures (orgScopedProcedure)
├── dal/[feature-name].ts                    ← server-only reads/writes, ioredis cache
├── services/[feature-name].ts               ← pure business logic, Result<T,E>
├── workers/[feature-name].worker.ts         ← BullMQ worker (if background work)
└── test/[feature-name]/
    ├── dal.test.ts
    ├── services.test.ts
    └── procedures.test.ts

packages/temporal-workflows/src/             ← (if Temporal workflow needed)
├── workflows/[feature-name].ts
└── activities/[feature-name].ts

apps/web/
├── app/(app)/[workspace]/[feature-name]/
│   ├── page.tsx                             ← RSC, SDK createCaller, flag guard
│   ├── loading.tsx                          ← Skeleton component
│   └── error.tsx                           ← GlitchTip capture, Réessayer
└── components/features/[feature-name]/
    ├── Create[Feature]Form.tsx              ← react-hook-form + useMutation
    ├── [Feature]List.tsx                    ← useQuery with initialData
    ├── [Feature]ListSkeleton.tsx            ← aria-busy skeleton
    └── index.ts                            ← barrel
    tests/e2e/[feature-name]/
    ├── happy.spec.ts
    └── isolation.spec.ts                   ← @critical tenant isolation
```

---

## 1. Drizzle Schema

**Package**: `packages/db/src/schema/[feature-name].ts`

| Table | Key columns | Indexes | Relations |
|---|---|---|---|
| `[feature_snake]` | `id uuid pk default random()`, `organizationId uuid fk`, `…`, `createdAt`, `updatedAt` | `(organizationId, createdAt desc)` | `→ organizations` |

**Migration notes**:
- Forward-compatible: [yes — add-only / no — two-step required]
- Rollback: flag OFF → behavior unchanged
- `drizzle-kit generate` only — no handwritten SQL

---

## 2. Zod Contracts

**Package**: `packages/shared/src/schemas/[feature-name].ts`

| Schema | Kind | Used by |
|---|---|---|
| `Create[Feature]Input` | input | `[feature].create` |
| `Update[Feature]Input` | input | `[feature].update` |
| `Get[Feature]Input` | input | `[feature].get` |
| `List[Feature]Input` | input | `[feature].list` |
| `[Feature]Dto` | output | all queries |
| `[Feature]ListDto` | output | list query |
| `[Feature]ErrorCode` | const literal | procedures + services |

---

## 3. tRPC Procedures

**File**: `apps/api/src/routers/[feature-name].ts`

| Procedure | Type | Input | Output | Min role | Flag guard |
|---|---|---|---|---|---|
| `[feature].get` | query | `Get[Feature]Input` | `[Feature]Dto` | viewer | yes |
| `[feature].list` | query | `List[Feature]Input` | `[Feature]ListDto` | viewer | yes |
| `[feature].create` | mutation | `Create[Feature]Input` | `[Feature]Dto` | member | yes |
| `[feature].update` | mutation | `Update[Feature]Input` | `[Feature]Dto` | member | yes |
| `[feature].delete` | mutation | `Get[Feature]Input` | void | admin | yes |

All use `orgScopedProcedure`. `organizationId` from session — never from input.

---

## 4. DAL

**File**: `apps/api/src/dal/[feature-name].ts`

| Function | Cache key | Invalidated by |
|---|---|---|
| `get[Feature]ById` | `[feature]:org:{orgId}:{id}` TTL 5m | `update`, `delete` |
| `list[Feature]s` | `[feature]s:org:{orgId}` TTL 5m | `create`, `update`, `delete` |
| `create[Feature]Record` | — | invalidates list |
| `update[Feature]Record` | — | invalidates one + list |
| `delete[Feature]Record` | — | invalidates one + list |

---

## 5. Services

**File**: `apps/api/src/services/[feature-name].ts`

| Function | Returns | Purpose |
|---|---|---|
| `buildCreate[Feature]Payload` | `Result<DBPayload>` | validate + transform input |
| `can[Feature]` | `boolean` | pure RBAC lookup |
| `validate[Feature]State` | `Result<void>` | state machine guard |

Zero infrastructure imports. `Result<T,E>` — no `throw` on business errors.

---

## 6. Feature Flag

| Property | Value |
|---|---|
| Name | `ff-[feature-name]` |
| Default | OFF |
| Granularity | org |
| Kill switch | < 5s |
| Guard locations | Every tRPC procedure + RSC page.tsx |
| Planned removal | [date] |

---

## 7. RBAC Matrix

| Action | owner | admin | member | viewer |
|---|---|---|---|---|
| read | ✓ | ✓ | ✓ | ✓ |
| create | ✓ | ✓ | ✓ | — |
| update | ✓ | ✓ | ✓ | — |
| delete | ✓ | ✓ | — | — |

---

## 8. Cache Strategy

| Key | Data | TTL | Invalidated by |
|---|---|---|---|
| `[feature]:org:{orgId}:{id}` | Single DTO | 5m | update, delete |
| `[feature]s:org:{orgId}` | List (first page) | 5m | create, update, delete |

React Query keys align with server cache: `[['[featureCamel]', 'list'], ...]`.

---

## 9. Background Jobs

| Effect | Tool | ID template | Trigger |
|---|---|---|---|
| [side effect description] | BullMQ / Temporal | `[feature]-{id}` | `[feature].create` mutation |

---

## 10. Observability Plan

| Signal | Attribute | Tool |
|---|---|---|
| OTel span | `org.id`, `user.id`, `procedure.name` | Tempo |
| Structured log | `organizationId`, `userId`, `correlationId`, `durationMs` | Loki |
| Analytics event | `[feature].created`, `[feature].updated` | ClickHouse only |
| Error capture | GlitchTip `captureException` | error.tsx + catch |
| Alert | error_rate > 1% / p95 > threshold | Grafana Alerting |

---

## 11. Testing Plan

| Type | File | Tool | Critical |
|---|---|---|---|
| Unit (services) | `apps/api/test/[feature]/services.test.ts` | bun:test | — |
| Integration (DAL) | `apps/api/test/[feature]/dal.test.ts` | bun:test + Testcontainers | cross-org isolation |
| Integration (procedures) | `apps/api/test/[feature]/procedures.test.ts` | bun:test + Testcontainers | RBAC, idempotency |
| E2E happy path | `apps/web/tests/e2e/[feature]/happy.spec.ts` | Playwright | — |
| E2E @critical | `apps/web/tests/e2e/[feature]/isolation.spec.ts` | Playwright | **blocks merge** |

---

## 12. Security Checklist

- [ ] `organizationId` extracted from BetterAuth session — never from procedure input
- [ ] Every DAL query includes `eq(table.organizationId, orgId)` in `where`
- [ ] RBAC checked via `can[Feature](ctx.member.role, action)` in every mutation
- [ ] ioredis rate limit on writes: `rl:[feature].[action]:{userId}`
- [ ] No raw SQL — `drizzle-kit generate` only
- [ ] No `@delta-global/analytics-db` imports in `apps/api` or `apps/web`
- [ ] Secrets via `env.ts` + Infisical
- [ ] Sensitive fields absent from DTO schemas and cache values

---

## 13. Open Questions

1. [Decision before implementation — e.g. "Soft-delete or hard-delete?"]
2. [Decision before implementation]

*(Delete if none.)*

---

## 14. Complexity Justification

> Fill only if a hard constraint is intentionally violated.

| Violation | Why needed | Simpler alternative rejected because |
|---|---|---|
| [e.g. raw SQL in migration] | [reason] | [why drizzle-kit generate was insufficient] |
