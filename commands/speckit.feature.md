---
description: Full-stack feature scaffold for the Delta-Global stack. Walks through Contract-First Zod schemas → Drizzle table → DAL (server-only, ioredis) → pure Services (Result<T,E>) → tRPC procedures (orgScopedProcedure) → RSC page (SDK caller) → Client components (@trpc/react-query) → BullMQ/Temporal side effects → bun:test tests. Generates every file for a complete feature slice compliant with the stack conventions.
handoffs:
  - label: Plan the feature
    agent: speckit.plan
    prompt: Generate a full feature plan for the feature described in $ARGUMENTS. Include route map, RSC/client boundary, data flow, caching strategy, RBAC matrix, and testing plan.
  - label: Scaffold the route
    agent: speckit.scaffold.route
    prompt: Scaffold the App Router route segment for this feature.
  - label: Scaffold the DAL
    agent: speckit.scaffold.dal
    prompt: Generate the DAL methods needed for this feature's CRUD operations.
  - label: Scaffold Temporal workflow
    agent: speckit.scaffold.temporal
    prompt: Scaffold the Temporal workflow and activities for this feature's async side effects.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check the scaffolded feature for RFC drift, RBAC gaps, and hard constraint violations.
---

## User Input

```text
$ARGUMENTS
```

Parse the first positional argument as the **feature name** (kebab-case slug — e.g. `post-publishing`, `invoice-export`).

Optional flags (all can be combined):

| Flag | Meaning | Default |
|---|---|---|
| `--description <text>` | One-line feature description | `""` |
| `--fields <list>` | Comma-separated field definitions `name:type` | inferred |
| `--skip-db` | Skip Phase 1 (table already exists) | generate table |
| `--skip-queue` | Skip Phase 7 (no async side effects) | generate BullMQ worker |
| `--skip-temporal` | Skip Temporal workflow generation | generate if `--temporal` or needs_temporal |
| `--temporal` | Force Temporal workflow instead of BullMQ | auto-detect from description |
| `--skip-tests` | Skip Phase 9 test files | generate tests |
| `--skip-ship` | Skip Phase 10 ship checklist | include checklist |
| `--id-type <type>` | Primary key type (`uuid` or `cuid2`) | `uuid` |
| `--no-auth` | Feature is public (no BetterAuth session check) | authenticated |
| `--roles <list>` | Comma-separated roles that can access (owner,admin,member,viewer) | `member` minimum |
| `--only <phases>` | Comma-separated phases to execute (e.g. `0,1,2`) | all phases |
| `--dry-run` | Print file contents instead of writing | write files |

If feature name is missing, ask for it before proceeding.

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_feature`. Apply standard hook-processing: skip disabled hooks, skip hooks with non-empty condition, surface optional as instructions, auto-execute mandatory.

Check for `packages/db/src/schema/` and `apps/api/src/dal/` — if neither exists, warn that this project does not follow the expected monorepo structure and ask whether to proceed.

---

## Feature Scaffold

This scaffold walks through 10 phases. Each phase produces one or more files. After all phases complete, run the verification checklist.

### Phase 0 — Contract First (Zod Schemas)

**Goal**: Define the Zod schemas and DTO types in `@delta-global/shared` before any implementation.

**Generate**: `packages/shared/src/schemas/<feature-kebab>.ts`

```ts
// packages/shared/src/schemas/<feature-kebab>.ts
import { z } from 'zod'

// ─── Business error codes ────────────────────────────────────────────────────
// Use `const` literals so tRPC can return typed errors the client can switch on.

export const <Feature>ErrorCode = {
  NOT_FOUND:        '<FEATURE>_NOT_FOUND',
  FORBIDDEN:        '<FEATURE>_FORBIDDEN',
  QUOTA_EXCEEDED:   '<FEATURE>_QUOTA_EXCEEDED',
  INVALID_STATE:    '<FEATURE>_INVALID_STATE',
  // TODO: add domain-specific error codes
} as const

export type <Feature>ErrorCode = typeof <Feature>ErrorCode[keyof typeof <Feature>ErrorCode]

// ─── Input schemas (one per tRPC procedure) ───────────────────────────────────
// Precise constraints: no z.any, no z.unknown, no z.record(z.any)

export const Create<Feature>Input = z.object({
  // organizationId is extracted from the BetterAuth session — NEVER in input
  // <name>: z.string().min(1).max(255),
  // <field>: z.enum(['draft', 'active', 'archived']),
})

export const Update<Feature>Input = z.object({
  id: z.string().uuid(),
  // TODO: add updatable fields — use .optional() for partial updates
})

export const Get<Feature>Input = z.object({
  id: z.string().uuid(),
})

export const List<Feature>Input = z.object({
  cursor: z.string().uuid().optional(),
  limit:  z.number().int().min(1).max(100).default(20),
  sortBy: z.enum(['createdAt', 'updatedAt']).default('createdAt'),
  order:  z.enum(['asc', 'desc']).default('desc'),
})

// ─── Output DTO schemas (what the client receives) ────────────────────────────
// Omit sensitive fields (tokens, hashes, internal IDs, secrets).

export const <Feature>Dto = z.object({
  id:             z.string().uuid(),
  organizationId: z.string().uuid(),
  // TODO: add public fields
  createdAt:      z.string().datetime(),
  updatedAt:      z.string().datetime(),
})

export const <Feature>ListDto = z.object({
  items:      z.array(<Feature>Dto),
  nextCursor: z.string().uuid().nullable(),
  total:      z.number().int(),
})

// ─── Inferred types ───────────────────────────────────────────────────────────

