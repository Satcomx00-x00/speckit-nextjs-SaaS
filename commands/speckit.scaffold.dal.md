---
description: Scaffold a Delta-Global DAL module. Generates apps/api/src/dal/<feature>.ts with import "server-only", BetterAuth session check, organizationId tenant-scoping on every query, ioredis caching, Result<T,E> envelope, and Drizzle stubs — all compliant with the stack conventions.
handoffs:
  - label: Scaffold the tRPC router
    agent: speckit.scaffold.route
    prompt: Scaffold the tRPC router and RSC page that consumes this DAL.
  - label: Generate feature tasks
    agent: speckit.tasks
    prompt: Generate implementation tasks for the feature that uses this DAL.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check the DAL against the RFC for organizationId scoping, cache invalidation, and hard constraint compliance.
---

## User Input

```text
$ARGUMENTS
```

Parse from `$ARGUMENTS`:

| Token | Meaning | Default |
|---|---|---|
| First positional arg | Feature/entity name (kebab-case or PascalCase accepted) | required |
| `--methods <list>` | Comma-separated method verbs | `get,list,create,update,delete` |
| `--schema <path>` | Path to existing Zod schema file to import | auto-detected in `packages/shared/src/schemas/` |
| `--id-type <type>` | Primary key type (`uuid` or `cuid2`) | `uuid` |
| `--no-result-envelope` | Return raw type instead of `Result<T,E>` | use envelope |
| `--soft-delete` | Generate soft-delete pattern instead of hard delete | hard delete |
| `--no-cache` | Skip Redis cache stubs | generate cache |

If the feature name is missing, ask for it before proceeding.

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing.

Verify `apps/api/src/dal/` exists. If not, warn and ask whether to create the directory or abort.

---

## Scaffold Steps

### 1. Normalize entity name

Convert the input to:

| Form | Example |
|---|---|
| `FeatureName` — PascalCase | `PostPublishing` |
| `featureName` — camelCase | `postPublishing` |
| `feature-name` — kebab-case | `post-publishing` |
| `feature_snake` — snake_case | `post_publishing` |

### 2. Resolve output path

Output file: `apps/api/src/dal/<feature-name>.ts`

If the file already exists, warn and ask whether to overwrite, skip, or abort.

### 3. Resolve Zod schema import

If `--schema <path>` was provided, import from that path.
Otherwise, look for `packages/shared/src/schemas/<feature-name>.ts`.
If neither exists, add a `// TODO` stub and continue.

### 4. Write the DAL module

