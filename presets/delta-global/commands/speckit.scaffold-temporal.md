---
description: Scaffold a Temporal workflow for the Delta-Global stack — the deterministic workflow and its activity interface in packages/temporal-workflows/src, the activity implementation in apps/workers (Python, Pydantic-validated payloads) or apps/crawler (TS), an idempotent start from apps/api through the Temporal client, start/complete/fail events, BENIGN classification of expected failures, and the replay-history test that guards every deploy.
handoffs:
  - label: Generate tasks for workflow
    agent: speckit.tasks
    prompt: Generate implementation tasks for the Temporal workflow scaffolded for this feature, tests first, including the replay history.
  - label: Analyze workflow consistency
    agent: speckit.analyze
    prompt: Cross-check the Temporal workflow against the plan's Background Jobs section — idempotent IDs, timeouts, retry budget, activity isolation and the replay history.
---

## User Input

```text
$ARGUMENTS
```

Parse from `$ARGUMENTS` (ask once if missing):

| Token | Meaning |
|---|---|
| workflow | `PascalCaseWorkflow` name and what it coordinates |
| activities | `camelCaseActivity` names, each with its single external effect |
| runtime | where activities run: `workers` (Python 3.12 — LLM, embeddings, classification) or `crawler` (TS — fetching sources) |
| trigger | API mutation (start), Temporal Schedule, signal, or child of another workflow |
| id | the business key the workflow ID derives from (e.g. `sector-embed-<sectorId>`) |

If a plan exists, §9 *Background Jobs* is the contract. Temporal is the **only** background mechanism here: no queue library, and a polling loop that could be a workflow is a forbidden pattern.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing: skip `enabled: false`, skip non-empty `condition`, surface optional hooks, execute mandatory hooks and wait for them.

Read before writing: `packages/temporal-workflows/src/workflows/data-retention.ts` (timeouts, heartbeats, bounded loops), `packages/temporal-workflows/src/activities.ts` + `src/index.ts` (activity type exports), `packages/temporal-workflows/test/histories/README.md`, and for Python `apps/workers/src/worker.py` (registration, task queue) and `apps/workers/src/infrastructure/error_reporting.py` (BENIGN).

## Rules this scaffold enforces

- **Determinism**: workflow code uses only `@temporalio/workflow` APIs — no `Date.now()`, `Math.random()`, `crypto.randomUUID()`, I/O, env reads or imports of `@delta-global/db` in a workflow file. Time comes from `workflow` sleep/timers; randomness from `uuid4()` of the workflow API.
- **Idempotent IDs**: workflow IDs derive from the business key (`<area>-<id>`), never a random UUID; the start uses an ID-conflict policy that makes a double click a no-op.
- **Every activity proxy** sets `startToCloseTimeout`, a bounded `retry` (`maximumAttempts`), and `heartbeatTimeout` when it can run long. Loops inside a workflow are bounded; long histories use `continueAsNew`.
- **Activities isolate external effects** (DB writes, OpenRouter, HTTP) and are idempotent on retry. LLM calls go through OpenRouter with a cost cap; a non-parseable answer is not retried on the paid path (F-54).
- **Payload validation**: TS activities parse their input with the Zod schema from `packages/shared`; Python activities validate with the **generated** Pydantic models (`bun run gen:py-models` → `apps/workers/src/models/generated.py`, never hand-edited; `check:py-models` fails on drift).
- **Expected failures are BENIGN**: a source-caused or client-caused failure raises `ApplicationFailure` with the BENIGN category so it is logged at debug and not sent to GlitchTip; unexpected ones are reported beside the existing handling (`createErrorReporter` in TS, the workers' `error_reporting` in Python).
- **Events**: the operation emits start / complete / fail with duration (log + span; a metric only with bounded labels — never a sector/article/user id label). Logs: `@delta-global/logger` (TS) or loguru (Python), with `trace_id`.
- **Replay safety**: every registered workflow type has a recorded history in `packages/temporal-workflows/test/histories/`. Changing a workflow that may have open executions requires `patched()`; a failing replay is **never** fixed by regenerating the fixture.
- **Flag**: if the workflow is part of a flagged feature, the trigger (API service) checks the flag; the workflow itself does not read flags (non-deterministic).

## Outline

### 1. Tests first

- `packages/temporal-workflows/test/<area>.test.ts` — `TestWorkflowEnvironment.createTimeSkipping()` with stubbed activities (pattern: `test/stubs.ts`, `test/scenarios.ts`): happy path, an activity failing past its retry budget, a BENIGN failure, idempotent re-start with the same ID.
- Add a scenario to `test/scenarios.ts` and record its history: `bun --filter @delta-global/temporal-workflows gen:replay-histories` → `test/histories/<Workflow>.<scenario>.json`. `test/replay.test.ts` picks it up.
- Python activities: `apps/workers/tests/test_<activity>.py` (pytest, `asyncio_mode=auto`); integration cases marked `integration` and run against `INTEGRATION_DB_URL` — a skip under `CI` fails.
- Crawler activities: `apps/crawler/src/activities/<area>.test.ts` (integration gated with the crawler's `describeIntegration` copy).

### 2. Files

```
packages/temporal-workflows/src/workflows/<area>.ts   # PascalCaseWorkflow — deterministic
packages/temporal-workflows/src/workflows/index.ts    # export it (the replay bundle imports this)
packages/temporal-workflows/src/activities.ts         # <Area>Activities interface + payload types
packages/temporal-workflows/src/index.ts              # re-export the types
apps/workers/src/activities/<area>.py                 # or apps/crawler/src/activities/<area>.ts
apps/workers/src/worker.py                            # register workflow-side activities on the right task queue
apps/api/src/services/<area>.ts                       # starts the workflow through the injected Temporal client
```

Workflow skeleton:

```ts
import { ApplicationFailure, log, proxyActivities } from "@temporalio/workflow";
import type { ReembedActivities, ReembedInput, ReembedResult } from "../activities";

const { reembedSector } = proxyActivities<ReembedActivities>({
  startToCloseTimeout: "2 minutes",
  heartbeatTimeout: "30 seconds",
  retry: { initialInterval: "5s", backoffCoefficient: 2, maximumAttempts: 3 },
});

export async function ReembedSectorWorkflow(input: ReembedInput): Promise<ReembedResult> {
  log.info("reembed.start", { sectorId: input.sectorId });
  const result = await reembedSector(input);
  if (result.kind === "skipped") {
    throw ApplicationFailure.create({ message: "sector deleted", nonRetryable: true, category: "BENIGN" });
  }
  log.info("reembed.complete", { sectorId: input.sectorId });
  return result;
}
```

API start (inside a service that receives the client as a parameter — services never value-import `clients/temporal`, `check:composition-root`):

```ts
await temporal.workflow.start("ReembedSectorWorkflow", {
  taskQueue: TASK_QUEUE,
  workflowId: `sector-reembed-${sectorId}`,
  workflowIdConflictPolicy: "USE_EXISTING",
  args: [{ sectorId }],
});
```

Use the task queue the target worker already polls (read it from the worker's registration — do not invent a new queue unless the plan justifies a new worker deployment, which is a `platform-infra` change).

### 3. Verify

```bash
bun test packages/temporal-workflows
bun run check:py-models
cd apps/workers && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest tests/ -k <area>
bun run check:composition-root && bun run typecheck
```

Report: workflow ID formula, timeouts and retry budget per activity, which failures are BENIGN, the recorded history file(s), and the command results.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
