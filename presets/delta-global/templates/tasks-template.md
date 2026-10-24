---
description: "Task list for feature [NNN] — [FEATURE NAME]"
---

# Tasks: [FEATURE NAME]

**Feature slug**: `[feature-name]`
**Feature flag**: `[feature-name]` (must be OFF at merge) | none
**Plan ref**: [plan.md](./plan.md) · **Spec ref**: [spec.md](./spec.md)
**Phase**: P1 (US1…) + P2 (…)

**Prerequisites**: plan.md, spec.md (+ research.md, data-model.md, contracts/schema.graphql, quickstart.md when they exist)

**Organization**: grouped by **user story**, not by layer — each story phase is
independently testable and shippable; US1 alone is the MVP.

**Tests are mandatory** (Constitution III — non-negotiable): within every phase
the *Tests first* tasks precede the *Implementation* tasks, and must be seen
failing before implementation starts.

**Delivery**: one phase = one commit (Conventional Commit, scope from
commitlint's list); a phase does not start before the previous phase's ACs
pass. Branch `feat/[feature-name]-[short-id]`.

---

## Format: `- [ ] T### [P?] [US#?] Description — exact/path (AC-###)`

- **[P]**: parallelizable — different files, no dependency on an incomplete task
- **[US#]**: the user story served (story phases only)
- Every task names an exact file path; every story task cites the AC(s) it covers
- A task that could not be completed stays `[ ]` with a **bold** note saying why
  (e.g. "**db:migrate NOT run** — only the shared dev DB was reachable"). Never tick partial work.

---

## Path Conventions (verified for this feature — correct them if the code says otherwise)

| Layer | Path |
|---|---|
| Zod contracts | `packages/shared/src/schemas/[feature-name].ts` |
| Flag registry | `packages/shared/src/schemas/feature-flags.ts` · seed `packages/db/src/seeds/feature-flags.ts` |
| Drizzle schema | `packages/db/src/schema/[file].ts` |
| Migration | `packages/db/drizzle/` via `bun run db:generate` (`--custom` for RLS) |
| DB functions | `packages/db/src/[feature-name]-dal.ts` |
| Services | `apps/api/src/services/[feature-name].ts` |
| SDL | `packages/graphql/schema/[NN]-[area].graphql` |
| Resolvers | `apps/api/src/graphql/resolvers/[feature-name].ts` |
| API tests | `apps/api/test/[feature-name]/` |
| Web operations | `apps/web/src/graphql/[feature-name].graphql` |
| RSC reads / seam | `apps/web/src/lib/server/[feature-name].ts` · `apps/web/src/lib/[feature-name]-api.ts` |
| Route | `apps/web/src/app/[locale]/(dashboard)/[feature-name]/` |
| Components | `apps/web/src/components/[feature-name]/` |
| i18n | `apps/web/messages/{en,fr,es}.json` |
| Temporal | `packages/temporal-workflows/src/` · activities `apps/workers/src/activities/` or `apps/crawler/src/` |
| E2E | `apps/web/e2e/[feature-name].spec.ts` |
| Infra (separate repo) | `platform-infra/charts/grafana/{alerting,dashboards}/[NNN]-[feature-name].json` |

---

## Phase 1 — Setup

Blockers that gate the value of everything else (measure, confirm premises).

- [ ] T001 Confirm integration tests execute here: `bun run check:integration-skip` (and `INTEGRATION_DB_URL` reachable) — evidence in the task note
- [ ] T002 [P] Register flag `[feature-name]` (OFF) in `packages/shared/src/schemas/feature-flags.ts` (KEYS + METADATA), seed `packages/db/src/seeds/feature-flags.ts`, python mirror if workers read it
- [ ] T003 [P] Zod contracts in `packages/shared/src/schemas/[feature-name].ts`, exported from the barrel; no scope key in any input; `bun run gen:py-models` if Python reads them
- [ ] T004 [P] Message keys in `apps/web/messages/en.json`, then fr/es (parity)

---

## Phase 2 — Foundational (blocks every story)

- [ ] T005 Drizzle schema `packages/db/src/schema/[file].ts` (scope column, timestamps, indexes incl. `id` tiebreak)
- [ ] T006 `bun run db:generate` → review the SQL line by line against CONVENTIONS §6; add the `--custom` RLS block for new tables; `bun run check:migration-expand-contract origin/main`
- [ ] T007 Apply locally (`bun run db:migrate` against your own/test DB — **never** silently against shared dev)
- [ ] T008 [P] Tests first: `apps/api/test/[feature-name]/services.test.ts` (pure branches) — failing
- [ ] T009 [P] Services `apps/api/src/services/[feature-name].ts` + flag wrapper `apps/api/src/services/[feature-name]-flag.ts`
- [ ] T010 SDL `packages/graphql/schema/[NN]-[area].graphql` with directives; `bun run check:field-auth`

---

## Phase 3 — US1: [title] (P1) 🎯 MVP

**Goal**: [one sentence]
**Independent test**: [how to prove US1 alone works]

### Tests first

- [ ] T011 [P] [US1] DB-function tests `apps/api/test/[feature-name]/dal.test.ts` with `describeIntegration` (AC-001)
- [ ] T012 [P] [US1] **@critical** isolation/authz `apps/api/test/[feature-name]/authz.test.ts`: other user's rows invisible, non-owner FORBIDDEN, scope key in input ignored (AC-002)
- [ ] T013 [P] [US1] Resolver tests `apps/api/test/[feature-name]/resolvers.test.ts` incl. flag OFF ⇒ today's behaviour (AC-003)

### Implementation

- [ ] T014 [US1] DB functions `packages/db/src/[feature-name]-dal.ts` (projection, cursor + `id` tiebreak)
- [ ] T015 [US1] Resolver `apps/api/src/graphql/resolvers/[feature-name].ts` (thin, typed error codes)
- [ ] T016 [US1] Operations `apps/web/src/graphql/[feature-name].graphql` → `bun --filter='@delta-global/web' codegen`
- [ ] T017 [US1] RSC read `apps/web/src/lib/server/[feature-name].ts` + route `apps/web/src/app/[locale]/(dashboard)/[feature-name]/page.tsx` (+ `loading.tsx`, title, `serverFeatureFlag`)
- [ ] T018 [P] [US1] Components + DOM tests `apps/web/src/components/[feature-name]/*.test.tsx` (`installDom()`): loading / empty / error / success, labels, keyboard path

**Checkpoint**: US1 ACs pass → commit `feat([scope]): …` → next phase.

---

## Phase N — US2: [title] (P2)

[same shape: Tests first → Implementation → Checkpoint]

---

## Phase N+1 — Background work (only if plan §9 is not "None")

- [ ] T0xx Workflow definition `packages/temporal-workflows/src/[feature-name].ts` (deterministic, deterministic workflow ID)
- [ ] T0xx Activities `apps/workers/src/activities/[feature_name].py` (Pydantic-validated payload) or `apps/crawler/src/…`
- [ ] T0xx Replay history in `packages/temporal-workflows/test/histories/` — changing an existing workflow ⇒ `patched()`, never a regenerated fixture

---

## Phase N+2 — Polish & Cross-Cutting

- [ ] T0xx Observability per plan §10 (spans, bounded metrics, `@audited` rows, error reporting)
- [ ] T0xx Alert rules `platform-infra/charts/grafana/alerting/[NNN]-[feature-name].json` (one per rollback threshold; `runbook_url`, no templating) + dashboard JSON
- [ ] T0xx Runbook `docs/runbooks/[feature-name].md` (symptoms, kill switch, rollback pin)
- [ ] T0xx Secrets: Infisical `/app-stack` keys for dev/staging/production + `env.ts` + `.env.example` — or "none"
- [ ] T0xx Egress: CLAUDE.md table + ADR + `charts/network-policies/values.yaml` — or "none"
- [ ] T0xx E2E `@smoke` `apps/web/e2e/[feature-name].spec.ts` (runs nightly)
- [ ] T0xx Gate battery (CONVENTIONS §8) — every command exits 0, outputs recorded:
  `bunx biome ci .` · `bun run depcruise` · `bun run check:composition-root` · `bun run typecheck` · `bun --filter='@delta-global/web' codegen:check` · `bun run check:py-models` · `bun run check:migration-immutability origin/main` · `bun run check:migration-expand-contract origin/main` · `bun run scripts/i18n-parity.ts` · `bun run scripts/i18n-scan.ts` · `bun run test` · `bun run check:integration-skip` · web `perf:budget` · workers `ruff`/`ty`/`pytest` · `gitleaks` · `bash scripts/guard-admin-dal-isolation.sh`
- [ ] T0xx `/speckit.verify` → `verify-report.md` overall PASS
- [ ] T0xx Update CLAUDE.md `SPECKIT START/END` block with what a future session must carry (measured facts, state, what is NOT done)

---

## Dependencies

- Setup → Foundational → US1 → US2 … → Polish. Stories after US1 depend only on Foundational unless stated.

## Parallel Execution Opportunities

[list [P] groups per phase]

## Implementation Strategy

MVP = US1 behind the flag. Ship, verify on staging, then continue.

## Notes

- AC → test map: every AC-### appears in at least one task; `/speckit.analyze` reports gaps.
- Open findings are never left in a table here — each becomes a task, a `follow-ups.md` entry with an owner, or an explicit decision.
