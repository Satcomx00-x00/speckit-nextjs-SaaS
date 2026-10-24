---
description: Delta-Global planning. Turns spec.md into plan.md (+ research.md, data-model.md, contracts/schema.graphql, quickstart.md) for the real platform — Drizzle schema with RLS block, Zod contracts, GraphQL SDL with field-level auth directives, packages/db functions, transport-agnostic services, global DB-backed flag, owner-scoped RBAC, id-list cache, Temporal, observability as code in platform-infra, Service Interaction Map, Complexity Justification.
handoffs:
  - label: Generate tasks
    agent: speckit.tasks
    prompt: Generate tasks.md from this plan, grouped by user story, tests first.
    send: true
  - label: Analyze consistency
    agent: speckit.analyze
    prompt: Cross-check spec ↔ plan for coverage gaps, missing directives, tenancy predicate, flag registry and migration safety.
  - label: RFC checklist
    agent: speckit.checklist
    prompt: preset:rfc
scripts:
  sh: scripts/bash/setup-plan.sh --json
  ps: scripts/powershell/setup-plan.ps1 -Json
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). It
usually carries planning guidance ("reuse the sector feed predicates", "no
Temporal, keep it synchronous"). If it names a research brief
(`docs/research/…/brief.md`), read it — its recommendation is the default
approach unless the spec overrode it.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_plan`. Apply standard hook-processing: skip `enabled: false`,
skip non-empty `condition`, surface optional hooks, execute mandatory ones and
wait for them.

## Ground rules

- **The rule book is the platform's**: `.specify/memory/constitution.md`, then
  `docs/adr/` (ADR-0000 first), then `CLAUDE.md`. The preset's
  `CONVENTIONS.md` summarises them; where they disagree the platform wins.
- **Read the code before designing it.** Every path in the File Map is either
  verified to exist or marked `(new)`. Every reuse claim cites `file:line`.
  The 026 plan's best decisions (read-side predicates, "a PIN cannot be a
  WHERE clause") came from reading the existing predicates first.
- **Measure, don't assume.** Volumes, row counts and latencies come from the
  latest spec measurements, `CLAUDE.md`, or a query you ran — and say which and
  when. A number nobody measured is labelled `assumed`.
- **No section silently skipped.** Sections 1–14 always exist; a section that
  does not apply keeps one line saying why ("§9 None — synchronous, p95 budget
  120 ms").

## Outline

1. **Setup**: Run `{SCRIPT}` from repo root and parse FEATURE_SPEC, IMPL_PLAN,
   SPECS_DIR, BRANCH. IMPL_PLAN already contains the plan template.

2. **Load context**: FEATURE_SPEC; constitution (note its version); the ADR
   index; CLAUDE.md *Forbidden Patterns*, *Approved External Services* and the
   `SPECKIT START/END` block; any research brief; related shipped specs
   (grep the slug and key nouns across `specs/*/plan.md`). Abort with guidance
   if the spec still has `[NEEDS CLARIFICATION]` markers on anything that
   changes the data model, the API surface or authorization — run
   `/speckit.clarify` first.

3. **Phase 0 — research.md**: one numbered entry `R1…Rn` per unknown, decision
   or reuse question, in the format *Question → Finding (with file:line or
   measurement) → Decision → Alternatives rejected*. Include at least:
   - **Tenancy model** — owner-scoped (default: `{{ var.tenancy_model }}`, column
     `{{ var.tenancy_column_snake }}`) or org-scoped, and why (Constitution IV).
   - **Existing code to reuse or extend** — services, DB functions, SDL modules,
     web seams, components.
   - **ADR trigger check** — pinned version/convention change, new API
     surface, new external service, new data store → ADR required; otherwise
     record "no ADR: <reason>" (research.md is then the design record).
   - **Egress** — every outbound host and whether it is already approved.
   - **Library docs** — for any library API you are not certain of in its
     installed version, read the docs (e.g. context7) and cite them.

4. **Phase 1 — design artifacts**:
   - `data-model.md` — entities, columns, constraints, indexes, onDelete,
     state transitions, scope key, RLS block.
   - `contracts/schema.graphql` — the exact SDL to add, with directives.
   - `quickstart.md` — how to run and see the feature locally (flag ON via
     seed or `setFeatureFlag`, `bun dev`, which URL, which account), plus the
     integration-test setup (`INTEGRATION_DB_URL`, port-forward to
     `platform-pg-test`).
   - `plan.md` — fill every section of the template:
     - **Service Interaction Map** first: an explicit yes/no for every
       service, reasons on every "no", timeout/retry/fallback/cost on every
       external call. Every "yes" must reappear in §1–§13.
     - **§1 Drizzle** — then simulate `check:migration-expand-contract`: list
       every statement it would flag and the recipe used (CONVENTIONS §6).
       New table ⇒ `--custom` RLS block, listed in §14.
     - **§3 GraphQL** — directive on every field; `@audited` + top-level
       `reason` on admin mutations; `@cost` on list/expensive fields; typed
       error codes.
     - **§4 DAL / §5 Services** — scope predicate on every query; projection;
       `id` tiebreak; services receive `db`/`redis` as parameters.
     - **§6 Flag** — key without prefix, global, OFF-behaviour argument.
     - **§7 RBAC** — real roles only (no `viewer`).
     - **§8 Cache** — ordered id arrays; blast radius of each write; Redis-down
       behaviour.
     - **§9 Temporal** — or "None" with the synchronous latency budget.
     - **§10 Observability** — bounded labels; alert per rollback threshold
       in `platform-infra/charts/grafana/alerting/<NNN>-<slug>.json`;
       dashboard; runbook path.
     - **§11 Testing** — a row per AC group, a `@critical` authz/isolation
       row per mutation, a flag-OFF row, a failure-mode row per touched
       service.
     - **§14 Complexity Justification** — every deviation from a MUST, or
       "None".

5. **Constitution check (inline, not a separate gate section)**: walk
   principles I–VI against the design and cite, next to each design block, the
   principle it satisfies. Any MUST violated without a §14 row is an
   **ERROR** — fix the design or justify it; do not output a plan that
   silently violates the constitution.

6. **Post-plan checks** (fix before reporting):
   1. Every FR in the spec maps to a plan section; every AC maps to a §11 row.
   2. Every SDL field in §3 has a directive and an RBAC row in §7.
   3. Every cache key in §8 has an invalidation site.
   4. Every rollback threshold in the spec has an alert row in §10.
   5. Every "yes" in the Service Interaction Map appears in §1–§13 and §11.
   6. No forbidden pattern from CLAUDE.md appears anywhere (tRPC, Server
      Actions, a ClickHouse client in api/web, a flag gating the graph,
      `ff-` prefixed keys, `viewer` role, a queue library, polling loops,
      payload-cached lists, unbounded metric labels, hand-written SQL outside
      a justified `--custom` block).

7. **Agent context**: update the plan reference between `<!-- SPECKIT START -->`
   and `<!-- SPECKIT END -->` in `CLAUDE.md` to point to this plan and its
   artifacts. Keep what is already there about other features unless it is
   now false; never remove the turborepo managed block.

8. **Report**: branch, plan path, artifacts written, the ADRs required (or
   none), the §14 deviations, and the riskiest part of the design in one
   sentence.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_plan` entries and apply
standard hook-processing.
