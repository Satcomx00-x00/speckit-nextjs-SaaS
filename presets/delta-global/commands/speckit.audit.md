---
description: Delta-Global codebase audit. Runs the platform's own machine gates (Biome, typecheck with the check:* scripts, depcruise, composition-root, migration, i18n, integration-skip) plus the kit's regex audit script, maps every finding to the constitution, and proposes prioritized fixes. Fast; use /speckit.audit.deep for confirmation and cross-file analysis.
handoffs:
  - label: Deep audit
    agent: speckit.audit.deep
    prompt: Run the deep audit on the same scope — add tests, dependency and Python layers plus cross-file confirmation.
  - label: Amend the constitution from findings
    agent: speckit.constitution.scan
    prompt: Re-scan the repo and propose a constitution amendment for the gaps this audit found.
---

## User Input

```text
$ARGUMENTS
```

Optional scope hints: paths (`apps/api apps/web`), a severity floor
("criticals only"), sections ("only security"), rule IDs, a cap per rule.
Empty = whole repository, floor `low`, 50 findings per rule.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_audit` and apply standard hook-processing (skip
`enabled: false`, skip non-empty `condition`, surface optional hooks, execute
mandatory ones and wait).

## Outline

Run from the platform repo root. The constitution
(`.specify/memory/constitution.md`) is the yardstick; `CLAUDE.md` *Forbidden
Patterns* and `.specify/presets/delta-global/CONVENTIONS.md` give the
concrete rules. Nothing is edited; the JSON reports go to `.specify/audits/`.

### 1. Layer A — platform gates (authoritative)

These are the repo's own checks; their verdict beats any regex. Run each,
record exit code and the first failing lines. Respect path scope where the
tool allows it.

| ID | Command | Constitution |
|---|---|---|
| `GATE.LINT` | `bunx biome ci .` | I |
| `GATE.TYPECHECK` | `bun run typecheck` (runs `check:field-auth`, `check:field-audit`, `check:log-hygiene`, `check:contrast` as turbo deps) | I, IV, V |
| `GATE.DEPCRUISE` | `bun run depcruise` | II |
| `GATE.COMPOSITION` | `bun run check:composition-root` | II |
| `GATE.TRPC` | `bun run check:trpc-removal` | I |
| `GATE.CODEGEN` | `bun --filter='@delta-global/web' codegen:check` | I |
| `GATE.PYMODELS` | `bun run check:py-models` | I |
| `GATE.MIGRATIONS` | `bun run check:migration-immutability origin/main && bun run check:migration-expand-contract origin/main` | IV |
| `GATE.I18N` | `bun run scripts/i18n-parity.ts && bun run scripts/i18n-scan.ts` | — |
| `GATE.SVG` | `bun run check:svg-assets` | — |
| `GATE.ADMIN_DAL` | `bash scripts/guard-admin-dal-isolation.sh` | IV |
| `GATE.SECRETS` | `gitleaks detect --source . --redact --no-banner` | IV |

A failing gate is a **Critical** finding (it would fail CI or a hook).
Also check that each gate is actually wired: find it in
`.github/workflows/ci.yml` or `.pre-commit-config.yaml`. A gate that exists
as a script but runs nowhere is a **High** `GATE_NOT_WIRED` finding (known
case: `guard-admin-dal-isolation.sh` claims CI but only runs in pre-commit).

### 2. Layer B — regex audit script

```bash
bash .specify/scripts/bash/audit-codebase.sh --json [--paths ...] [--rules ...] \
     [--sections ...] [--severity critical|high|medium|low] [--max-findings-per-rule N]