export type Create<Feature>Input = z.infer<typeof Create<Feature>Input>
export type Update<Feature>Input = z.infer<typeof Update<Feature>Input>
export type Get<Feature>Input    = z.infer<typeof Get<Feature>Input>
export type List<Feature>Input   = z.infer<typeof List<Feature>Input>
export type <Feature>Dto         = z.infer<typeof <Feature>Dto>
export type <Feature>ListDto     = z.infer<typeof <Feature>ListDto>
```

**Export from barrel**: add `export * from './<feature-kebab>'` to `packages/shared/src/schemas/index.ts`.

**Checklist**:
- [ ] Every input field has a precise constraint (`.min`, `.max`, `.uuid()`, `.email()`, `.regex()`, etc.)
- [ ] No `z.any()`, `z.unknown()`, `z.record(z.any())` — Biome will fail
- [ ] `organizationId` is absent from input schemas (extracted from session in procedures)
- [ ] DTO schemas omit sensitive fields
- [ ] Types are inferred — never hand-duplicated

---

### Phase 1 — Database Schema (Drizzle)

**Goal**: Express the domain in Drizzle, generate migration, export `InferSelectModel` types.

**Generate**: `packages/db/src/schema/<feature-kebab>.ts`

```ts
// packages/db/src/schema/<feature-kebab>.ts
import { pgTable, text, timestamp, uuid, index, uniqueIndex } from 'drizzle-orm/pg-core'
import { relations } from 'drizzle-orm'
import { organizations } from './organization'

export const <featureSnake> = pgTable(
  '<feature_snake>',
  {
    id:             uuid('id').primaryKey().defaultRandom(),
    organizationId: uuid('organization_id')
      .notNull()
      .references(() => organizations.id, { onDelete: 'cascade' }),
    // TODO: add domain columns
    // name: text('name').notNull(),
    // status: text('status', { enum: ['draft', 'active', 'archived'] }).notNull().default('draft'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    // Tenant-scoped index: EVERY query must filter by organizationId
    index('<feature_snake>_org_idx').on(t.organizationId, t.createdAt.desc()),
    // TODO: add composite indexes for frequent filter+sort patterns
  ],
)

// ─── Relations ────────────────────────────────────────────────────────────────

export const <featureSnake>Relations = relations(<featureSnake>, ({ one }) => ({
  organization: one(organizations, {
    fields: [<featureSnake>.organizationId],
    references: [organizations.id],
  }),
  // TODO: add other relations
}))

// ─── Types ────────────────────────────────────────────────────────────────────

export type <Feature>    = typeof <featureSnake>.$inferSelect
export type New<Feature> = typeof <featureSnake>.$inferInsert
```

**Also update**: `packages/db/src/schema/index.ts` — add the export.

**After writing**: run `bun --filter @delta-global/db drizzle-kit generate` and review the SQL diff.

**Checklist**:
- [ ] `uuid().primaryKey().defaultRandom()` — no serial IDs
- [ ] `organizationId` FK with `onDelete` decision documented (cascade vs restrict)
- [ ] Timestamps with `withTimezone: true`
- [ ] Index on `(organizationId, createdAt desc)` at minimum
- [ ] `InferSelectModel` / `InferInsertModel` types exported
- [ ] `drizzle-kit generate` only — never handwrite SQL

---

### Phase 2 — Data Access Layer (DAL)

**Goal**: Single choke-point for every DB interaction. Auth, tenant scoping, and caching live here.

**Generate**: `apps/api/src/dal/<feature-kebab>.ts`

```ts
// apps/api/src/dal/<feature-kebab>.ts
import 'server-only'
import { cache } from 'react'
import { eq, and, desc, lt } from 'drizzle-orm'
import { db } from '@delta-global/db'
import { <featureSnake> } from '@delta-global/db/schema'
import { redis } from '@/lib/redis'
import { getSession, assertMembership } from '@/lib/auth'
import type { List<Feature>Input } from '@delta-global/shared'

// ─── Cache keys ───────────────────────────────────────────────────────────────
// Pattern: <feature>:org:{orgId}:{id}  |  <feature>s:org:{orgId}
// Invalidate on every mutation by DEL on the key prefix.

const cacheKey = {
  one:  (orgId: string, id: string) => `<feature>:org:${orgId}:${id}`,
  list: (orgId: string)             => `<feature>s:org:${orgId}`,
}

const CACHE_TTL = 60 * 5 // 5 minutes

// ─── Reads ────────────────────────────────────────────────────────────────────

/**
 * Fetch a single <Feature> by ID, scoped to the authenticated user's organization.
 * Cached in Redis for 5 minutes. Wrapped with React cache() for intra-request dedup.
 */
export const get<Feature>ById = cache(async (id: string) => {
  const session = await getSession()
  if (!session) throw new Error('UNAUTHORIZED')

  const orgId = session.activeOrganizationId
  await assertMembership(session.user.id, orgId)

  const cached = await redis.get(cacheKey.one(orgId, id))
  if (cached) return JSON.parse(cached) as <Feature>

  const row = await db.query.<featureSnake>.findFirst({
    where: and(
      eq(<featureSnake>.id, id),
      eq(<featureSnake>.organizationId, orgId),   // ← tenant scope: always required
    ),
    columns: {
      // Explicitly select columns — never SELECT *
      id: true, organizationId: true, createdAt: true, updatedAt: true,
      // TODO: add business columns
    },
  })

  if (!row) return null

  await redis.setex(cacheKey.one(orgId, id), CACHE_TTL, JSON.stringify(row))
  return row
})

