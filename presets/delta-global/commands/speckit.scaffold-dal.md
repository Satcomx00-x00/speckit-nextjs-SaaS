---
description: Scaffold the data-access slice of a Delta-Global feature — DB functions in packages/db/src/<slug>-dal.ts (scope predicate from session claims, projected columns, cursor + id tiebreak), the transport-agnostic service in apps/api/src/services/<slug>.ts that receives db/redis as parameters, cache-tag invalidation, and the integration tests (describeIntegration, @critical isolation) written first.
handoffs:
  - label: Scaffold the GraphQL slice
    agent: speckit.scaffold-graphql
    prompt: Scaffold the SDL, resolver and web operations that call this service.
  - label: Generate feature tasks
    agent: speckit.tasks
    prompt: Generate implementation tasks for the feature that uses these DB functions.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check the DAL and service against the plan for scope predicates, cache invalidation and composition-root compliance.
---

## User Input

```text
$ARGUMENTS
```

Parse from `$ARGUMENTS` (ask once if the entity or its use cases cannot be inferred):

- **slug** (kebab-case) and **entity** (table, snake_case plural)
- **use cases** — one DB function per business use case, not per table (`listReadingListsForOwner`, not `select`)
- **tenancy model** — `{{ var.tenancy_model }}` by default; the plan (§1 / §7) may declare org-scoped instead. Ask if it says neither.
- **cache** — which reads are cached and which writes invalidate them (plan §8)

If `specs/<NNN>-<slug>/plan.md` exists, §1 *Drizzle Schema*, §4 *DAL*, §5 *Services* and §8 *Cache Strategy* are the contract.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing: skip `enabled: false`, skip non-empty `condition`, surface optional hooks, execute mandatory hooks and wait for them.

Read an existing pair before writing, to copy the house style: `packages/db/src/sector-overrides-dal.ts` + `apps/api/src/services/sector-override-crud.ts`, and `apps/api/test/sector-overrides/{dal,authz}.test.ts`.

## Rules this scaffold enforces

| Rule | Why / enforced by |
|---|---|
| All SQL lives in `packages/db` (`<slug>-dal.ts`, exported from `packages/db/src/index.ts`); app code never builds a query | CLAUDE.md *Data Access Layer* |
| DB functions take `db: DbExecutor` as their first parameter (works inside a transaction) | `packages/db/src/client.ts` |
| Every read and write of scoped data carries the scope predicate: `eq(table.{{ var.tenancy_column }}, viewerId)` (owner-scoped) or `eq(table.organizationId, orgId)` (org-scoped), plus any visibility gate (`isPublic`, admin) | Constitution IV — the scope key comes from the session, never from input |
| Project columns explicitly (`select({ id: t.id, … })`); never select a wide table object — the `articles` object drags embedding + content (340.7 KB vs 9.1 KB/page) | use `articleListColumns()` for articles |
| Cursor pagination, ordered by the sort column **plus `id`** as tiebreak; no `OFFSET` | rows repeat or vanish between pages otherwise |
| No N+1: `with` joins or one batched `inArray` fetch | |
| Services (`apps/api/src/services/<slug>.ts`) receive `db` and `redis` **as parameters** (`import type { db as Database } from "../db"`), never value-import `db`, `cache`, `redis-config`, `env`, `auth`, `cache-aside`, `clients/temporal` | `bun run check:composition-root`, depcruise `api-use-cases-transport-agnostic` |
| Business failures are typed error subclasses with a `code`; boundaries return/translate them — never catch-log-swallow | CLAUDE.md *Error Handling* |
| Cached lists store **ordered id arrays**; invalidation goes through `cache-tags.ts` + `invalidateTags()`; a Redis outage degrades to the DB, never fails the call | FR-017; failure-isolation lesson (F-08) |
| Admin DB access goes in `admin-dal.ts`, never imported from the web or the reader path | `scripts/guard-admin-dal-isolation.sh` |
| A new table needs the RLS `--custom` block (see `speckit.feature` Phase 1) | migration 0057 precedent |

## Outline