```ts
// apps/api/src/dal/<feature-name>.ts
import 'server-only'
import { cache } from 'react'
import { eq, and, desc, lt } from 'drizzle-orm'
import { db } from '@delta-global/db'
import { <featureSnake> } from '@delta-global/db/schema'
import { redis } from '@/lib/redis'
import { getSession, assertMembership } from '@/lib/auth'
import type { List<Feature>Input } from '@delta-global/shared'

// ─── Cache keys ────────────────────────────────────────────────────────────────
// Pattern enforced by stack: <feature>:org:{orgId}:{id}
// Invalidate on every mutation via prefix DEL.

const cacheKey = {
  one:  (orgId: string, id: string) => `<feature>:org:${orgId}:${id}`,
  list: (orgId: string)             => `<feature>s:org:${orgId}`,
}

const CACHE_TTL_SECONDS = 300 // 5 minutes

// ─── Reads ─────────────────────────────────────────────────────────────────────

/**
 * Fetch a single <Feature> by ID, scoped to the authenticated user's organization.
 * Wrapped with React cache() for intra-request dedup.
 * Redis-cached for ${CACHE_TTL_SECONDS}s.
 */
export const get<Feature>ById = cache(async (id: string): Promise<Result<<Feature>DTO | null>> => {
  const session = await getSession()
  if (!session) return { ok: false, error: 'UNAUTHORIZED' }

  const orgId = session.activeOrganizationId
  const membership = await assertMembership(session.user.id, orgId)
  if (!membership) return { ok: false, error: 'FORBIDDEN' }

  const cached = await redis.get(cacheKey.one(orgId, id))
  if (cached) return { ok: true, data: JSON.parse(cached) as <Feature>DTO }

  const row = await db.query.<featureSnake>.findFirst({
    where: and(
      eq(<featureSnake>.id, id),
      eq(<featureSnake>.organizationId, orgId), // ← tenant scope: always required
    ),
    columns: {
      // Explicit column selection — never SELECT *
      // Exclude sensitive fields: tokens, hashes, secrets
      id: true,
      organizationId: true,
      createdAt: true,
      updatedAt: true,
      // TODO: add business columns
    },
  })

  if (!row) return { ok: true, data: null }

  const dto = to<Feature>DTO(row)
  await redis.setex(cacheKey.one(orgId, id), CACHE_TTL_SECONDS, JSON.stringify(dto))
  return { ok: true, data: dto }
})

/**
 * List <Feature>s for the current organization with cursor-based pagination.
 */
export const list<Feature>s = cache(async (input: List<Feature>Input): Promise<Result<<Feature>ListDTO>> => {
  const session = await getSession()
  if (!session) return { ok: false, error: 'UNAUTHORIZED' }

  const orgId = session.activeOrganizationId
  const membership = await assertMembership(session.user.id, orgId)
  if (!membership) return { ok: false, error: 'FORBIDDEN' }

  // Use list cache only on the first page (no cursor)
  if (!input.cursor) {
    const cached = await redis.get(cacheKey.list(orgId))
    if (cached) return { ok: true, data: JSON.parse(cached) as <Feature>ListDTO }
  }

  // Whitelisted sort columns — never interpolate user-supplied column names
  const sortColumn = <featureSnake>.createdAt // TODO: map input.sortBy to actual column

  const rows = await db.query.<featureSnake>.findMany({
    where: and(
      eq(<featureSnake>.organizationId, orgId), // ← tenant scope: always required
      input.cursor ? lt(<featureSnake>.createdAt, new Date(input.cursor)) : undefined,
    ),
    orderBy: desc(sortColumn),
    limit: input.limit + 1, // +1 to detect if there is a next page
    columns: {
      id: true,
      organizationId: true,
      createdAt: true,
      updatedAt: true,
      // TODO: add business columns
    },
  })

  const hasMore = rows.length > input.limit
  const items = (hasMore ? rows.slice(0, -1) : rows).map(to<Feature>DTO)
  const result: <Feature>ListDTO = {
    items,
    nextCursor: hasMore ? items.at(-1)?.createdAt ?? null : null,
    total: items.length,
  }

  if (!input.cursor) {
    await redis.setex(cacheKey.list(orgId), CACHE_TTL_SECONDS, JSON.stringify(result))
  }

  return { ok: true, data: result }
})

// ─── Writes ────────────────────────────────────────────────────────────────────

/**
 * Insert a new <Feature>, scoped to the given organizationId.
 * organizationId is always passed explicitly — never from user input.
 */
export async function create<Feature>Record(
  data: Omit<New<Feature>, 'id' | 'createdAt' | 'updatedAt'>,
  organizationId: string,
): Promise<Result<<Feature>DTO>> {
  const [row] = await db
    .insert(<featureSnake>)
    .values({ ...data, organizationId })
    .returning()
  if (!row) return { ok: false, error: '<FEATURE>_INSERT_FAILED' }
  await invalidate<Feature>Cache(organizationId)
  return { ok: true, data: to<Feature>DTO(row) }
}

/**
 * Update fields on an existing <Feature>.
 * Ownership enforced in the WHERE clause — not separately checked.
 */
export async function update<Feature>Record(
  id: string,
  organizationId: string,
  data: Partial<Omit<New<Feature>, 'id' | 'organizationId' | 'createdAt' | 'updatedAt'>>,
): Promise<Result<<Feature>DTO>> {
  const [row] = await db
    .update(<featureSnake>)
    .set({ ...data, updatedAt: new Date() })
    .where(
      and(
        eq(<featureSnake>.id, id),
        eq(<featureSnake>.organizationId, organizationId), // ← ownership in query
      ),
    )
    .returning()
  if (!row) return { ok: false, error: '<FEATURE>_NOT_FOUND' }
  await invalidate<Feature>Cache(organizationId, id)
  return { ok: true, data: to<Feature>DTO(row) }
}

/**
 * Delete a <Feature>. Ownership enforced in WHERE clause.
 * Use soft-delete pattern if the domain requires an audit trail.
 */
export async function delete<Feature>Record(
  id: string,
  organizationId: string,
): Promise<Result<void>> {
  await db
    .delete(<featureSnake>)
    .where(
      and(
        eq(<featureSnake>.id, id),
        eq(<featureSnake>.organizationId, organizationId), // ← ownership in query
      ),
    )
  await invalidate<Feature>Cache(organizationId, id)
  return { ok: true, data: undefined }
}

// ─── Cache invalidation ────────────────────────────────────────────────────────

async function invalidate<Feature>Cache(orgId: string, id?: string): Promise<void> {
  const pattern = `<feature>*:org:${orgId}*`
  const keys = await redis.keys(pattern)
  if (keys.length > 0) await redis.del(...keys)
}

// ─── Mapper ────────────────────────────────────────────────────────────────────

/** Convert a DB row to the public DTO. Never expose raw DB rows to callers. */
function to<Feature>DTO(row: <Feature>): <Feature>DTO {
  return {
    id:             row.id,
    organizationId: row.organizationId,
    createdAt:      row.createdAt.toISOString(),
    updatedAt:      row.updatedAt.toISOString(),
    // TODO: map business columns
  }
}

// ─── Result type ──────────────────────────────────────────────────────────────

type Result<T, E extends string = string> =
  | { ok: true;  data: T }
  | { ok: false; error: E }
```