/**
 * List <Feature>s for the current organization with cursor-based pagination.
 */
export const list<Feature>s = cache(async (input: List<Feature>Input) => {
  const session = await getSession()
  if (!session) throw new Error('UNAUTHORIZED')

  const orgId = session.activeOrganizationId
  await assertMembership(session.user.id, orgId)

  const cached = await redis.get(cacheKey.list(orgId))
  if (cached && !input.cursor) return JSON.parse(cached) as <Feature>[]

  // Whitelisted sort columns — never interpolate user-supplied strings
  const sortColumn = <featureSnake>.createdAt // TODO: map input.sortBy to actual column

  const rows = await db.query.<featureSnake>.findMany({
    where: and(
      eq(<featureSnake>.organizationId, orgId),   // ← tenant scope: always required
      input.cursor ? lt(<featureSnake>.createdAt, new Date(input.cursor)) : undefined,
    ),
    orderBy: desc(sortColumn),
    limit: input.limit + 1, // fetch one extra to determine if there is a next page
    columns: {
      id: true, organizationId: true, createdAt: true, updatedAt: true,
      // TODO: add business columns
    },
  })

  const hasMore = rows.length > input.limit
  const items = hasMore ? rows.slice(0, -1) : rows

  if (!input.cursor) {
    await redis.setex(cacheKey.list(orgId), CACHE_TTL, JSON.stringify(items))
  }

  return {
    items,
    nextCursor: hasMore ? items.at(-1)?.createdAt.toISOString() ?? null : null,
    total: items.length,
  }
})

// ─── Writes ───────────────────────────────────────────────────────────────────

/** Insert a new <Feature> and invalidate the list cache. */
export async function create<Feature>Record(
  data: Omit<New<Feature>, 'id' | 'createdAt' | 'updatedAt'>,
  organizationId: string,
): Promise<<Feature>> {
  const [row] = await db
    .insert(<featureSnake>)
    .values({ ...data, organizationId })
    .returning()
  if (!row) throw new Error('<FEATURE>_INSERT_FAILED')
  await invalidate<Feature>Cache(organizationId)
  return row
}

/** Update fields on an existing <Feature> and invalidate caches. */
export async function update<Feature>Record(
  id: string,
  organizationId: string,
  data: Partial<Omit<New<Feature>, 'id' | 'organizationId' | 'createdAt' | 'updatedAt'>>,
): Promise<<Feature>> {
  const [row] = await db
    .update(<featureSnake>)
    .set({ ...data, updatedAt: new Date() })
    .where(and(
      eq(<featureSnake>.id, id),
      eq(<featureSnake>.organizationId, organizationId),  // ← ownership check in query
    ))
    .returning()
  if (!row) throw new Error('<FEATURE>_NOT_FOUND_OR_FORBIDDEN')
  await invalidate<Feature>Cache(organizationId, id)
  return row
}

/** Hard-delete a <Feature>. Use soft-delete if the domain requires an audit trail. */
export async function delete<Feature>Record(
  id: string,
  organizationId: string,
): Promise<void> {
  await db
    .delete(<featureSnake>)
    .where(and(
      eq(<featureSnake>.id, id),
      eq(<featureSnake>.organizationId, organizationId),  // ← ownership check in query
    ))
  await invalidate<Feature>Cache(organizationId, id)
}

// ─── Cache invalidation ───────────────────────────────────────────────────────

async function invalidate<Feature>Cache(orgId: string, id?: string) {
  const keys = await redis.keys(`<feature>*:org:${orgId}*`)
  if (keys.length > 0) await redis.del(...keys)
}
```

**Checklist**:
- [ ] `import 'server-only'` as the first non-comment line
- [ ] `organizationId` is an explicit parameter on every write function
- [ ] Every query filters by `eq(table.organizationId, orgId)` — no cross-tenant leaks
- [ ] Cursor-based pagination only — no `OFFSET`
- [ ] Explicit column selection — no `SELECT *`
- [ ] Reads wrapped with `cache()` for intra-request dedup
- [ ] Redis cache with TTL, invalidated on every mutation
- [ ] Tokens, hashes, secrets excluded from returned rows
- [ ] Writes return the affected row via `.returning()`

---

### Phase 3 — Business Logic (Services)

**Goal**: Pure, side-effect-free functions. Unit-testable with zero mocks.

**Generate**: `apps/api/src/services/<feature-kebab>.ts`

```ts
// apps/api/src/services/<feature-kebab>.ts
// ─── ZERO external imports ────────────────────────────────────────────────────
// No db, auth, redis, Hono, tRPC, Next, headers, cookies, fetch, Date.now, Math.random.
// Every dependency injected as a parameter.

import type { Create<Feature>Input, Update<Feature>Input } from '@delta-global/shared'
import type { <Feature>ErrorCode } from '@delta-global/shared'

// ─── Result type ──────────────────────────────────────────────────────────────

export type Result<T, E extends string = <Feature>ErrorCode> =
  | { ok: true;  data: T }
  | { ok: false; error: E; message?: string }

// ─── Service functions ────────────────────────────────────────────────────────

/**
 * Validate and transform a create input into the DB payload.
 * Returns Result to force callers to handle all error paths.
 */
export function buildCreate<Feature>Payload(
  input: Create<Feature>Input,
  opts: { now: Date },
): Result<Omit<Parameters<typeof create<Feature>Record>[0], 'organizationId'>> {
  // Guard clauses on top — happy path at the bottom
  // if (!input.name.trim()) return { ok: false, error: '<Feature>ErrorCode.INVALID_STATE' }

  return {
    ok: true,
    data: {
      // TODO: map input fields to DB payload
      // name: input.name.trim(),
    },
  }
}

