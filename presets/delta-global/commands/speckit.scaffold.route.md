---
description: Scaffold a Delta-Global App Router route segment under apps/web/src/app/[locale]/ — an async RSC page that reads through lib/server (Result envelope, never a throw across the RSC wire), a localized title, Suspense + skeleton, the shared RouteError boundary (retry(), not reset()), the serverFeatureFlag/flagAllows gate, next-intl keys in every locale, and the DOM/route-convention tests.
handoffs:
  - label: Scaffold the GraphQL slice
    agent: speckit.scaffold.graphql
    prompt: Scaffold the SDL, resolver and web operations this route reads and mutates.
  - label: Generate feature tasks
    agent: speckit.tasks
    prompt: Generate implementation tasks for the feature at this route.
  - label: Scaffold Temporal workflow
    agent: speckit.scaffold.temporal
    prompt: Scaffold the Temporal workflow for any async side effects started from this route.
---

## User Input

```text
$ARGUMENTS
```

Parse from `$ARGUMENTS` (ask once if missing):

| Token | Meaning | Default |
|---|---|---|
| slug | kebab-case segment name | required |
| group | `(dashboard)` (signed-in reader) · `(admin)/admin` (admin console) · `(legal)` · `share` (public) | `(dashboard)` |
| params | dynamic segments, e.g. `[id]` | none |
| flag | flag key, plain kebab-case, no `ff-` prefix | the slug, or none |
| interactive | client islands needed (forms, mutations) | inferred |

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing: skip `enabled: false`, skip non-empty `condition`, surface optional hooks, execute mandatory hooks and wait for them.

Read before writing: `apps/web/src/app/[locale]/(dashboard)/sources/submissions/page.tsx` (flag-gated page), `apps/web/src/app/[locale]/(dashboard)/for-you/page.tsx` (title + streaming), `apps/web/src/components/route-error.tsx`, `apps/web/src/app/route-conventions.test.ts`, and `apps/web/docs/adr/0002-graphql-presentation-tier-one-apollo-client.md`.

## Rules this scaffold enforces

- **Server Components by default.** `'use client'` only on interactive leaves; Server Components are passed as `children` into client ones.
- `params` / `searchParams` are Promises — always `await` them; validate any `searchParams` with Zod.
- Initial data is read on the server through `apps/web/src/lib/server/<slug>.ts` (`import "server-only"`, `query()` from `lib/apollo/rsc.ts`), which returns the `Result` envelope from `lib/result.ts`. A failed read **degrades** (the client view fetches itself) — it never throws across the RSC wire.
- One Apollo client per browser session: hooks only inside `(dashboard)` and `(admin)/admin`; imperative calls through the seam `apps/web/src/lib/<slug>-api.ts` (`getBrowserClient()`). Never `new ApolloClient(`, never `fetch('/graphql')` by hand, never a Server Action.
- Every non-admin page has a localized `generateMetadata` title (`getTranslations`), the brand comes from the `[locale]` layout template.
- Every page sits under an `error.tsx` (the route-group one is enough — `(dashboard)/error.tsx` already renders `<RouteError>`). A segment-specific boundary also delegates to `RouteError`, which uses `retry()` (re-fetches) not `reset()` and reports through `reportClientError`.
- `next/image` with remote URLs passed through `httpsImageUrl()` (`src/lib/image-guard.ts`); `preload`, not the deprecated `priority`. `next/font`. No raw `<img>`.
- Every user-facing string is a `next-intl` key present in **{{ var.locales }}** (`apps/web/messages/<locale>.json`, `{{ var.default_locale }}` is the source). No literals in JSX or in `aria-label` / `placeholder` / `title`.
- Flag gate: `const flag = await serverFeatureFlag("<key>")` then branch on `flag === false` only — `null` (unreadable) is treated as allowed via `flagAllows()`, because the server re-checks every gated mutation. An admin route adds no flag check of its own for access: `(admin)` already re-checks `role === "admin"` server-side.
- Four UI states, each designed: loading (skeleton matching the final layout, `aria-busy`), empty (copy + primary action), error (`RouteError`), success. Touch targets ≥ 44×44 px; keyboard complete; WCAG 2.2 AA (`bun run check:contrast` guards tokens).
- Post-auth redirects go through `safeInternalPath()` (`src/lib/safe-redirect.ts`).

## Outline

### 1. Tests first

- Extend nothing in `route-conventions.test.ts` unless the segment needs an exemption (and then keep "the exemption list honest").
- `apps/web/src/components/<slug>/<slug>-view.test.tsx` — DOM test: `installDom()` from `apps/web/test/dom.ts`, Testing Library; cover the four states and the flag-OFF render. Run with `bun test --parallel`.
- Pure helpers (`lib/server/<slug>.ts` mapping) get a `.test.ts` next to them.

### 2. Files

```
apps/web/src/app/[locale]/(dashboard)/<slug>/
├── page.tsx                      # async RSC, generateMetadata, Suspense around the data
└── loading.tsx                   # only if the segment needs its own skeleton beyond the group's
apps/web/src/components/<slug>/
├── <slug>-view.tsx               # 'use client' leaf: renders initial data, fetches itself when absent
├── <slug>-skeleton.tsx
└── <slug>-view.test.tsx
apps/web/src/lib/server/<slug>.ts # server-only reads → Result
apps/web/src/lib/<slug>-api.ts    # imperative client calls (only if needed)
apps/web/messages/<locale>.json   # new namespace "<slug>" in each of {{ var.locales }}
```

`page.tsx`:

```tsx
import type { Metadata } from "next";
import { hasLocale } from "next-intl";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";
import { ReadingListsSkeleton } from "@/components/reading-lists/reading-lists-skeleton";
import { ReadingListsView } from "@/components/reading-lists/reading-lists-view";
import { routing } from "@/i18n/routing";
import { serverFeatureFlag } from "@/lib/server/feature-flag";
import { getReadingLists } from "@/lib/server/reading-lists";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) return {};
  const t = await getTranslations({ locale, namespace: "readingLists" });
  return { title: t("title") };
}

async function ReadingListsData() {
  const enabled = await serverFeatureFlag("reading-lists");
  if (enabled === false) return <ReadingListsView initialEnabled={false} />;
  const result = await getReadingLists();
  return result.ok ? <ReadingListsView initialItems={result.data} initialEnabled /> : <ReadingListsView />;
}

export default function ReadingListsPage(): React.JSX.Element {
  return (
    <Suspense fallback={<ReadingListsSkeleton />}>
      <ReadingListsData />
    </Suspense>
  );
}
```

Messages (`en.json`, then the same keys in every other locale — drafts allowed via `bun run scripts/i18n-translate.ts`, human review required):

```json
{ "readingLists": { "title": "Reading lists", "empty": { "title": "No reading lists yet", "cta": "Create a list" } } }
```

If the segment is newly migrated to i18n, add it to `MIGRATED_DIRS` in `scripts/i18n-scan.ts` so the scan covers it.

### 3. Verify

```bash
bun --filter='@delta-global/web' test        # includes route-conventions.test.ts and the DOM tests
bun run scripts/i18n-parity.ts && bun run scripts/i18n-scan.ts
bun run typecheck
bun run turbo run build --filter=@delta-global/web && bun --filter=@delta-global/web perf:budget
```

Report the files created, the flag behaviour (ON / OFF / unreadable), the new message keys, and the command results. If the bundle budget moved, say by how much.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
