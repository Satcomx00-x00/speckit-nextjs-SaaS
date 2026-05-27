---
description: "Scaffold a tRPC router for the Delta-Global stack without the full feature scaffold"
---

# speckit.scaffold.trpc

Scaffold a standalone tRPC router for the Delta-Global stack (`apps/api`).
Use this when you need to add procedures to an **existing** feature or create a
**new router stub** without running the full `speckit.feature` scaffold.

**Input**: Feature slug and procedure list: "$ARGUMENTS"

---

## When to use this command

| Scenario | Command |
|---|---|
| New feature — full stack (schema + DAL + services + UI) | `speckit.feature` |
| New router only (schema and DAL already exist) | **`speckit.scaffold.trpc`** ← you are here |
| Add procedures to an existing router | **`speckit.scaffold.trpc`** with `--append` |
| Scaffold DAL without router | `speckit.scaffold.dal` |
| Scaffold RSC page without backend | `speckit.scaffold.route` |

---

## Prerequisites (must exist before scaffolding)

| Artifact | Path | Required by |
|---|---|---|
| Zod contracts | `packages/shared/src/schemas/<feature-name>.ts` | `.input()` / `.output()` types |
| DAL module | `apps/api/src/dal/<feature-name>.ts` | procedure implementations |
| Services module | `apps/api/src/services/<feature-name>.ts` | business logic calls |
| `appRouter` | `apps/api/src/routers/index.ts` | wiring the new router |

If any of these are missing, run `speckit.scaffold.dal` and `speckit.tasks` first.

---

## Output

```
apps/api/src/routers/<feature-name>.ts          ← tRPC router (main output)
apps/api/test/<feature-name>/procedures.test.ts ← test stubs (generated alongside)
```

---

## Router scaffold — `apps/api/src/routers/<feature-name>.ts`

Generate a tRPC router using the following canonical pattern:

```typescript
import { z } from "zod";
import { TRPCError } from "@trpc/server";
import { createTRPCRouter, orgScopedProcedure } from "../trpc";
import {
  Create<Feature>Input,
  Update<Feature>Input,
  Get<Feature>Input,
  List<Feature>Input,
  <Feature>Dto,
  <Feature>ListDto,
  <Feature>ErrorCode,
} from "@delta-global/shared";
import {
  get<Feature>ById,
  list<Feature>s,
  create<Feature>Record,
  update<Feature>Record,
  delete<Feature>Record,
} from "../dal/<feature-name>";
import {
  buildCreate<Feature>Payload,
  can<Feature>,
} from "../services/<feature-name>";
import { flagService } from "../lib/flags";
import { redis } from "../lib/redis";

// ──────────────────────────────────────────────────────────────────
// Rate-limit helper
// ──────────────────────────────────────────────────────────────────
async function checkRateLimit(key: string, limit: number, windowSec: number) {
  const count = await redis.incr(key);
  if (count === 1) await redis.expire(key, windowSec);
  if (count > limit) {
    throw new TRPCError({
      code: "TOO_MANY_REQUESTS",
      message: "Rate limit exceeded. Try again later.",
    });
  }
}

// ──────────────────────────────────────────────────────────────────
// Router
// ──────────────────────────────────────────────────────────────────
export const <featureCamel>Router = createTRPCRouter({

  get: orgScopedProcedure
    .meta({ name: "<feature>.get" })
    .input(Get<Feature>Input)
    .output(<Feature>Dto)
    .query(async ({ ctx, input }) => {
      if (!await flagService.isEnabled("ff-<feature-name>", ctx.organization.id)) {
        throw new TRPCError({ code: "NOT_FOUND" });
      }

      const result = await get<Feature>ById({
        id: input.id,
        organizationId: ctx.organization.id,
        session: ctx.session,
      });

      if (!result.ok) {
        throw new TRPCError({ code: "NOT_FOUND", message: result.error });
      }

      return result.data;
    }),

  list: orgScopedProcedure
    .meta({ name: "<feature>.list" })
    .input(List<Feature>Input)
    .output(<Feature>ListDto)
    .query(async ({ ctx, input }) => {
      if (!await flagService.isEnabled("ff-<feature-name>", ctx.organization.id)) {
        throw new TRPCError({ code: "NOT_FOUND" });
      }

      const result = await list<Feature>s({
        organizationId: ctx.organization.id,
        session: ctx.session,
        cursor: input.cursor,
        limit: input.limit,
      });

      if (!result.ok) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: result.error });
      }

      return result.data;
    }),

  create: orgScopedProcedure
    .meta({ name: "<feature>.create" })
    .input(Create<Feature>Input)
    .output(<Feature>Dto)
    .mutation(async ({ ctx, input }) => {
      if (!await flagService.isEnabled("ff-<feature-name>", ctx.organization.id)) {
        throw new TRPCError({ code: "NOT_FOUND" });
      }

      if (!can<Feature>(ctx.member.role, "create")) {
        throw new TRPCError({ code: "FORBIDDEN", message: "Insufficient permissions." });
      }

      await checkRateLimit(
        `rl:<feature>.create:${ctx.session.user.id}`,
        20,
        60,
      );

      const payload = buildCreate<Feature>Payload(input, { now: new Date() });
      if (!payload.ok) {
        throw new TRPCError({ code: "BAD_REQUEST", message: payload.error });
      }

      const result = await create<Feature>Record({
        ...payload.data,
        organizationId: ctx.organization.id,
        session: ctx.session,
      });

      if (!result.ok) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: result.error });
      }

      return result.data;
    }),

  update: orgScopedProcedure
    .meta({ name: "<feature>.update" })
    .input(Update<Feature>Input)
    .output(<Feature>Dto)
    .mutation(async ({ ctx, input }) => {
      if (!await flagService.isEnabled("ff-<feature-name>", ctx.organization.id)) {
        throw new TRPCError({ code: "NOT_FOUND" });
      }

      if (!can<Feature>(ctx.member.role, "update")) {
        throw new TRPCError({ code: "FORBIDDEN", message: "Insufficient permissions." });
      }

      await checkRateLimit(
        `rl:<feature>.update:${ctx.session.user.id}`,
        30,
        60,
      );

      const result = await update<Feature>Record({
        id: input.id,
        organizationId: ctx.organization.id,
        session: ctx.session,
        data: input,
      });

      if (!result.ok) {
        throw new TRPCError({ code: "NOT_FOUND", message: result.error });
      }

      return result.data;
    }),

  delete: orgScopedProcedure
    .meta({ name: "<feature>.delete" })
    .input(Get<Feature>Input)
    .output(z.void())
    .mutation(async ({ ctx, input }) => {
      if (!await flagService.isEnabled("ff-<feature-name>", ctx.organization.id)) {
        throw new TRPCError({ code: "NOT_FOUND" });
      }

      if (!can<Feature>(ctx.member.role, "delete")) {
        throw new TRPCError({ code: "FORBIDDEN", message: "Insufficient permissions." });
      }

      const result = await delete<Feature>Record({
        id: input.id,
        organizationId: ctx.organization.id,
        session: ctx.session,
      });

      if (!result.ok) {
        throw new TRPCError({ code: "NOT_FOUND", message: result.error });
      }
    }),

});
```

