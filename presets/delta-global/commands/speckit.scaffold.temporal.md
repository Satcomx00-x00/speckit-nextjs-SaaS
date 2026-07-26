---
description: Scaffold a Temporal workflow and its activities for the Delta-Global stack. Generates the workflow file, activities file, and bun:test tests using TestWorkflowEnvironment with time skipping. Enforces determinism rules (no Date.now, no Math.random, no direct I/O in workflow code) and idempotent workflow IDs.
handoffs:
  - label: Generate tasks for workflow
    agent: speckit.tasks
    prompt: Generate implementation tasks for the Temporal workflow scaffolded for this feature. Include retry policies, timeout values, and activity implementations.
  - label: Analyze workflow consistency
    agent: speckit.analyze
    prompt: Cross-check the Temporal workflow against the RFC background-jobs section. Verify idempotency, activity isolation, and test coverage.
---

## User Input

```text
$ARGUMENTS
```

Parse from `$ARGUMENTS`:

| Token | Meaning | Default |
|---|---|---|
| First positional arg | Feature/workflow name (kebab-case) | required |
| `--trigger <type>` | What starts the workflow: `trpc`, `bullmq`, `cron`, `webhook` | `trpc` |
| `--activities <list>` | Comma-separated activity names (camelCase verbs) | inferred from feature name |
| `--retry <N>` | Max retry attempts on activities | `3` |
| `--schedule-to-close <duration>` | Overall workflow timeout | `1h` |
| `--start-to-close <duration>` | Per-activity timeout | `30s` |
| `--heartbeat <duration>` | Heartbeat interval for long activities | `10s` |
| `--skip-tests` | Skip TestWorkflowEnvironment tests | generate tests |
| `--dry-run` | Print file contents instead of writing | write files |

If the feature name is missing, ask for it before proceeding.

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing.

Verify `packages/temporal-workflows/` exists. If not, warn the user and ask whether to create the package structure or abort.

---

## Scaffold Steps

### 1. Normalize names

From the feature name (e.g. `post-publishing`):

| Form | Example |
|---|---|
| `FeatureName` — PascalCase | `PostPublishing` |
| `featureName` — camelCase | `postPublishing` |
| `feature-name` — kebab-case | `post-publishing` |
| `FEATURE_NAME` — SCREAMING_SNAKE | `POST_PUBLISHING` |
| Workflow type name | `PostPublishingWorkflow` |
| Default workflow ID template | `post-publishing-{id}` |

### 2. Resolve output paths

```
packages/temporal-workflows/src/workflows/<feature-name>.ts    ← workflow
packages/temporal-workflows/src/activities/<feature-name>.ts   ← activities
packages/temporal-workflows/test/<feature-name>.test.ts        ← tests
packages/temporal-workflows/src/workflows/index.ts             ← barrel (add export)
packages/temporal-workflows/src/activities/index.ts            ← barrel (add export)
```

If files already exist, warn and ask whether to overwrite, skip, or abort.

### 3. Write the workflow file

```ts
// packages/temporal-workflows/src/workflows/<feature-name>.ts
import {
  proxyActivities,
  defineSignal,
  defineQuery,
  setHandler,
  workflowInfo,
  sleep,
  condition,
  log,
} from '@temporalio/workflow'
import type * as activities from '../activities/<feature-name>'

// ─── Activity proxy ───────────────────────────────────────────────────────────
// Activities are proxied — the workflow runtime handles retries and timeouts.
// DO NOT import activity implementations directly here (non-determinism risk).

const {
  // <activityName>,
  // <activityName2>,
} = proxyActivities<typeof activities>({
  startToCloseTimeout: '<start-to-close>',
  scheduleToCloseTimeout: '<schedule-to-close>',
  heartbeatTimeout: '<heartbeat>',
  retry: {
    maximumAttempts: <retry>,
    initialInterval: '1s',
    backoffCoefficient: 2,
    maximumInterval: '30s',
    nonRetryableErrorTypes: [
      // Add error class names that should NOT be retried (e.g. validation errors)
    ],
  },
})

// ─── Signals ─────────────────────────────────────────────────────────────────
// Signals allow external code to push data into a running workflow.
// export const cancelSignal = defineSignal('cancel')

// ─── Queries ─────────────────────────────────────────────────────────────────
// Queries allow external code to read state from a running workflow (sync).
// export const statusQuery = defineQuery<string>('status')

// ─── Input / Output types ────────────────────────────────────────────────────

export interface <FeatureName>WorkflowInput {
  organizationId: string
  // TODO: add required input fields
}

export interface <FeatureName>WorkflowOutput {
  // TODO: add output fields
}

// ─── Workflow ─────────────────────────────────────────────────────────────────
//
// DETERMINISM RULES — the Temporal runtime replays workflow history to recover
// state. Any non-deterministic call crashes the replay:
//   ✗ Date.now() / new Date()       → use workflow.now() instead
//   ✗ Math.random()                 → pass rng seed via input or generate in activity
//   ✗ fetch / axios / db / redis    → must be in an activity
//   ✗ crypto.randomUUID()           → generate in activity, pass via signal/return
//   ✗ console.log()                 → use log.info() from @temporalio/workflow
//   ✓ sleep() / condition()         → safe workflow timers
//   ✓ setHandler() for signals      → safe
//   ✓ proxyActivities()             → safe (deterministic proxy)

export async function <featureName>Workflow(
  input: <FeatureName>WorkflowInput,
): Promise<<FeatureName>WorkflowOutput> {
  const { workflowId } = workflowInfo()
  log.info('<feature-name> workflow started', { workflowId, organizationId: input.organizationId })

  // ── Signal handlers (register before any await) ───────────────────────────
  // let cancelled = false
  // setHandler(cancelSignal, () => { cancelled = true })

  // ── Query handlers (register before any await) ────────────────────────────
  // let status = 'pending'
  // setHandler(statusQuery, () => status)

  // ── Step 1 ────────────────────────────────────────────────────────────────
  // status = 'step-1'
  // const result = await <activityName>({ organizationId: input.organizationId })

  // ── Step 2 (conditional) ──────────────────────────────────────────────────
  // if (result.requiresApproval) {
  //   // Wait up to 48h for an external signal before timing out
  //   const approved = await condition(() => approved || cancelled, '48h')
  //   if (!approved) throw ApplicationFailure.create({ message: 'APPROVAL_TIMEOUT', nonRetryable: true })
  // }

  // ── Step 3 ────────────────────────────────────────────────────────────────
  // status = 'complete'
  log.info('<feature-name> workflow complete', { workflowId })

  return {
    // TODO: return output
  }
}
```