/**
 * Check whether a role is allowed to perform an action.
 * Pure lookup — no DB or auth calls.
 */
export function can<Feature>(
  role: 'owner' | 'admin' | 'member' | 'viewer',
  action: 'create' | 'update' | 'delete' | 'read',
): boolean {
  const matrix: Record<typeof action, typeof role[]> = {
    create: ['owner', 'admin', 'member'],
    update: ['owner', 'admin', 'member'],
    delete: ['owner', 'admin'],
    read:   ['owner', 'admin', 'member', 'viewer'],
  }
  return matrix[action].includes(role)
}

// TODO: add domain-specific validation, state machine checks, and quota checks.
// Keep nesting < 2 levels. One function per use-case. Composable inputs/outputs.
```

**Checklist**:
- [ ] Zero imports from `db`, `auth`, `redis`, `Hono`, `tRPC`, `Next`, `headers`, `cookies`
- [ ] `Result<T, E>` discriminated union — no `throw` on business errors
- [ ] `now`, `rng` injected as parameters — never `Date.now()` or `Math.random()` directly
- [ ] Guard clauses at top, happy path at bottom
- [ ] Nesting < 2 levels
- [ ] Every branch is testable without mocks

---

### Phase 4 — tRPC Procedures

**Goal**: Thin orchestrator. Auth → feature flag → role check → quota → service → DAL → queue → cache invalidation.

**Generate**: `apps/api/src/routers/<feature-kebab>.ts`

```ts
// apps/api/src/routers/<feature-kebab>.ts
import { TRPCError } from '@trpc/server'
import { orgScopedProcedure, router } from '../trpc'
import { flagService } from '@/lib/flags'
import { redis } from '@/lib/redis'
import {
  Create<Feature>Input,
  Update<Feature>Input,
  Get<Feature>Input,
  List<Feature>Input,
  <Feature>Dto,
  <Feature>ListDto,
} from '@delta-global/shared'
import {
  get<Feature>ById,
  list<Feature>s,
  create<Feature>Record,
  update<Feature>Record,
  delete<Feature>Record,
} from '../dal/<feature-kebab>'
import { buildCreate<Feature>Payload, can<Feature> } from '../services/<feature-kebab>'
// import { queue } from '@/lib/bullmq'         // ← fire-and-forget side effects
// import { temporalClient } from '@/lib/temporal' // ← durable async workflows

const FLAG = 'ff-<feature-kebab>'

export const <featureCamel>Router = router({
  // ── Queries ──────────────────────────────────────────────────────────────────

  get: orgScopedProcedure
    .meta({ name: '<feature>.get' })
    .input(Get<Feature>Input)
    .output(<Feature>Dto)
    .query(async ({ ctx, input }) => {
      if (!await flagService.isEnabled(FLAG, ctx.organizationId)) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Feature not available' })
      }

      const row = await get<Feature>ById(input.id)
      if (!row || row.organizationId !== ctx.organizationId) {
        throw new TRPCError({ code: 'NOT_FOUND', message: 'Not found' })
      }
      // TODO: map DB row to DTO (omit sensitive fields)
      return row as <Feature>Dto
    }),

  list: orgScopedProcedure
    .meta({ name: '<feature>.list' })
    .input(List<Feature>Input)
    .output(<Feature>ListDto)
    .query(async ({ ctx, input }) => {
      if (!await flagService.isEnabled(FLAG, ctx.organizationId)) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Feature not available' })
      }
      return list<Feature>s(input)
    }),

  // ── Mutations ─────────────────────────────────────────────────────────────

  create: orgScopedProcedure
    .meta({ name: '<feature>.create' })
    .input(Create<Feature>Input)
    .output(<Feature>Dto)
    .mutation(async ({ ctx, input }) => {
      if (!await flagService.isEnabled(FLAG, ctx.organizationId)) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Feature not available' })
      }

      // Role check (extracted from BetterAuth session — never from input)
      if (!can<Feature>(ctx.member.role, 'create')) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Insufficient role' })
      }

      // Rate limit — rl:<procedure>:<userId>
      const rlKey = `rl:<feature>.create:${ctx.session.user.id}`
      const [, reqs] = await redis.multi().incr(rlKey).expire(rlKey, 60).exec() as [null, number, null, null][]
      if ((reqs as unknown as number) > 20) {
        throw new TRPCError({ code: 'TOO_MANY_REQUESTS', message: 'Rate limit exceeded' })
      }

      // Pure service validation
      const payload = buildCreate<Feature>Payload(input, { now: new Date() })
      if (!payload.ok) {
        throw new TRPCError({ code: 'BAD_REQUEST', message: payload.error })
      }

      // DAL write (includes cache invalidation)
      const row = await create<Feature>Record(payload.data, ctx.organizationId)

      // Fire-and-forget side effects (choose one):
      // await queue.add('<feature>-created', { id: row.id, organizationId: ctx.organizationId })
      // await temporalClient.workflow.start(<featureCamel>Workflow, {
      //   workflowId: `<feature>-${row.id}`,
      //   taskQueue:  'default',
      //   args:       [{ organizationId: ctx.organizationId, id: row.id }],
      // })

      // TODO: map row to DTO
      return row as <Feature>Dto
    }),

  update: orgScopedProcedure
    .meta({ name: '<feature>.update' })
    .input(Update<Feature>Input)
    .output(<Feature>Dto)
    .mutation(async ({ ctx, input }) => {
      if (!await flagService.isEnabled(FLAG, ctx.organizationId)) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Feature not available' })
      }
      if (!can<Feature>(ctx.member.role, 'update')) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Insufficient role' })
      }
      const { id, ...data } = input
      const row = await update<Feature>Record(id, ctx.organizationId, data)
      return row as <Feature>Dto
    }),

  delete: orgScopedProcedure
    .meta({ name: '<feature>.delete' })
    .input(Get<Feature>Input)
    .mutation(async ({ ctx, input }) => {
      if (!await flagService.isEnabled(FLAG, ctx.organizationId)) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Feature not available' })
      }
      if (!can<Feature>(ctx.member.role, 'delete')) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Insufficient role' })
      }
      await delete<Feature>Record(input.id, ctx.organizationId)
    }),
})
```

**Wire into appRouter**: add `<featureCamel>: <featureCamel>Router` to `apps/api/src/routers/index.ts`.

**Checklist**:
- [ ] `orgScopedProcedure` used — `organizationId` from session, never from `input`
- [ ] `.input()` schema imported from `@delta-global/shared` — never inlined
- [ ] `.output()` schema for typed SDK contracts
- [ ] `.meta({ name: '...' })` for OTel spans and structured logs
- [ ] Feature flag checked in every procedure
- [ ] Role check via `ctx.member.role` (service layer evaluates)
- [ ] Rate limit via ioredis before any DB write
- [ ] Background work dispatched asynchronously (BullMQ or Temporal)
- [ ] `TRPCError` with generic client message; full stack logged server-side

---

### Phase 5 — Read Path (RSC Page)

**Goal**: Server Component reads via SDK caller; zero client JS for the happy path.

**Generate**: `apps/web/app/(app)/[workspace]/<feature-kebab>/page.tsx`

```tsx
// apps/web/app/(app)/[workspace]/<feature-kebab>/page.tsx
import { Suspense } from 'react'
import { notFound, redirect } from 'next/navigation'
import type { Metadata } from 'next'
import { createCaller } from '@delta-global/sdk'
import { getSession } from '@/lib/auth'
import { flagService } from '@/lib/flags'
import { <Feature>List } from '@/components/features/<feature-kebab>/<Feature>List'
import { <Feature>ListSkeleton } from '@/components/features/<feature-kebab>/<Feature>ListSkeleton'

