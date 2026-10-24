---
description: Delta-Global deep audit. Everything /speckit.audit runs, plus real tests against Postgres/Redis with skip detection, bun audit, the Python worker toolchain (ruff, ty, pytest), Temporal replay, the web bundle budget, and an LLM read-through that confirms findings, removes false positives and correlates cross-file patterns (auth directives, tenancy predicates, cache invalidation, failure isolation). Slower; materially higher signal.
handoffs:
  - label: Plan the remediation
    agent: speckit.plan
    prompt: Build a remediation plan from the deep audit — sequence by criticality, one phase per area, each phase one commit.
  - label: Track as follow-ups
    agent: speckit.tasks
    prompt: Turn the confirmed Critical and High findings into tasks with owners.
---

## User Input

```text
$ARGUMENTS
```

Same scope hints as `/speckit.audit` (paths, severity floor, sections, rule
IDs, cap per rule), plus `--no-tests` to skip Layer D when no test database is
reachable. Empty = whole repository.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. Look for hooks under
`hooks.before_audit_deep`, then `hooks.before_audit`, and apply standard
hook-processing.

## Outline

Run from the platform repo root. Record every command, its exit code and the
relevant output lines — the report quotes them.

### 1. Layers A–C — run `/speckit.audit` logic

Platform gates (Biome, typecheck + check:* scripts, depcruise,
composition-root, tRPC removal, codegen, py-models, migrations, i18n, SVG,
admin-DAL guard, gitleaks), the regex script with its supersession table, and
the Delta-Global pattern sweep — exactly as `/speckit.audit` defines them.

### 2. Layer D — tests that really run

- Integration DB: CI uses service containers; locally, port-forward
  `svc/platform-pg-test-rw` (namespace `platform`) to 15432, run
  `bunx drizzle-kit migrate` in `packages/db`, export `INTEGRATION_DB_URL`
  (and `REDIS_URL` for a disposable Redis). If none is reachable, record
  `UNVERIFIABLE: no integration database` — do **not** report the suites as
  passing.
- `CI=1 bun run test` — with `CI` set, a would-be skip fails, which is the point.
- `bun run check:integration-skip`.
- Count `@critical` tests per api area (`grep -rn "@critical" apps/api/test`)
  and list mutations in `packages/graphql/schema/` with no `@critical` test
  touching their service — each is a **High** finding (Constitution III).
- Temporal: `bun test packages/temporal-workflows/test/replay.test.ts`; a
  history file changed in the same diff as a workflow body is **Critical**
  (`patched()` was required).
- Coverage, report only: `bun run test:affected --coverage --coverage-reporter=lcov`
  then `uvx --from 'diff-cover==10.6.0' diff-cover coverage/lcov.info --compare-branch=origin/main`.
  Compare against the gate in `ci.yml` (`--fail-under`); if the constitution or
  CLAUDE.md claims a threshold CI does not enforce, report `GATE_MISSING_FROM_CI`.

### 3. Layer E — dependencies and supply chain

- `bun audit --audit-level=high` (JSON with `--json`). Critical/High advisories
  on a runtime dependency of `apps/api`, `apps/web`, `apps/crawler` → finding
  with the advisory ID.
- Python: `cd apps/workers && uv run pip-audit` if available, else report as
  not covered.
- Lockfiles: only `bun.lock` and `apps/workers/uv.lock`; any npm/pnpm/yarn
  lockfile is **High**.
- `postinstall` scripts that fetch the network → **High**.
- GitHub Actions pinned by SHA (`uses: …@<40-hex>`); tag pins → **High**.

### 4. Layer F — Python workers

```bash
cd apps/workers
uv run ruff check && uv run ruff format --check && uv run ty check
uv run pytest tests/ -rs        # with INTEGRATION_DB_URL; CI=1 makes skips fail
```

Also: every Temporal activity payload validated by Pydantic on receive;
`generated.py` untouched by hand (`bun run check:py-models`); loguru only.

### 5. Layer G — web performance budget

`bun run turbo run build --filter=@delta-global/web && bun --filter=@delta-global/web perf:budget`.
Over budget → **High** with the offending route/chunk. If a browser tool is
available, measure LCP/INP/CLS on the main reader routes; otherwise list them
as `NOT MEASURED`.

### 6. Layer H — LLM confirmation and cross-file analysis

Read each flagged file in full and classify every Critical/High finding as
`confirmed`, `false positive (<reason>)` or `mitigated (<where>)`. Then run
these cross-file checks, which no regex covers:

1. **Auth directive vs data** — for each `@public` field, read its resolver
   and service: does it return data private to one owner? → Critical.
2. **Tenancy predicate** — for each DAL function on an owner-/org-scoped
   table, trace the scope key back to the GraphQL context: from session/JWT,
   or from an argument? Argument → Critical.
3. **Admin realm** — every `(admin)/admin` page and every `@auth(role: ADMIN)`
   field re-checks the role server-side; admin UI never renders for a member
   (F-45).
4. **Audit contract** — every `@audited` mutation has `reason` as a top-level
   argument and its service writes `audit_log` in the same transaction.
5. **Cache invalidation** — for every mutation, list the id-list cache keys
   it must invalidate and check it does; note any write that invalidates
   every user's cache (blast radius).
6. **Failure isolation** — Redis down: does the request degrade to the DB?
   External call: timeout + retry budget + fallback present? Flag read
   failing closed on a path that serves the whole surface?
7. **Session leaks** — client caches (Apollo, module-level state) reset on
   sign-out so the next account in the same tab sees nothing of the previous
   (F-39).
8. **Error exposure** — raw DB/server error text reachable by a reader (F-41).
9. **Egress/SSRF** — every server-side fetch of a user-supplied URL goes
   through the internal-address guard; every outbound host is in CLAUDE.md
   *Approved External Services*.
10. **Cost** — every OpenRouter call path has a cost cap and no paid retry of
    an unparseable answer; every growing table has a retention rule (ADR-0034).
11. **Web data layer** — one Apollo client; singletons with `keyFields`;
    hooks only inside `(dashboard)` / `(admin)/admin`.

### 7. Persist

`.specify/audits/deep-<YYYYMMDD-HHMMSS>.json` with every layer's raw results
and the classification of each finding; overwrite `.specify/audits/latest-deep.json`.

### 8. Report

```markdown
# Deep Audit — <scope> — <date>

**Layers run**: A gates · B regex · C patterns · D tests · E deps · F python · G perf · H LLM
**Unverifiable layers**: <layer — reason>
**Confirmed**: critical c · high h · medium m · low l   **False positives removed**: n

## Critical, confirmed (block release)
### <ID> — <directive>
*source layer · Constitution principle · evidence*
- `file:line` — snippet / command output
**Fix:** …

## High, confirmed
## Mitigated (document, do not block)
## False positives (why the tool misled)
## Cross-file patterns
## Gates claimed but not enforced
## Top 5 prioritized actions
```

### 9. Self-check

- Every confirmed finding cites a file or command output you actually saw.
- No layer is reported as passing that did not run.
- Tests run with no database are `UNVERIFIABLE`, never green.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_audit_deep`, then
`hooks.after_audit`, and apply standard hook-processing.