### 4. Write the activities file

```ts
// packages/temporal-workflows/src/activities/<feature-name>.ts
import { Context } from '@temporalio/activity'
import { ApplicationFailure } from '@temporalio/common'

// Activities isolate ALL external effects: DB writes, HTTP calls, emails,
// queue publishes, file I/O. They can use Date.now, Math.random, and I/O
// freely — they are NOT replayed by the runtime.
//
// Activity rules:
//   ✓ Call Context.current().heartbeat() in long-running loops
//   ✓ Check Context.current().cancelled for cancellation
//   ✓ Throw ApplicationFailure.create({ nonRetryable: true }) for permanent errors
//   ✓ Import db, redis, fetch, etc. freely here

// ─── Input / Output types ─────────────────────────────────────────────────────

export interface <ActivityName>Input {
  organizationId: string
  // TODO: add activity-specific fields
}

export interface <ActivityName>Output {
  // TODO: add output fields
}

// ─── Activities ───────────────────────────────────────────────────────────────

/**
 * TODO: describe what this activity does and what external systems it touches.
 * External effects: <list DB tables, HTTP endpoints, queues>
 */
export async function <activityName>(
  input: <ActivityName>Input,
): Promise<<ActivityName>Output> {
  const ctx = Context.current()

  try {
    // Long-running activities should heartbeat regularly so Temporal knows
    // they are still alive. Heartbeat also carries cancellation signals.
    // await someLoop(..., async (item) => {
    //   ctx.heartbeat({ processed: item.id })
    //   if (ctx.cancelled) break
    // })

    // TODO: implement activity
    // import db from '@delta-global/db' — drizzle client
    // const result = await db.insert(someTable).values({ ... }).returning()

    return {
      // TODO: return output
    }
  } catch (err) {
    // Distinguish permanent errors (don't retry) from transient ones (do retry)
    if (err instanceof SomeValidationError) {
      throw ApplicationFailure.create({
        message: err.message,
        nonRetryable: true,
      })
    }
    // Re-throw transient errors — Temporal will retry per the retry policy
    throw err
  }
}

// Add more activity functions below following the same pattern.
// Each activity = one external side-effect boundary.
```

### 5. Write the test file (skip if `--skip-tests`)