---

## Wire into `appRouter`

After generating the router file, add it to `apps/api/src/routers/index.ts`:

```typescript
import { <featureCamel>Router } from "./<feature-name>";

export const appRouter = createTRPCRouter({
  // ... existing routers ...
  <featureCamel>: <featureCamel>Router,
});
```

Verify wiring with `bun run typecheck` — if the import is broken, the build fails immediately.

---

## Procedure test stubs — `apps/api/test/<feature-name>/procedures.test.ts`

Generate test stubs covering the mandatory cases. Use `bun:test` + Testcontainers:

```typescript
import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { PostgreSqlContainer, StartedPostgreSqlContainer } from "@testcontainers/postgresql";
import { GenericContainer, StartedTestContainer } from "testcontainers";
import { createCallerFactory } from "@trpc/server";
import { appRouter } from "../../src/routers";

// ── Containers ───────────────────────────────────────────────────────────────

let pgContainer: StartedPostgreSqlContainer;
let redisContainer: StartedTestContainer;

beforeAll(async () => {
  pgContainer = await new PostgreSqlContainer().start();
  redisContainer = await new GenericContainer("redis:7-alpine")
    .withExposedPorts(6379)
    .start();
  // run drizzle-kit migrate against pgContainer.getConnectionUri()
}, 60_000);

afterAll(async () => {
  await pgContainer?.stop();
  await redisContainer?.stop();
});

// ── Helpers ───────────────────────────────────────────────────────────────────

const createCaller = createCallerFactory(appRouter);

function makeCtx(overrides?: Partial<typeof baseCtx>) {
  return { ...baseCtx, ...overrides };
}

const baseCtx = {
  session: { user: { id: "user-a", email: "a@example.com" } },
  organization: { id: "org-a" },
  member: { role: "member" as const },
};

// ── Auth ─────────────────────────────────────────────────────────────────────

describe("<feature>.list — auth", () => {
  it("returns UNAUTHORIZED when session is absent", async () => {
    const caller = createCaller(makeCtx({ session: null as any }));
    expect(caller.<featureCamel>.list({ limit: 10 })).rejects.toMatchObject({
      code: "UNAUTHORIZED",
    });
  });

  it("returns FORBIDDEN when org membership is absent", async () => {
    const caller = createCaller(makeCtx({ member: null as any }));
    expect(caller.<featureCamel>.list({ limit: 10 })).rejects.toMatchObject({
      code: "FORBIDDEN",
    });
  });
});

// ── RBAC ──────────────────────────────────────────────────────────────────────

describe("<feature>.create — RBAC", () => {
  it("rejects viewer role", async () => {
    const caller = createCaller(makeCtx({ member: { role: "viewer" } }));
    expect(caller.<featureCamel>.create({ /* valid input */ } as any)).rejects.toMatchObject({
      code: "FORBIDDEN",
    });
  });

  it("allows member role", async () => {
    const caller = createCaller(makeCtx({ member: { role: "member" } }));
    // TODO: replace with valid Create<Feature>Input
    const result = await caller.<featureCamel>.create({ /* valid input */ } as any);
    expect(result.id).toBeDefined();
  });
});

describe("<feature>.delete — RBAC", () => {
  it("rejects member role", async () => {
    const caller = createCaller(makeCtx({ member: { role: "member" } }));
    expect(caller.<featureCamel>.delete({ id: "any" })).rejects.toMatchObject({
      code: "FORBIDDEN",
    });
  });
});

// ── Validation ───────────────────────────────────────────────────────────────

describe("<feature>.create — validation", () => {
  it("returns ZodError on invalid input", async () => {
    const caller = createCaller(makeCtx());
    expect(caller.<featureCamel>.create({} as any)).rejects.toMatchObject({
      code: "BAD_REQUEST",
    });
  });
});

// ── Isolation ─────────────────────────────────────────────────────────────────

describe("<feature>.get — tenant isolation", () => {
  it("cannot read a resource from a different org", async () => {
    // Create a record in org-a, then attempt to read from org-b ctx
    const callerA = createCaller(makeCtx({ organization: { id: "org-a" } }));
    const created = await callerA.<featureCamel>.create({ /* valid */ } as any);

    const callerB = createCaller(makeCtx({ organization: { id: "org-b" } }));
    expect(callerB.<featureCamel>.get({ id: created.id })).rejects.toMatchObject({
      code: "NOT_FOUND",
    });
  });
});

// ── Rate limit ────────────────────────────────────────────────────────────────

describe("<feature>.create — rate limit", () => {
  it("returns TOO_MANY_REQUESTS after N+1 calls within the window", async () => {
    const caller = createCaller(makeCtx());
    const LIMIT = 20;
    const calls = Array.from({ length: LIMIT }, () =>
      caller.<featureCamel>.create({ /* valid */ } as any).catch(() => null),
    );
    await Promise.all(calls);
    expect(caller.<featureCamel>.create({ /* valid */ } as any)).rejects.toMatchObject({
      code: "TOO_MANY_REQUESTS",
    });
  });
});

// ── Cache invalidation ────────────────────────────────────────────────────────

describe("<feature> — cache invalidation", () => {
  it("list cache key is absent after create", async () => {
    const caller = createCaller(makeCtx());
    await caller.<featureCamel>.create({ /* valid */ } as any);
    // TODO: assert redis key `<feature>s:org:org-a` does not exist
  });
});
```

