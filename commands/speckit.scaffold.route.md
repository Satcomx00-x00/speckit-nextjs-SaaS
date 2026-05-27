---
description: Scaffold a Delta-Global App Router route segment. Generates page.tsx (RSC, SDK createCaller, feature-flag guard), layout.tsx, loading.tsx, error.tsx (GlitchTip capture, Réessayer button), and not-found.tsx — wired to BetterAuth, the flag service, and @delta-global/ui conventions.
handoffs:
  - label: Scaffold the DAL
    agent: speckit.scaffold.dal
    prompt: Scaffold the DAL module this route depends on.
  - label: Generate feature tasks
    agent: speckit.tasks
    prompt: Generate implementation tasks for the feature at this route.
  - label: Scaffold Temporal workflow
    agent: speckit.scaffold.temporal
    prompt: Scaffold the Temporal workflow for any async side effects on this route.
---

## User Input

```text
$ARGUMENTS
```

Parse the route path and feature name from `$ARGUMENTS`. Examples:

| Input | Route prefix | Feature slug |
|---|---|---|
| `post-publishing` | `app/(app)/[workspace]/post-publishing` | `post-publishing` |
| `app/(app)/[workspace]/invoices` | `app/(app)/[workspace]/invoices` | `invoices` |
| `invoices --no-layout` | `app/(app)/[workspace]/invoices` | `invoices` |

Flags (all optional):

| Flag | Meaning | Default |
|---|---|---|
| `--no-layout` | Skip `layout.tsx` | generate layout |
| `--loading=false` | Skip `loading.tsx` | generate loading |
| `--not-found=false` | Skip `not-found.tsx` | generate not-found |
| `--public` | No auth or flag guard | authenticated + flag guarded |
| `--no-flag` | No feature-flag guard | generate flag guard |
| `--title <string>` | Page title for `generateMetadata` | `<FeatureName>s` |
| `--description <string>` | Meta description | placeholder |

If the route path is missing or ambiguous, ask one clarifying question.

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_scaffold`. Apply standard hook-processing.

Compute `ROUTE_ROOT`:
- Base: `apps/web/app/(app)/[workspace]/`
- Append the feature slug. Example: `post-publishing` → `apps/web/app/(app)/[workspace]/post-publishing/`

If `src/app/` exists instead, use that as the base.

---

## Scaffold Steps

### 1. Check for collisions

If any of the target files already exist, print a warning per file and ask whether to overwrite, skip, or abort before writing anything.

### 2. Write the files

#### `page.tsx`

```tsx
// <ROUTE_ROOT>/page.tsx
import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import type { Metadata } from 'next'
import { getSession } from '@/lib/auth'
import { flagService } from '@/lib/flags'
import { createCaller } from '@delta-global/sdk'
import { <Feature>ListSkeleton } from '@/components/features/<feature-name>/<Feature>ListSkeleton'
// import { <Feature>List } from '@/components/features/<feature-name>/<Feature>List'

interface Props {
  params: Promise<{ workspace: string }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { workspace } = await params
  return {
    title: '<title placeholder>',
    description: '<description placeholder>',
  }
}

export default async function <FeatureName>sPage({ params }: Props) {
  // Next.js 15: always await params and searchParams
  const { workspace } = await params

  // ── Auth guard ──────────────────────────────────────────────────────────────
  // Remove this block if --public flag is set.
  const session = await getSession()
  if (!session) redirect('/login')

  // ── Feature flag guard ──────────────────────────────────────────────────────
  // Remove this block if --no-flag flag is set.
  const flagOn = await flagService.isEnabled('ff-<feature-name>', workspace)
  if (!flagOn) redirect(`/${workspace}`)

  return (
    <main>
      <Suspense fallback={<<Feature>ListSkeleton />}>
        <<Feature>DataLayer workspaceId={workspace} />
      </Suspense>
    </main>
  )
}

// ── Async RSC data layer ────────────────────────────────────────────────────────
// Keep inside Suspense boundary so the page shell renders immediately.
// Fetch via SDK server caller — NOT fetch('/api/...'), NOT React Query in RSC.

async function <Feature>DataLayer({ workspaceId }: { workspaceId: string }) {
  const caller = createCaller({ organizationId: workspaceId })
  const data = await caller.<featureCamel>.list({ limit: 20 })
  // TODO: pass data as initialData prop to the client list component
  // return <<Feature>List initialData={data} workspaceId={workspaceId} />
  return null // remove once the component exists
}
```

Rules:
- No `'use client'` — this is a Server Component.
- `await params` and `await searchParams` — required in Next.js 15.
- Data fetched via `createCaller` from `@delta-global/sdk` — never `fetch('/api/...')`.
- Feature flag guard redirects before any data fetch.
- `generateMetadata` always present.
- `<Suspense>` wraps the async data layer.

---

#### `layout.tsx` (unless `--no-layout`)

```tsx
// <ROUTE_ROOT>/layout.tsx
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  params: Promise<{ workspace: string }>
}