#### `--methods` filtering

Only generate method stubs listed in `--methods`. If `--methods get,list` is passed, omit `create`, `update`, `delete` stubs.

#### `--no-result-envelope`

Replace `Promise<Result<T>>` with `Promise<T | null>` (for get) and `Promise<T>` (for writes). Remove the `Result` type. Cache and mapper still apply.

#### `--soft-delete`

Replace `delete<Feature>Record` with a soft-delete that sets `deletedAt = new Date()` instead of issuing `db.delete(...)`. Add `isNull(<featureSnake>.deletedAt)` to every `where` clause in reads.

#### `--no-cache`

Remove all Redis imports, `cacheKey`, `CACHE_TTL_SECONDS`, and `invalidate<Feature>Cache`. Remove the cache lookup/set blocks from reads. Writes still call the DB directly.

### 5. Print the scaffold summary

```
## DAL scaffold complete

**Entity**: `<FeatureName>`
**File**: `apps/api/src/dal/<feature-name>.ts`

**Includes**:
- `import 'server-only'`          ← DAL_MISSING_SERVER_ONLY satisfied
- BetterAuth session + membership ← UNAUTHORIZED / FORBIDDEN enforced
- `organizationId` on every query ← MISSING_ORG_SCOPE satisfied
- `Result<T, E>` envelope         ← typed errors, no raw throws to callers
- ioredis cache: key pattern `<feature>:org:{orgId}:{id}`, TTL 5m
- React `cache()` for intra-request dedup
- Explicit column selection        ← no SELECT *
- Sensitive fields excluded from DTO

**Methods generated**: <method list>

**TODOs** (search `// TODO` in the generated file):
- [ ] Add business columns to column selection and DTO mapper
- [ ] Map `input.sortBy` to actual Drizzle column in list function
- [ ] Implement `to<Feature>DTO` mapper fully

**Next steps**:
- Run `/speckit.scaffold.route <feature-name>` to scaffold the tRPC router and page
- Run `/speckit.analyze` to verify organizationId scoping and cache tag coverage
- Run `bun run typecheck` to confirm the file compiles
```

### 6. Compliance check

Before writing the file, verify:

1. `import 'server-only'` is the **first non-comment line**.
2. `organizationId` is a required (non-optional) parameter on every write function.
3. Every `db.query.*` or `db.select()` call includes `eq(<featureSnake>.organizationId, orgId)` in `where`.
4. No `SELECT *` — every `columns` object is explicit.
5. No sensitive fields (`passwordHash`, `token`, `secret`, `apiKey`) in the DTO mapper return value.
6. No raw SQL string interpolation.
7. Cache key follows the `<feature>:org:{orgId}:{id}` pattern.

If any check fails, do not write the file — report the issue and ask the user to clarify before continuing.

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