---

## Compliance checklist

After generating the router, verify:

- [ ] Every procedure uses `orgScopedProcedure` — no `publicProcedure` for authenticated routes
- [ ] Every procedure has `.meta({ name: '<feature>.<action>' })` for OTel tracing
- [ ] Every procedure has a feature flag guard (`flagService.isEnabled`)
- [ ] Every mutation has an RBAC check (`can<Feature>(ctx.member.role, action)`)
- [ ] Every mutation has a rate-limit check using ioredis (`rl:<feature>.<action>:{userId}`)
- [ ] `.input()` and `.output()` schemas imported from `@delta-global/shared` — never inlined
- [ ] `organizationId` taken from `ctx.organization.id` — NEVER from `input`
- [ ] Router wired into `appRouter` in `apps/api/src/routers/index.ts`
- [ ] `bun run typecheck` passes
- [ ] Test stubs created at `apps/api/test/<feature-name>/procedures.test.ts`

---

## Hard constraints (violations abort scaffold)

- No `@delta-global/analytics-db` imports
- No raw SQL — DAL uses Drizzle ORM only
- No `z.any()`, `z.unknown()`, `z.record(z.any())` in inline schemas
- No relative cross-workspace imports (`../../packages/...`)
- No `process.env` — secrets via `env.ts` + Infisical
- Hono routes only for webhooks / mobile / streaming — all internal calls use tRPC