interface Props {
  params: Promise<{ workspace: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { workspace } = await params
  return {
    title: '<Feature>s',
    description: 'Manage <feature>s for your organization',
  }
}

export default async function <Feature>sPage({ params }: Props) {
  const { workspace } = await params

  // Feature flag guard — redirect to dashboard if flag is OFF
  const session = await getSession()
  if (!session) redirect('/login')

  const flagOn = await flagService.isEnabled('ff-<feature-kebab>', workspace)
  if (!flagOn) redirect(`/${workspace}`)

  return (
    <main>
      <Suspense fallback={<<Feature>ListSkeleton />}>
        <<Feature>DataLayer workspaceId={workspace} />
      </Suspense>
    </main>
  )
}

// Async RSC that fetches data — keep inside Suspense boundary
async function <Feature>DataLayer({ workspaceId }: { workspaceId: string }) {
  // Fetch via SDK server caller — NOT React Query, NOT fetch('/api/...')
  const caller = createCaller({ organizationId: workspaceId })
  const data = await caller.<featureCamel>.list({ limit: 20 })

  return <<Feature>List initialData={data} workspaceId={workspaceId} />
}
```

**Generate**: `apps/web/app/(app)/[workspace]/<feature-kebab>/loading.tsx`

```tsx
// apps/web/app/(app)/[workspace]/<feature-kebab>/loading.tsx
import { <Feature>ListSkeleton } from '@/components/features/<feature-kebab>/<Feature>ListSkeleton'

export default function Loading() {
  return <<Feature>ListSkeleton />
}
```

**Generate**: `apps/web/app/(app)/[workspace]/<feature-kebab>/error.tsx`

```tsx
// apps/web/app/(app)/[workspace]/<feature-kebab>/error.tsx
'use client'

import { useEffect } from 'react'
import { Button } from '@delta-global/ui'
// import * as Sentry from '@sentry/nextjs' // ← replace with GlitchTip SDK

interface Props {
  error: Error & { digest?: string }
  reset: () => void
}

export default function <Feature>sError({ error, reset }: Props) {
  useEffect(() => {
    // Sentry.captureException(error) // ← GlitchTip capture
    console.error(error)
  }, [error])

  return (
    <div role="alert" className="flex flex-col items-center gap-4 py-12">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="text-muted-foreground text-sm">{error.digest ?? 'An unexpected error occurred'}</p>
      <Button type="button" variant="outline" onClick={reset}>
        Réessayer
      </Button>
    </div>
  )
}
```

**Checklist**:
- [ ] `page.tsx` is a Server Component — no `'use client'`
- [ ] Data fetched via SDK `createCaller` — not `fetch()` or React Query in RSC
- [ ] Feature flag guard redirects before rendering
- [ ] `<Suspense>` wraps async data layer
- [ ] `generateMetadata` present
- [ ] `loading.tsx` skeleton matches final layout
- [ ] `error.tsx` captures to GlitchTip + has Réessayer button

---

### Phase 6 — Write Path (Client Components)

**Goal**: Minimal `'use client'` leaf components. Form → tRPC mutation → optimistic feedback.

**Generate**: `apps/web/components/features/<feature-kebab>/Create<Feature>Form.tsx`

```tsx
// apps/web/components/features/<feature-kebab>/Create<Feature>Form.tsx
'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/trpc/client'
import { Create<Feature>Input } from '@delta-global/shared'
import { Button, Input, Form, FormField, FormItem, FormLabel, FormMessage } from '@delta-global/ui'
import { toast } from 'sonner'

interface Props {
  workspaceId: string
  onSuccess?: () => void
}

export function Create<Feature>Form({ workspaceId, onSuccess }: Props) {
  const queryClient = useQueryClient()

  const form = useForm<Create<Feature>Input>({
    resolver: zodResolver(Create<Feature>Input),
    defaultValues: {
      // TODO: add default values
    },
  })

  const mutation = api.<featureCamel>.create.useMutation({
    onSuccess: () => {
      // Invalidate React Query cache — aligned with server-side Redis key pattern
      queryClient.invalidateQueries({ queryKey: [['<featureCamel>', 'list'], { input: { }, type: 'query' }] })
      form.reset()
      toast.success('<Feature> created')
      onSuccess?.()
    },
    onError: (err) => {
      // Map tRPC field errors back to react-hook-form
      if (err.data?.zodError?.fieldErrors) {
        for (const [field, messages] of Object.entries(err.data.zodError.fieldErrors)) {
          form.setError(field as keyof Create<Feature>Input, { message: messages?.[0] })
        }
      } else {
        toast.error(err.message)
      }
    },
  })

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((data) => mutation.mutate(data))}
        aria-busy={mutation.isPending}
        className="space-y-4"
      >
        {/* TODO: add form fields */}
        <FormField
          control={form.control}
          name="name" // TODO: replace with actual field name
          render={({ field }) => (
            <FormItem>
              <FormLabel><Feature> name</FormLabel>
              <Input
                aria-invalid={!!form.formState.errors.name}
                aria-describedby={form.formState.errors.name ? '<feature>-name-error' : undefined}
                {...field}
              />
              <FormMessage id="<feature>-name-error" />
            </FormItem>
          )}
        />

        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create <Feature>'}
        </Button>
      </form>
    </Form>
  )
}
```

**Generate**: `apps/web/components/features/<feature-kebab>/<Feature>List.tsx`

```tsx
// apps/web/components/features/<feature-kebab>/<Feature>List.tsx
'use client'

