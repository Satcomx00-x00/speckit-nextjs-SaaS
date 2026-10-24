---
description: Scaffold a GraphQL slice for the Delta-Global API — SDL in packages/graphql/schema with field-level auth directives (@public/@auth/@selfOnly, @audited on admin mutations, @cost on expensive fields), a thin resolver over apps/api/src/services, the web operation document, codegen, and the resolver/authz tests with @critical naming. Replaces the removed tRPC scaffold.
handoffs:
  - label: Scaffold the DB functions
    agent: speckit.scaffold.dal
    prompt: Scaffold the packages/db DAL functions and the service this resolver calls.
  - label: Scaffold the route
    agent: speckit.scaffold.route
    prompt: Scaffold the RSC page and client seam that consume these operations.
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check the new SDL and resolvers against the plan's GraphQL Operations and RBAC Matrix sections.
---

## User Input

```text
$ARGUMENTS
```

Parse from `$ARGUMENTS` (ask once if the operation list cannot be inferred):

| Token | Meaning | Example |
|---|---|---|
| area / slug | kebab-case feature slug | `reading-lists` |
| operations | queries / mutations with args and return type | `readingLists(first, after): ReadingListConnection` |
| audience per field | `@public` · `@auth(role: MEMBER\|ADMIN)` · `@selfOnly` | owner data → `@selfOnly` |
| admin? | is any mutation in the admin realm | → `@audited(action: "<area>.<verb>")` |
| flag | flag key, plain kebab-case, no `ff-` prefix | `reading-lists` |

If a plan exists (`specs/<NNN>-<slug>/plan.md` §3 *GraphQL Operations*, §7 *RBAC Matrix*), it is the contract — scaffold exactly what it lists and stop on a mismatch rather than inventing.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing: skip `enabled: false`, skip non-empty `condition`, surface optional hooks, execute mandatory hooks and wait for them.

Read `CLAUDE.md` (*Forbidden Patterns*), `packages/graphql/schema/00-directives.graphql` and `apps/api/src/graphql/guards.ts` before writing anything. If `apps/api/src/router/` or any `@trpc/*` import exists, stop: `check:trpc-removal` must stay at zero.

## Rules this scaffold enforces

- GraphQL at `/graphql` is the **only** API surface. No Hono route for app data (standing exceptions only: `GET /public/share/:token`, `POST /webhooks/stripe`). No Server Actions.
- **Every field** has exactly one of `@public` (any *authenticated* caller — ADR-0027), `@auth(role: MEMBER|ADMIN|SUPERADMIN)`, `@selfOnly`. An unannotated field is denied at runtime **and** fails `bun run check:field-auth`.
- **Every admin-realm mutation** has `@audited(action: "<area>.<verb>", reason: REQUIRED)` and declares `reason: String` as a **top-level argument** — never inside an input object (F-50: the mutation could never succeed). `bun run check:field-audit`.
- Fields whose cost scales with arguments or list size declare `@cost(weight: N, multipliers: ["first"])`.
- SDL enums are SCREAMING_CASE and the resolver returns the NAME (`"PIN"`), never a lowercase DTO value.
- Resolvers are **thin**: parse args with the Zod schema from `{{ var.package_scope }}/shared`, take the viewer from `requireViewer(ctx)` / `viewerIsAdmin(ctx)` (`apps/api/src/graphql/guards.ts`), call **one** service in `apps/api/src/services/`, map the result. The scope key ({{ var.tenancy_column }} for the {{ var.tenancy_model }} model) comes from the context, **never** from an argument.
- Errors: services throw typed subclasses (`class XError extends Error { code = "X" }`); the resolver maps them to `GraphQLError` with `extensions.code` (`BAD_USER_INPUT`, `FORBIDDEN`, `NOT_FOUND`, a domain code). Never surface a raw DB/driver message to a reader (F-41).
- Lists: connection with cursor + an `id` tiebreak; the Redis cache stores **ordered id arrays**, never payloads (keys on args × selection are unbounded — FR-017).
- Flag-gated fields check `is<Pascal>Enabled()` (`apps/api/src/services/<slug>-flag.ts`) in the service. OFF must reproduce today's behaviour exactly; a flag never gates whether the graph serves at all.

## Outline

### 1. SDL — `packages/graphql/schema/NN-<area>.graphql`

Extend the existing area file if one fits (`10-reader`, `20-viewer`, `30-sources`, `40-notifications`, `45-sectors`, `50-billing`, `50-platform`, `70-schedules`, `80-admin-console`, `90-admin-operations`, `95-admin-articles`, `96-admin-billing`); create a new `NN-` file only for a genuinely new area, numbered to sit with its neighbours (admin areas ≥ 80).