```ts
// packages/temporal-workflows/test/<feature-name>.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'bun:test'
import { TestWorkflowEnvironment } from '@temporalio/testing'
import { Worker } from '@temporalio/worker'
import { <featureName>Workflow } from '../src/workflows/<feature-name>'
import * as activities from '../src/activities/<feature-name>'

let testEnv: TestWorkflowEnvironment

beforeAll(async () => {
  // TestWorkflowEnvironment starts a local Temporal server in-process.
  // Time skipping is enabled by default — sleep() and condition() timeouts
  // resolve instantly in tests unless you call testEnv.sleep() to advance time.
  testEnv = await TestWorkflowEnvironment.createTimeSkipping()
})

afterAll(async () => {
  await testEnv?.teardown()
})

// ─── Helper ───────────────────────────────────────────────────────────────────

async function runWorkflow(
  input: Parameters<typeof <featureName>Workflow>[0],
  activityOverrides: Partial<typeof activities> = {},
) {
  const { client, nativeConnection } = testEnv

  const worker = await Worker.create({
    connection: nativeConnection,
    taskQueue: 'test-<feature-name>',
    workflowsPath: require.resolve('../src/workflows/<feature-name>'),
    activities: { ...activities, ...activityOverrides },
  })

  return worker.runUntil(
    client.workflow.execute(<featureName>Workflow, {
      taskQueue: 'test-<feature-name>',
      workflowId: `test-<feature-name>-${Date.now()}`,
      args: [input],
    }),
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('<FeatureName> workflow', () => {
  it('completes successfully on happy path', async () => {
    const result = await runWorkflow({ organizationId: 'org-1' })
    expect(result).toBeDefined()
    // TODO: assert specific output fields
  })

  it('is idempotent — second execution with same input produces same outcome', async () => {
    const input = { organizationId: 'org-1' }
    const [r1, r2] = await Promise.all([
      runWorkflow(input),
      runWorkflow(input),
    ])
    // TODO: assert r1 and r2 are equivalent (or second is a no-op)
    expect(r1).toEqual(r2)
  })

  it('handles activity failure with retry', async () => {
    let callCount = 0
    const result = await runWorkflow(
      { organizationId: 'org-1' },
      {
        <activityName>: async (input) => {
          callCount++
          if (callCount < 2) throw new Error('transient failure')
          return activities.<activityName>(input)
        },
      },
    )
    expect(callCount).toBeGreaterThanOrEqual(2)
    expect(result).toBeDefined()
  })

  it('fails permanently on non-retryable error', async () => {
    await expect(
      runWorkflow(
        { organizationId: 'org-1' },
        {
          <activityName>: async () => {
            const { ApplicationFailure } = await import('@temporalio/common')
            throw ApplicationFailure.create({ message: 'PERMANENT', nonRetryable: true })
          },
        },
      ),
    ).rejects.toThrow('PERMANENT')
  })

  it('advances through time-gated steps (time skipping)', async () => {
    // For workflows with sleep() or condition() timeouts, time skipping
    // allows the test to advance time without actually waiting.
    // Example: await testEnv.sleep('48h') to trigger a 48-hour condition.
    //
    // TODO: add a time-gated test if the workflow has sleep() or condition()
    expect(true).toBe(true) // placeholder — replace or remove
  })
})
```

### 6. Update barrels

Add the new workflow and activities to their respective `index.ts` barrels:

```ts
// packages/temporal-workflows/src/workflows/index.ts
export { <featureName>Workflow } from './<feature-name>'
// export type { <FeatureName>WorkflowInput, <FeatureName>WorkflowOutput } from './<feature-name>'
```

```ts
// packages/temporal-workflows/src/activities/index.ts
export * from './<feature-name>'
```

### 7. Print the scaffold summary

```
## Temporal scaffold complete

**Feature**: `<feature-name>`
**Workflow ID template**: `<feature-name>-{id}` (idempotent — derive {id} from the triggering resource)

**Files created / updated**:
- `packages/temporal-workflows/src/workflows/<feature-name>.ts`  ← deterministic workflow
- `packages/temporal-workflows/src/activities/<feature-name>.ts` ← activities (external effects)
- `packages/temporal-workflows/test/<feature-name>.test.ts`       ← bun:test + time skipping
- `packages/temporal-workflows/src/workflows/index.ts`           ← barrel (updated)
- `packages/temporal-workflows/src/activities/index.ts`          ← barrel (updated)

**Trigger** (`--trigger <type>`):
  - trpc: call `temporalClient.workflow.start(<featureName>Workflow, { workflowId: \`<feature-name>-${id}\`, ... })` from the tRPC procedure
  - bullmq: emit a BullMQ job whose worker calls `temporalClient.workflow.start(...)`
  - cron: register in Temporal schedules config
  - webhook: call from Hono route handler

**TODOs** (search `// TODO` in the generated files):
- [ ] Implement activity functions (add DB / HTTP / email calls)
- [ ] Add workflow steps (un-comment the step stubs in the workflow)
- [ ] Define WorkflowInput / WorkflowOutput types
- [ ] Set meaningful retry policy values for each activity
- [ ] Add time-gated test if workflow uses sleep() or condition()
- [ ] Register the worker task queue in `apps/api/src/workers/temporal.ts`

**Determinism check** (never put these in workflow code — only in activities):
  ✗ Date.now() / new Date()   →  use workflow.now() or pass timestamps via input
  ✗ Math.random()             →  generate in activity, pass result back
  ✗ db / redis / fetch        →  activity only
  ✗ console.log()             →  use log.info() from @temporalio/workflow

**Run tests**:
  bun test packages/temporal-workflows/test/<feature-name>.test.ts
```

### 8. Constitution compliance check

Before writing files, verify:

1. Workflow file has **zero imports from `db`, `redis`, `fetch`, `axios`, `nodemailer`** — all I/O must be in activities.
2. Activities file has `Context.current().heartbeat()` in any function with a loop or long I/O operation.
3. Workflow ID template is idempotent (deterministic from the triggering resource ID) — not `crypto.randomUUID()`.
4. `nonRetryable: true` is set on `ApplicationFailure` for permanent business errors.
5. Test file uses `TestWorkflowEnvironment.createTimeSkipping()` — not a live Temporal connection.

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