import { api } from '@/lib/trpc/client'
import type { <Feature>ListDto } from '@delta-global/shared'

interface Props {
  workspaceId: string
  initialData: <Feature>ListDto
}

export function <Feature>List({ workspaceId, initialData }: Props) {
  const { data } = api.<featureCamel>.list.useQuery(
    { limit: 20 },
    {
      initialData,      // Hydrate from RSC fetch — no client re-fetch on load
      staleTime: 30_000,
    },
  )

  if (data.items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-12 text-center">
        {/* TODO: empty state illustration */}
        <p className="text-muted-foreground">No <feature>s yet.</p>
        {/* TODO: primary CTA */}
      </div>
    )
  }

  return (
    <div role="list" aria-label="<Feature>s">
      {data.items.map((item) => (
        <div key={item.id} role="listitem">
          {/* TODO: render item fields */}
        </div>
      ))}
    </div>
  )
}
```

**Generate**: `apps/web/components/features/<feature-kebab>/<Feature>ListSkeleton.tsx`

```tsx
// apps/web/components/features/<feature-kebab>/<Feature>ListSkeleton.tsx
import { Skeleton } from '@delta-global/ui'

export function <Feature>ListSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading <Feature>s" className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-md" />
      ))}
    </div>
  )
}
```

**Checklist**:
- [ ] `'use client'` only on interactive leaves — not on the page
- [ ] `react-hook-form` + `zodResolver` — schema from `@delta-global/shared`
- [ ] tRPC `useMutation` (not `fetch` or Server Actions)
- [ ] `queryClient.invalidateQueries` on success with correct queryKey
- [ ] Submit disabled while `mutation.isPending` — no double-submit
- [ ] Server errors mapped to fields via `setError`
- [ ] `aria-invalid` + `aria-describedby` on error fields — AA a11y
- [ ] `aria-live` for async state changes
- [ ] 44×44px touch targets on mobile (Tailwind min-h, min-w)
- [ ] Strings via `next-intl` — no hardcoded FR/EN

---

### Phase 7 — Side Effects (BullMQ / Temporal)

**Goal**: Slow or unreliable work runs outside the request. The tRPC procedure stays under 200ms.

Skip this phase if `--skip-queue` is passed.

**For BullMQ (fire-and-forget)** — generate `apps/api/src/workers/<feature-kebab>.worker.ts`:

```ts
// apps/api/src/workers/<feature-kebab>.worker.ts
import { Worker, Queue } from 'bullmq'
import { redis } from '@/lib/redis'

export const <featureCamel>Queue = new Queue('<feature-kebab>', { connection: redis })

export const <featureCamel>Worker = new Worker(
  '<feature-kebab>',
  async (job) => {
    const { id, organizationId } = job.data

    switch (job.name) {
      case '<feature>-created': {
        // TODO: implement side effects (emails, webhooks, third-party APIs)
        break
      }
      default:
        throw new Error(`Unknown job: ${job.name}`)
    }
  },
  {
    connection: redis,
    concurrency: 5,
    removeOnComplete: { count: 100 },
    removeOnFail:     { count: 50 },
  },
)