```graphql
"""A user-owned reading list (spec NNN)."""
type ReadingList {
  id: ID! @selfOnly
  name: String! @selfOnly
  articleCount: Int! @selfOnly
  createdAt: DateTime! @selfOnly
}

type ReadingListConnection {
  nodes: [ReadingList!]! @selfOnly
  nextCursor: String @selfOnly
}

enum ReadingListErrorCode { NAME_TAKEN LIMIT_REACHED }

extend type Query {
  readingLists(first: Int = 20, after: String): ReadingListConnection!
    @selfOnly @cost(weight: 1, multipliers: ["first"])
}

extend type Mutation {
  createReadingList(name: String!): ReadingList! @selfOnly
}

# Admin realm — audited, reason top-level:
extend type Mutation {
  adminDeleteReadingList(id: ID!, reason: String!): Boolean!
    @auth(role: ADMIN) @audited(action: "reading-lists.delete", reason: REQUIRED)
}
```

Write a `"""docstring"""` on every type and on any field whose meaning is not obvious — the SDL is the wire contract (Constitution I).

### 2. Zod — `packages/shared/src/schemas/<slug>.ts`

Input schemas for every argument set (`CreateReadingListInput`), output DTO types via `z.infer`, error codes as an `as const` object + union. No `z.any()` / `z.unknown()` passthroughs. Export from `packages/shared/src/index.ts`. If `apps/workers` reads the shape, run `bun run gen:py-models`.

### 3. Resolver — `apps/api/src/graphql/resolvers/<slug>.ts`

```ts
import { CreateReadingListInput } from "@delta-global/shared";
import { GraphQLError } from "graphql";
import type { GraphQLContext } from "../context";
import { requireViewer } from "../guards";
import { createReadingList, listReadingLists, ReadingListError } from "../../services/reading-lists";

function rethrowAsGraphQLError(err: unknown): never {
  if (err instanceof ReadingListError) {
    throw new GraphQLError(err.message, { extensions: { code: err.code } });
  }
  throw err; // unexpected: the error plugin reports it and masks the message
}

export const readingListResolvers = {
  Query: {
    readingLists: (_p: unknown, args: { first: number; after: string | null }, ctx: GraphQLContext) =>
      listReadingLists(ctx.db, ctx.redis, requireViewer(ctx), args).catch(rethrowAsGraphQLError),
  },
  Mutation: {
    createReadingList: async (_p: unknown, args: { name: string }, ctx: GraphQLContext) => {
      const input = CreateReadingListInput.safeParse(args);
      if (!input.success) {
        throw new GraphQLError("Invalid input", { extensions: { code: "BAD_USER_INPUT" } });
      }
      return createReadingList(ctx.db, ctx.redis, requireViewer(ctx), input.data).catch(rethrowAsGraphQLError);
    },
  },
};
```

Register it in `apps/api/src/graphql/resolvers/index.ts` (merged by `merge.ts`). Batched field reads go through a DataLoader in `apps/api/src/graphql/loaders/` — no N+1.

### 4. Web operations — `apps/web/src/graphql/<slug>.graphql`

One named operation per use (`query ReadingLists`, `mutation CreateReadingList`). Select only the fields the UI renders. Then:

```bash
bun --filter='@delta-global/web' codegen          # regenerates packages/graphql/src/generated (persisted documents)
bun --filter='@delta-global/web' codegen:check    # must be clean before commit
```

Consumers: RSC through `apps/web/src/lib/server/<slug>.ts` (`import "server-only"`, `query()` from `lib/apollo/rsc.ts`); client through `useQuery`/`useMutation` inside `(dashboard)` or `(admin)/admin`, or imperatively through the seam `apps/web/src/lib/<slug>-api.ts` via `getBrowserClient()`. Never `new ApolloClient(`. Singleton results need `keyFields` in the cache policy.

### 5. Tests first — `apps/api/test/<slug>/`

Write and run these **before** the resolver body (they must fail first):

| File | Covers |
|---|---|
| `resolvers.test.ts` | arg parsing → `BAD_USER_INPUT`; typed error codes; enum NAME serialisation; no raw DB text in `message` |
| `authz.test.ts` | `describeIntegration("<slug> authorisation — @critical", …)`: owner reads/mutates own rows; another user gets empty/`FORBIDDEN`/`NOT_FOUND`; non-admin refused on `@auth(role: ADMIN)`; scope key ignored if smuggled in args |
| `audit.test.ts` (admin mutations) | an `audit_log` row per call with action + reason; missing reason refused; the mutation actually succeeds with a reason |
| `graphql-surface.test.ts` (optional) | the SDL fields exist with the expected directive |

Integration suites use `describeIntegration` / `itIntegration` (`apps/api/test/helpers/integration.ts`) and `requireRedis()` — any other skip idiom fails `check:integration-skip`. Never `quit()` the shared Redis client.

### 6. Verify

```bash
bun run check:field-auth && bun run check:field-audit
bun --filter='@delta-global/web' codegen:check
bun run typecheck
bun test apps/api/test/<slug>
bun run check:integration-skip && bun run check:trpc-removal
```

Report the files created, the directive on every new field (a table), and the command results. Any failing check is reported, not worked around.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