export default async function <FeatureName>Layout({ children, params }: Props) {
  // Add shared data fetching here only if ALL children need it (e.g. nav context).
  // Otherwise leave empty — don't pull data that only page.tsx needs.
  return <>{children}</>
}
```

Rules:
- No `'use client'`.
- Children typed as `ReactNode` — not `React.ReactNode`.
- `async` only if layout fetches shared data; omit `async` if it just wraps children.

---

#### `loading.tsx` (unless `--loading=false`)

```tsx
// <ROUTE_ROOT>/loading.tsx
import { <Feature>ListSkeleton } from '@/components/features/<feature-name>/<Feature>ListSkeleton'

export default function <FeatureName>Loading() {
  return <<Feature>ListSkeleton />
}
```

Rules:
- No `'use client'`.
- Uses the same skeleton component as the `<Suspense>` fallback — not a bare `<div>`.
- `aria-busy="true"` and `aria-label` live inside the skeleton component.

---

#### `error.tsx`

```tsx
// <ROUTE_ROOT>/error.tsx
'use client'

import { useEffect } from 'react'
import { Button } from '@delta-global/ui'
// import { captureException } from '@/lib/glitchtip' // ← replace with GlitchTip SDK

interface Props {
  error: Error & { digest?: string }
  reset: () => void
}

export default function <FeatureName>Error({ error, reset }: Props) {
  useEffect(() => {
    // captureException(error)
    console.error(error) // ← replace with GlitchTip capture before shipping
  }, [error])

  return (
    <div role="alert" className="flex flex-col items-center gap-4 py-12 text-center">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="text-sm text-muted-foreground">
        {error.digest ? `Error ID: ${error.digest}` : 'An unexpected error occurred.'}
      </p>
      <Button type="button" variant="outline" onClick={reset}>
        Réessayer
      </Button>
    </div>
  )
}
```

Rules:
- `'use client'` required — React error boundary.
- `role="alert"` on the wrapper for screen-reader announcement.
- GlitchTip capture in `useEffect` — replace `console.error` before shipping.
- Button label is "Réessayer" — use `next-intl` translation key in production.
- `@delta-global/ui` `Button` component, not a raw `<button>`.

---

#### `not-found.tsx` (unless `--not-found=false`)

```tsx
// <ROUTE_ROOT>/not-found.tsx
import Link from 'next/link'
import { Button } from '@delta-global/ui'

export default function <FeatureName>NotFound() {
  return (
    <div className="flex flex-col items-center gap-4 py-12 text-center">
      <h2 className="text-lg font-semibold">Not Found</h2>
      <p className="text-sm text-muted-foreground">
        This resource does not exist or you do not have access to it.
      </p>
      <Button asChild variant="outline">
        <Link href="/">Return Home</Link>
      </Button>
    </div>
  )
}
```

Rules:
- No `'use client'`.
- Use `next/link` via `Button asChild` — not a raw `<a>`.
- Message does not distinguish "not found" from "forbidden" — avoids information leakage.

---

### 3. Print the scaffold summary

```
## Scaffold complete

**Route**: `<ROUTE_ROOT>/`
**Feature flag**: `ff-<feature-name>` (guard in page.tsx)
**Auth**: BetterAuth session check (getSession) in page.tsx

**Files created**:
- `<ROUTE_ROOT>/page.tsx`       ← RSC, generateMetadata, flag guard, SDK caller
- `<ROUTE_ROOT>/layout.tsx`     ← RSC wrapper  (if not skipped)
- `<ROUTE_ROOT>/loading.tsx`    ← Suspense skeleton (if not skipped)
- `<ROUTE_ROOT>/error.tsx`      ← Client error boundary, GlitchTip capture
- `<ROUTE_ROOT>/not-found.tsx`  ← 404/403 handler (if not skipped)

**TODOs** (search `// TODO` in generated files):
- [ ] Implement <Feature>DataLayer — un-comment the SDK caller + component render
- [ ] Create `<Feature>ListSkeleton` component at `components/features/<feature-name>/`
- [ ] Replace `console.error` in error.tsx with GlitchTip `captureException`
- [ ] Replace `generateMetadata` placeholders with real title/description
- [ ] Wire `next-intl` translation keys for all user-visible strings

**Verify**:
- [ ] `bun run typecheck` — new files must compile cleanly
- [ ] `ff-<feature-name>` flag declared in the flag service (OFF by default)
- [ ] No `'use client'` in page.tsx, layout.tsx, loading.tsx, not-found.tsx

**Next steps**:
- Run `/speckit.scaffold.dal <feature-name>` for the DAL this page depends on
- Run `/speckit.tasks <feature-name>` to generate the full implementation task list
```

### 4. Compliance check

After generating all files, verify:

1. `page.tsx` does **not** contain `'use client'`.
2. `error.tsx` **does** contain `'use client'` — required by Next.js for error boundaries.
3. `loading.tsx` and `not-found.tsx` do **not** contain `'use client'`.
4. `page.tsx` does **not** contain `fetch('/api/...')` — only `createCaller`.
5. `page.tsx` contains `await params` before any use of `params` — Next.js 15 requirement.
6. `error.tsx` contains `role="alert"` on the wrapper element.
7. Feature flag guard is present in `page.tsx` (unless `--public` or `--no-flag`).

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_scaffold`. Apply standard hook-processing.