<featureCamel>Worker.on('failed', (job, err) => {
  // TODO: capture to GlitchTip + alert if dead-letter queue grows
  console.error(`[<feature>] Job ${job?.id} failed:`, err)
})
```

**For Temporal (durable workflows)** — run `/speckit.scaffold.temporal <feature-kebab>` separately.

**Checklist**:
- [ ] Worker is idempotent — safe to retry on failure
- [ ] Retry strategy configured
- [ ] External calls isolated (no direct DB writes from the tRPC procedure body)
- [ ] Dead-letter / failure alert wired to GlitchTip or PagerDuty

---

### Phase 8 — Observability

**Goal**: Every procedure is traceable. Failures are loud. Analytics go to ClickHouse, not Postgres.

```
Observability checklist (integrate into existing files):

apps/api/src/routers/<feature-kebab>.ts
  [ ] .meta({ name: '<feature>.<action>' }) on every procedure
  [ ] OTel span attributes: org.id, user.id, procedure.name (set via trpc middleware)
  [ ] Structured log fields: organizationId, userId, correlationId, durationMs

apps/web/app/(app)/[workspace]/<feature-kebab>/error.tsx
  [ ] GlitchTip / Sentry captureException in useEffect

Analytics events (ClickHouse only — never Postgres)
  [ ] <feature>.created   { orgId, userId, <feature>Id }
  [ ] <feature>.updated   { orgId, userId, <feature>Id, fields[] }
  [ ] <feature>.deleted   { orgId, userId, <feature>Id }
  [ ] <feature>.viewed    { orgId, userId }
  [ ] Event names follow feature.action convention
  [ ] NO @delta-global/analytics-db imports in apps/api or apps/web

Grafana / Mimir
  [ ] Volume counter per procedure per org
  [ ] p50/p95/p99 latency per procedure (Tempo)
  [ ] Error rate per procedure and error type (Loki + GlitchTip)
  [ ] BullMQ dead-letter queue > 0 alert
```

---

### Phase 9 — Tests

**Goal**: Confidence without brittle tests. Unit (bun:test, pure) → Integration (Testcontainers) → E2E (Playwright).

**Generate**: `apps/api/test/<feature-kebab>/services.test.ts` _(skip if `--skip-tests`)_

```ts
// apps/api/test/<feature-kebab>/services.test.ts
import { describe, it, expect } from 'bun:test'
import { buildCreate<Feature>Payload, can<Feature> } from '../../src/services/<feature-kebab>'

describe('<Feature> services', () => {
  describe('buildCreate<Feature>Payload', () => {
    it('returns ok with valid input', () => {
      const result = buildCreate<Feature>Payload(
        { /* valid input */ } as any,
        { now: new Date('2026-01-01') },
      )
      expect(result.ok).toBe(true)
    })

    it('returns error with invalid input', () => {
      const result = buildCreate<Feature>Payload({ name: '' } as any, { now: new Date() })
      expect(result.ok).toBe(false)
      // TODO: assert specific error code
    })
  })

  describe('can<Feature>', () => {
    it('allows owners to delete', () => expect(can<Feature>('owner', 'delete')).toBe(true))
    it('denies viewers from deleting', () => expect(can<Feature>('viewer', 'delete')).toBe(false))
    it('allows all roles to read', () => {
      for (const role of ['owner', 'admin', 'member', 'viewer'] as const) {
        expect(can<Feature>(role, 'read')).toBe(true)
      }
    })
  })
})
```

**Generate**: `apps/api/test/<feature-kebab>/dal.test.ts` _(skip if `--skip-tests`)_

```ts
// apps/api/test/<feature-kebab>/dal.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'bun:test'
// Uses Testcontainers for ephemeral Postgres — no shared test DB

describe('<Feature> DAL', () => {
  // TODO: set up TestContainer Postgres + apply migrations

  it('returns null for non-existent id', async () => {
    // const row = await get<Feature>ById('00000000-0000-0000-0000-000000000000')
    // expect(row).toBeNull()
  })

  it('cross-org isolation: user of org A cannot see org B data', async () => {
    // Create record in org A, query with org B session → expect null / FORBIDDEN
  })

  it('no session → throws UNAUTHORIZED', async () => {
    // mock getSession() to return null
    // await expect(get<Feature>ById('...')).rejects.toThrow('UNAUTHORIZED')
  })
})
```

**Generate**: `apps/web/tests/e2e/<feature-kebab>/happy.spec.ts` _(skip if `--skip-tests`)_

```ts
// apps/web/tests/e2e/<feature-kebab>/happy.spec.ts
import { test, expect } from '@playwright/test'

// Use pre-authenticated storage state — no re-login per test
test.use({ storageState: 'tests/e2e/.auth/member.json' })

test('create <feature> and verify it appears in the list', async ({ page }) => {
  await page.goto('/[workspace]/<feature-kebab>')
  // await page.getByRole('button', { name: 'Create <Feature>' }).click()
  // await page.getByLabel('<Feature> name').fill('Test <Feature>')
  // await page.getByRole('button', { name: 'Create <Feature>' }).click()
  // await expect(page.getByText('Test <Feature>')).toBeVisible()
})
```

**Generate**: `apps/web/tests/e2e/<feature-kebab>/isolation.spec.ts` _(tagged @critical)_

```ts
// apps/web/tests/e2e/<feature-kebab>/isolation.spec.ts
// @critical — MUST pass to merge
import { test, expect } from '@playwright/test'

test.use({ storageState: 'tests/e2e/.auth/member.json' })

test('@critical user A sees their own org data', async ({ page }) => {
  await page.goto('/org-a/<feature-kebab>')
  await expect(page).not.toHaveURL('/404')
})

test('@critical user A on org B URL gets 404', async ({ page }) => {
  await page.goto('/org-b/<feature-kebab>')
  await expect(page).toHaveURL('/404')
})

