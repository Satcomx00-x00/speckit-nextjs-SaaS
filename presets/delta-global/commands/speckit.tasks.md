---
description: Delta-Global task generation. Turns plan.md + spec.md into tasks.md — T### grouped by user story (Setup → Foundational → US1 MVP → … → Polish), tests first in every phase, exact verified file paths, AC-### mapping, one commit per phase, and the platform's real gate battery.
handoffs:
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check spec ↔ plan ↔ tasks — every AC covered by a task, every plan section by tasks, no forbidden patterns.
    send: true
  - label: Implement
    agent: speckit.implement
    prompt: Implement tasks.md phase by phase — tests first, one commit per phase.
scripts:
  sh: scripts/bash/setup-tasks.sh --json
  ps: scripts/powershell/setup-tasks.ps1 -Json
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). When a
workflow step passes a narrow instruction ("Implement the DB schema for X per
the approved RFC"), treat it as the scope of **this** invocation: generate (or
update) only the tasks for that slice, then implement them if the
instruction says "implement".

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_tasks`. Apply standard hook-processing.

## Outline

1. **Setup**: Run `{SCRIPT}` from repo root and parse FEATURE_DIR,
   TASKS_TEMPLATE and AVAILABLE_DOCS. If TASKS_TEMPLATE is empty fall back to
   `.specify/templates/tasks-template.md`.

2. **Load**: plan.md (File Map, §1–§14, Service Interaction Map) and spec.md
   (stories with priorities, AC-### ids, FRs) — both required. Optional:
   research.md, data-model.md, contracts/schema.graphql, quickstart.md.

3. **Verify the paths before writing them.** For every path in the plan's File
   Map, check whether it exists; record the real path (e.g. a table appended to
   an existing `packages/db/src/schema/sectors.ts` rather than a new file) in
   the *Path Conventions* table. The 026 tasks used `seed/` where the repo has
   `seeds/` — that class of error is caught here.

4. **Generate tasks.md** from the template:
   - **Phase 1 — Setup**: premises that gate everything (`check:integration-skip`,
     measurements the plan marked `assumed`), flag registration, Zod contracts,
     message keys.
   - **Phase 2 — Foundational**: schema + generated migration + review against
     CONVENTIONS §6, services, SDL — whatever every story needs.
   - **Phase 3+ — one phase per user story, in priority order**: *Goal*,
     *Independent test*, `### Tests first` (failing tests, including the
     `@critical` authz/isolation test for every mutation the story adds, and
     the flag-OFF test), `### Implementation`, then a *Checkpoint* line naming
     the commit.
   - **Background work phase** only if plan §9 is not "None" (workflow,
     activities, replay history; `patched()` for changes to existing workflows).
   - **Polish**: observability, alert/dashboard JSON in platform-infra, runbook,
     secrets (Infisical `/app-stack` per env, `env.ts`, `.env.example`), egress,
     E2E `@smoke`, the gate battery, `/speckit.verify`, CLAUDE.md carry-forward.
   - Format, strictly: `- [ ] T### [P?] [US#?] Description — exact/path (AC-###)`.
     IDs sequential across the file. Each story task cites its AC(s).

5. **Coverage validation** (fix before reporting):
   - Every AC-### in spec.md appears in at least one task.
   - Every plan section §1–§13 that is not "None" yields at least one task;
     every "yes" row of the Service Interaction Map yields an implementation
     task and a failure-mode test task.
   - Every SDL mutation has a `@critical` test task; every `@audited` mutation
     has an audit test task.
   - Every rollback threshold has an alert-rule task.
   - No task uses a forbidden pattern or a stale path (`apps/api/src/routers`,
     `apps/api/src/dal/<slug>.ts` for new DB functions, `ff-` keys, BullMQ,
     Server Actions, `scripts/seed.ts`, `bun run knip`, `TASK-NNN` ids).
   - No table of "open findings not addressed here": each finding becomes a
     task, a `follow-ups.md` entry with an owner, or a recorded decision.

6. **Report**: tasks.md path; task count total and per story; the MVP scope
   (normally US1); parallel groups; any path the plan had wrong and what it
   really is.

## Implementing (when the input says "implement")

- Work one phase at a time: write the *Tests first* tasks, run them and see
  them **fail**, implement, run them and see them **pass**, then tick.
- Run the narrowest command that proves the task (`bun test apps/api/test/<slug>/…`
  with `INTEGRATION_DB_URL` set for integration suites), and paste the result
  line into the task note when it was not obvious.
- Never tick a task whose command was not run. A task that cannot be completed
  here (e.g. `db:migrate` against the shared dev DB) stays `[ ]` with a bold
  note — "partially done" is not done.
- Never apply migrations to the shared `dev` database without being asked —
  use your own database or `platform-pg-test`.
- At each checkpoint, propose the Conventional Commit for the phase; commit
  only if the user (or the running workflow) asked for commits.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_tasks` entries and apply
standard hook-processing.