```

(PowerShell: `.specify/scripts/powershell/audit-codebase.ps1 -Json …`; if the
script lives under `.specify/presets/<id>/scripts/`, use that path.) If it is
missing, say so and continue with Layer A only — do not improvise regexes.

Several regex rules are **superseded** by a platform gate; when both report,
keep the gate's verdict and drop the regex finding:

| Regex rule | Superseded by | Note |
|---|---|---|
| `TS.COMPILER.*` | `GATE.TYPECHECK` + `tsconfig.base.json` | flags already set; regex only checks per-package overrides |
| `TS.TYPE.any-usage`, `TS.TYPE.ts-ignore`, `TS.TYPE.unchecked-as-cast` | `GATE.LINT` (Biome) where the rule is enabled | keep regex hits Biome does not cover |
| `PERF.LOG.console-log-in-source` | `GATE.LINT` + `GATE.TYPECHECK` (`check:log-hygiene`) | |
| `FE.IMG.raw-img-tag` | `apps/web/src/app/route-conventions.test.ts` | |
| `SEC.SECRET.*` | `GATE.SECRETS` | regex still useful for `NEXT_PUBLIC_` misuse |
| `INFRA.CI.missing-typecheck-job` | reading `ci.yml` (`typecheck:affected`) | |
| `BE.DAL.missing-server-only` | — | applies to `apps/web/src/lib/server/*` only; `packages/db` and `apps/api` never ship to a browser — drop hits there as false positives |
| `BE.ENV.direct-process-env-outside-validator` | — | `env.ts` modules are the validators |
| `SEC.SQL.template-literal-query` | — | allowed inside `packages/db` Drizzle `sql\`\`` with bound params; a hit in `apps/*` is real |

Persist the script JSON to `.specify/audits/audit-<YYYYMMDD-HHMMSS>.json` and
copy it to `.specify/audits/latest.json`. Add a sibling
`gates-<timestamp>.json` with the Layer A results.

### 3. Layer C — Delta-Global pattern sweep (grep, cheap)

For the scope, grep and report each hit with `file:line`:

| ID | Pattern | Severity |
|---|---|---|
| `DG.CLICKHOUSE.app-tier` | `@clickhouse/` imported under `apps/api` or `apps/web` | Critical |
| `DG.APOLLO.second-client` | `new ApolloClient(` outside `browser-client.ts` / `rsc.ts` | Critical |
| `DG.GRAPHQL.cookie` | a cookie forwarded to `/graphql` | Critical |
| `DG.BILLING.client-price` | price id / amount / return URL accepted from a GraphQL argument | Critical |
| `DG.STRIPE.state-from-event` | `event.data.object.status` written to the DB | Critical |
| `DG.METRIC.unbounded-label` | metric attributes using user/tenant/article id, URL, query, trace/session id | Critical |
| `DG.TEMPORAL.polling` | `setInterval`/`while(true)` + sleep polling in services or workers | High |
| `DG.PAGINATION.no-tiebreak` | `orderBy(` on a paginated list without `id` | High |
| `DG.SELECT.wide-table` | `.from(articles)` / `select().from(` returning the full row in a list | High |
| `DG.ENUM` | `enum ` in TS source | Medium |
| `DG.REACTFC` | `React.FC` | Low |
| `DG.SERVER_ACTION` | `"use server"` | High |
| `DG.FLAG.prefix` | `ff-` in flag keys | Medium |
| `DG.PKG.manager` | `npm `, `pnpm `, `yarn ` in scripts/docs/CI | Medium |
| `DG.ACTION.tag-pin` | `uses: …@v` in `.github/workflows` | High |

### 4. Report

```markdown
# Codebase Audit — <scope> — <date>

**Gates**: <n passed>/<n run> · **Regex findings**: <n> · **Pattern hits**: <n>
**Persisted**: `.specify/audits/audit-…json`, `gates-…json`

## Critical (blocks release)
### <ID> — <rule / directive>
*Constitution <principle> · source: gate | regex | pattern*
- `file:line` — `snippet` / failing output line
**Remediation:** …

## High
## Medium
## Low

## Gates not wired into CI
## Superseded regex findings dropped (count per rule)

## Top 5 prioritized actions
1. <action, files> — clears <n> findings
```

Omit empty severities. Never list a finding the tools did not return.

### 5. Recommendations

- Any Critical → run `/speckit.audit.deep` before the next release.
- A failing `GATE.*` on `main` → fix before any feature work: it means CI was red or not looked at (GitHub Free has no required checks).
- `GATE_NOT_WIRED` → propose the `ci.yml` step.
- Recurring classes (same rule in ≥ 3 modules) → propose a new `scripts/check-*.ts` gate rather than manual fixes.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_audit` entries and apply
standard hook-processing.