test('@critical user A calling procedure with org B id gets 403', async ({ page }) => {
  // Use page.evaluate or API call to invoke the tRPC procedure with orgId B
  // Expect 403 / FORBIDDEN response
})

test('@critical user A on resource from org B gets 404', async ({ page }) => {
  // Navigate to /org-a/<feature-kebab>/<resource-id-from-org-b>
  await expect(page).toHaveURL('/404')
})
```

**Checklist**:
- [ ] Service tests: 100% branch coverage, no mocks (pure functions)
- [ ] DAL tests: cross-org isolation, no session, suspended org
- [ ] E2E happy path: login → create → assert visible
- [ ] `@critical` isolation.spec.ts: all 4 tenant-isolation assertions
- [ ] No `waitForTimeout` in Playwright — use selectors
- [ ] Tests run in `< 100ms` per service file

---

### Phase 10 — Ship Checklist

```
[ ] Feature branch → draft PR linked to RFC PR
[ ] Feature flag `ff-<feature-kebab>` declared and OFF by default
[ ] drizzle-kit generate + review SQL diff + apply locally
[ ] Rollback plan documented (flag OFF → behavior unchanged)
[ ] bun install && bun run lint && bun run typecheck → green
[ ] bun test apps/api/test/<feature-kebab>/ → green
[ ] @critical isolation tests green (bun run test:e2e --grep @critical)
[ ] PR diff < 600 lines (split if larger)
[ ] PR description complete with screenshots for all 4 UI states
[ ] Conventional Commits title (feat / fix / refactor)
[ ] bun.lockb committed if deps changed
[ ] Infisical secrets registered for new env vars
[ ] .env.example updated
[ ] PR ready for review (1 approver minimum, 2 if billing/auth/security)
```

---

## Security Checklist

```
Auth
  [ ] Session checked in orgScopedProcedure middleware (BetterAuth)
  [ ] Membership checked in DAL before every query
  [ ] organizationId extracted from session — never from procedure input

Input
  [ ] Zod schema attached via .input() — no inline schemas
  [ ] No manual type casting of user input
  [ ] File uploads: size + MIME type validated server-side

Rate limiting
  [ ] ioredis sliding window on userId per procedure

Data
  [ ] Every query filters by eq(table.organizationId, orgId)
  [ ] No raw SQL (drizzle-kit generate only)
  [ ] No SELECT * — explicit column selection
  [ ] Sensitive fields absent from DTO schemas

Output
  [ ] Generic error message to client ("Something went wrong")
  [ ] Full stack logged to GlitchTip + Loki server-side only
  [ ] No internal IDs, emails, secrets in client response

Cache
  [ ] Redis key scoped by orgId: <feature>:org:{orgId}:{id}
  [ ] Invalidated on every mutation via prefix DEL

Secrets
  [ ] New env vars in env.ts + Infisical — never process.env directly
  [ ] No NEXT_PUBLIC_ prefix on private values
```

---

## Post-Scaffold Verification

After generating all files, verify:

1. No `'use client'` in `page.tsx` — all page files are Server Components
2. No `import { db }` in components or pages — every DB query routes through the DAL
3. No `fetch('/api/...')` inside RSC pages — use `createCaller` from `@delta-global/sdk`
4. No `@delta-global/analytics-db` imports in `apps/api` or `apps/web`
5. No raw SQL (`sql\`` template literals outside migration files)
6. No `import "server-only"` missing from DAL files
7. All imports resolve: `bun run typecheck`
8. Feature flag declared and OFF

Output the scaffold summary:

```
## Feature scaffold complete

**Feature**: `<feature-kebab>`
**Description**: `<description>`
**Flag**: `ff-<feature-kebab>` (OFF)

**Files created**:
  packages/shared/src/schemas/<feature-kebab>.ts         ← Zod schemas + DTOs
  packages/db/src/schema/<feature-kebab>.ts              ← Drizzle table
  apps/api/src/dal/<feature-kebab>.ts                    ← DAL (server-only, Redis)
  apps/api/src/services/<feature-kebab>.ts               ← Pure services (Result<T,E>)
  apps/api/src/routers/<feature-kebab>.ts                ← tRPC procedures
  apps/api/src/workers/<feature-kebab>.worker.ts         ← BullMQ worker (if queued)
  apps/web/app/(app)/[workspace]/<feature-kebab>/page.tsx
  apps/web/app/(app)/[workspace]/<feature-kebab>/loading.tsx
  apps/web/app/(app)/[workspace]/<feature-kebab>/error.tsx
  apps/web/components/features/<feature-kebab>/Create<Feature>Form.tsx
  apps/web/components/features/<feature-kebab>/<Feature>List.tsx
  apps/web/components/features/<feature-kebab>/<Feature>ListSkeleton.tsx
  apps/api/test/<feature-kebab>/services.test.ts
  apps/api/test/<feature-kebab>/dal.test.ts
  apps/web/tests/e2e/<feature-kebab>/happy.spec.ts
  apps/web/tests/e2e/<feature-kebab>/isolation.spec.ts   ← @critical

**Verification**:
  bun run typecheck
  bun test apps/api/test/<feature-kebab>/
  bun run test:e2e --grep @critical --grep <feature-kebab>

**Next steps**:
  - Run /speckit.plan <feature-kebab> for a full planning document
  - Run /speckit.scaffold.temporal <feature-kebab> if Temporal workflow needed
  - Run /speckit.analyze to verify RFC ↔ implementation consistency
  - Run /speckit.audit to verify constitution compliance
```

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_feature`. Apply standard hook-processing.