### 1. Tests first — `apps/api/test/<slug>/`

Create and run them; they must fail before step 2.

`dal.test.ts` — real Postgres (`INTEGRATION_DB_URL`):

```ts
import { afterEach, beforeEach, expect } from "bun:test";
import { createClient, listReadingListsForOwner } from "@delta-global/db";
import { describeIntegration, itIntegration } from "../helpers/integration";
import { seedTwoOwners, type TwoOwnersFixture } from "./fixtures";

describeIntegration("reading-lists DAL", () => {
  const db = createClient(process.env.INTEGRATION_DB_URL as string);
  let fx: TwoOwnersFixture;
  beforeEach(async () => { fx = await seedTwoOwners(db); });
  afterEach(async () => { await fx.cleanup(); });

  itIntegration("isolation — owner B never sees owner A's rows — @critical", async () => {
    const rows = await listReadingListsForOwner(db, fx.ownerB, { first: 50 });
    expect(rows.nodes.map((r) => r.id)).not.toContain(fx.listOfA);
  });

  itIntegration("pagination is stable across ties (id tiebreak)", async () => { /* … */ });
  itIntegration("projects only the listed columns", async () => { /* … */ });
});
```

`services.test.ts` — pure logic with fakes for the injected `redis` (rate-limit / tag stores); no network. `fixtures.ts` seeds **two owners** (Unicode names, max-length values) and cleans up after itself.

Gate integration suites only with `describeIntegration` / `itIntegration` / `requireRedis()`; anything else fails `bun run check:integration-skip`, and under `CI` a skip fails.

### 2. DB functions — `packages/db/src/<slug>-dal.ts`

```ts
import { and, desc, eq, lt, or } from "drizzle-orm";
import type { DbExecutor } from "./client";
import { readingLists } from "./schema/index";

/** Reading lists owned by `ownerId`, newest first (spec NNN, FR-00x). */
export async function listReadingListsForOwner(
  db: DbExecutor,
  ownerId: string,
  page: { readonly first: number; readonly after?: { createdAt: Date; id: string } },
) {
  const t = readingLists;
  const rows = await db
    .select({ id: t.id, name: t.name, createdAt: t.createdAt })
    .from(t)
    .where(
      and(
        eq(t.{{ var.tenancy_column }}, ownerId),
        page.after
          ? or(lt(t.createdAt, page.after.createdAt), and(eq(t.createdAt, page.after.createdAt), lt(t.id, page.after.id)))
          : undefined,
      ),
    )
    .orderBy(desc(t.createdAt), desc(t.id))
    .limit(page.first + 1);
  return { nodes: rows.slice(0, page.first), hasMore: rows.length > page.first };
}
```

Writes return the projected row; constraint violations are translated to a typed error in the service, never leaked as driver text. Export every function from `packages/db/src/index.ts`. Confirm an index serves each predicate + order (`({{ var.tenancy_column_snake }}, created_at desc, id)`), and say which in the JSDoc.

### 3. Service — `apps/api/src/services/<slug>.ts`

```ts
import { listReadingListsForOwner } from "@delta-global/db";
import type { db as Database } from "../db";
import type { TagStore } from "../cache-util";

type Db = typeof Database;

export class ReadingListError extends Error {
  constructor(readonly code: "NAME_TAKEN" | "LIMIT_REACHED" | "NOT_FOUND", message: string) {
    super(message);
  }
}

export async function listReadingLists(db: Db, redis: TagStore, viewerId: string, args: { first: number; after: string | null }) {
  // decode cursor, clamp `first`, call the DB function, optionally serve the id list from cache
}
```

Authorization decisions live here (`can<Feature>(role, action)` or an ownership check), not in the resolver. A flag-gated behaviour asks `is<Pascal>Enabled()` from `services/<slug>-flag.ts`.

### 4. Verify

```bash
bun test apps/api/test/<slug>
bun run check:composition-root && bun run depcruise
bun run check:integration-skip
bun run typecheck
```

Report files created, the scope predicate used by each function, the index serving it, and the command results.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
