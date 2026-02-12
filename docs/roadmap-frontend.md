# Frontend Roadmap — DrumScribe

> Auto-updated as work progresses. Each phase has a status: `[ ]` pending, `[~]` in progress, `[x]` done.

---

## Phase 1: Scaffold & Dependencies
- [x] Create Next.js 14+ project (App Router, TypeScript, TailwindCSS 4, `src/` dir)
- [x] Init shadcn/ui (`npx shadcn@latest init`) — dark theme default
- [x] Install dependencies: `next-themes`, `framer-motion`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `lucide-react`, `opensheetmusicdisplay`
- [x] Pull shadcn components: Button, Card, Tabs, Progress, Badge, Alert, Collapsible, Sonner, Skeleton, Dialog
- [x] Configure fonts (Inter + JetBrains Mono via `next/font/google`)
- [x] Setup `.env.local` with `API_URL` and `NEXT_PUBLIC_API_URL`

## Phase 2: Foundation (types, lib, providers)
- [x] `src/types/api.ts` — TypeScript interfaces: Job, JobResult, Hit, HitSummary, JobStatus, etc.
- [x] `src/lib/constants.ts` — Instrument colors, status labels, config values
- [x] `src/lib/validations.ts` — Zod schemas (file upload, YouTube URL, BPM range)
- [x] `src/lib/utils.ts` — `cn()` helper, `formatDuration`, `formatBytes`, `formatComputeTime`
- [x] `src/lib/api-client.ts` — Server-side typed fetch wrapper (used in Server Actions + RSC)
- [x] `src/lib/api-client-browser.ts` — Client-side fetch wrapper (used in TanStack Query)
- [x] `src/providers/theme-provider.tsx` — next-themes Client Component wrapper
- [x] `src/providers/query-provider.tsx` — TanStack Query Client Component wrapper

## Phase 3: Layout & Landing Page
- [x] `src/app/layout.tsx` — Root layout: fonts, ThemeProvider, QueryProvider, Header, Footer
- [x] `src/app/globals.css` — Tailwind directives + CSS variables (shadcn dark theme palette)
- [x] `src/components/layout/header.tsx` — Server Component: logo, nav
- [x] `src/components/layout/footer.tsx` — Server Component
- [x] `src/components/layout/theme-toggle.tsx` — Client Component: dark/light switch
- [x] `src/app/page.tsx` — Landing page Server Component shell (hero, "How it works")
- [x] `src/components/upload/upload-form.tsx` — Client Component: Tabs (Upload / YouTube)
- [x] `src/components/upload/drop-zone.tsx` — Client Component: drag-and-drop + file input
- [x] `src/components/upload/youtube-input.tsx` — Client Component: URL input + Zod validation
- [x] `src/components/upload/advanced-options.tsx` — Client Component: Collapsible BPM + title

## Phase 4: Server Action & Job Creation
- [x] `src/app/actions.ts` — `createJob` Server Action (Zod validation, forward to backend, redirect)
- [x] Wire UploadForm to submit via Server Action
- [x] Handle errors: return typed error objects, display in form
- [x] Handle HTTP 429: toast + disable submit

## Phase 5: Processing Page
- [x] `src/app/jobs/[id]/page.tsx` — Client Component with polling
- [x] `src/hooks/use-job-polling.ts` — TanStack Query hook (`refetchInterval: 2000`, stop on terminal)
- [x] `src/components/processing/progress-stepper.tsx` — Multi-step animated stepper (Framer Motion)
- [x] `src/components/processing/progress-bar.tsx` — shadcn Progress with percentage
- [x] Handle `completed` → auto-redirect to `/jobs/[id]/result`
- [x] Handle `failed` → destructive Alert + "Try Again" button
- [x] Handle HTTP 429 → toast + back off polling to 10s

## Phase 6: Result Page
- [x] `src/app/jobs/[id]/result/page.tsx` — Server Component: fetch result, redirect if not completed
- [x] `src/components/result/hit-summary.tsx` — Server Component: stat cards grid
- [x] `src/components/result/warnings-banner.tsx` — Server Component: amber Alert for warnings
- [x] `src/components/result/confidence-badge.tsx` — Server Component: colored confidence indicator
- [x] `src/components/result/download-buttons.tsx` — Client Component: PDF + MusicXML download
- [x] Result header: song title, BPM badge, duration badge, model version, compute time

## Phase 7: Sheet Music Viewer
- [x] `src/components/result/sheet-music-viewer.tsx` — Client Component wrapper (dynamic import)
- [x] `src/components/result/sheet-music-viewer-inner.tsx` — OSMD load + render
- [x] Skeleton placeholder while loading
- [x] Scrollable container + pinch-to-zoom on mobile
- [x] ResizeObserver for re-render on container resize

## Phase 8: Hit Timeline (Piano Roll)
- [x] `src/components/result/hit-timeline.tsx` — Canvas-based visualization
- [x] X-axis = time, Y-axis = instrument rows, colored dots/rects by instrument
- [x] Velocity mapped to opacity/size
- [x] Horizontal scroll for long songs
- [x] Minimap scrubber for songs >60s
- [x] Virtual rendering for >5000 hits (only render visible viewport)

## Phase 9: Audio Player
- [x] `src/hooks/use-audio-player.ts` — Web Audio API hook
- [x] `src/components/result/audio-player.tsx` — Custom player: play/pause, seek, time display
- [x] Handle "not available" for YouTube-sourced jobs

## Phase 10: Polish & Error Handling
- [x] `src/app/error.tsx` — Global error boundary
- [x] `src/app/not-found.tsx` — 404 page
- [x] Framer Motion page transitions (`AnimatePresence` in layout)
- [x] Loading skeletons for all async content (loading.tsx for processing + result pages)
- [x] Responsive tweaks: mobile-first, stepper vertical below `md`, timeline horizontal scroll
- [x] `prefers-reduced-motion` respect (useReducedMotion hook)
- [x] SEO: `metadata` export on landing, `generateMetadata()` on result page
- [x] Accessibility: keyboard nav, aria attributes, focus rings

## Phase 11: Testing
- [x] Setup Vitest + React Testing Library
- [x] Unit tests: Zod schemas, `formatDuration`, `formatBytes`, instrument color mapping (38 tests passing)
- [x] Component tests: DropZone, YouTubeInput, ConfidenceBadge, WarningsBanner, ProgressStepper (72 tests total)
- [x] Setup Playwright + config
- [x] E2E: Landing page tests (hero, tabs, validation, theme toggle, 404)

---

## UX & Architecture Audit (Feb 2026)

> Findings from a senior frontend audit. Fixes already applied are marked `[x]`. New improvement tasks are marked `[ ]`.

### Audit 1: Async State Management

- [x] Replace `as any` casts on error objects with typed `ApiError` interface (`api-client-browser.ts`, `jobs/[id]/page.tsx`)
- [x] **Implement 429 backoff in polling** — `refetchInterval` dynamically reads `ApiError.retryAfter` from `query.state.error` and backs off accordingly.
- [x] **Add stale-job timeout** — Shows warning alert after 15 minutes in non-terminal status. Cancel Job button also added.

### Audit 2: Large File Ingestion

- [x] Client-side validation (type + size) in DropZone — dual MIME + extension check, 50MB limit
- [x] **Upload progress indicator** — XHR upload path with `onprogress` for files >5MB, Server Action fallback for small files. Progress bar shown during upload.
- [x] **Show error on invalid drag-and-drop** — `DropZone` now shows inline error with auto-clear after 4 seconds when a dropped file fails validation.

### Audit 3: Data Visualization (Hit Timeline)

- [x] Canvas-based rendering with virtual viewport culling — correct approach
- [x] Minimap scrubber for songs >60s
- [x] **Remove unused `scrollLeft`/`viewportWidth` state** — Removed `useState` calls that triggered re-renders on every scroll. Scroll state now only used internally in draw callbacks.
- [x] **Cache minimap hit layer** — Hit marks cached to offscreen canvas; only viewport indicator overlay redrawn on scroll.
- [x] **Pre-compute instrument index map** — Module-level `INSTRUMENT_INDEX_MAP` (`Map<InstrumentLabel, number>`) for O(1) lookup in draw loops.

### Audit 4: Environment Consistency

- [x] BFF pattern: `API_URL` (server) / `NEXT_PUBLIC_API_URL` (client) correctly separated
- [x] **Handle CORS/network errors explicitly** — `fetchJobStatus()` catches `TypeError` with "Network or CORS error" message and `TimeoutError` with "Request timed out" message.
- [x] **Add fetch timeout** — `AbortSignal.timeout(10_000)` on all client-side polling and delete fetches.
- [x] **Propagate HTTP status in server-side errors** — `api-client.ts` `handleResponse()` now attaches `status` to thrown `ApiError`.

### Audit 5: Type Safety

- [x] Added missing `created_at`, `updated_at`, `title` fields to `Job` interface (match backend `JobStatusResponse`)
- [x] Added missing `id` field to `JobResult` interface
- [x] Made `JobResult` nullable fields match backend `Optional` types (`number | null`, `string | null`)
- [x] Changed `download_urls` from `{ musicxml; pdf }` to `Record<string, string>` to match backend `Dict[str, str]`
- [x] Created typed `ApiError` interface — zero `as any` casts remain
- [x] Added null-safety guards in result page template

### Audit 6: Roadmap & Milestone Alignment

- [x] Interactive Piano Roll — canvas-based, minimap, virtual rendering
- [x] Sheet Music Viewer — OSMD dynamic import, skeleton, resize-aware
- [x] Audio Player — Web Audio API, YouTube-source fallback
- [x] Mobile/Responsive — stepper vertical below `md`, timeline horizontal scroll, flex-wrap
- [x] **Display user's song title on result page** — Result page `<h1>` now renders `job.title` when available, falls back to "Drum Transcription Result".
- [x] **"Cancel Job" button on processing page** — Client-side `deleteJob()` added to `api-client-browser.ts`, wired to a "Cancel Job" ghost button on the processing page.
- [x] **Backend health-check banner** — `useHealthCheck` hook pings `GET /health` every 30s. `OfflineBanner` component renders a destructive banner when backend is unreachable.
- [ ] **Post-result BPM re-run** — Requires backend support for re-running a job with different BPM. Deferred until backend endpoint is available.

---

## Phase 12: Audit Improvements (Backlog)

> Prioritized tasks derived from the UX audit. Ordered by impact. All items completed except BPM re-run (blocked on backend).

### High Priority
- [x] Upload progress bar for large files (>5MB) — XHR upload with `onprogress` + `useUploadProgress` hook
- [x] 429 dynamic backoff in `useJobPolling` — reads `ApiError.retryAfter` from `query.state.error`
- [x] Display song title on result page from `job.title`
- [x] Fetch timeout (`AbortSignal.timeout(10_000)`) on all client-side API calls

### Medium Priority
- [x] Show inline error on invalid drag-and-drop in DropZone (auto-clears after 4s)
- [x] Stale-job timeout warning (>15 min in non-terminal status)
- [x] "Cancel Job" button on processing page (client-side `deleteJob()`)
- [x] CORS/network `TypeError` handling in `fetchJobStatus()`
- [x] Propagate HTTP status code in server-side `api-client.ts` errors

### Low Priority (Performance)
- [x] Remove `scrollLeft`/`viewportWidth` `useState` in HitTimeline — eliminated scroll-triggered re-renders
- [x] Cache minimap hit layer to offscreen canvas
- [x] Pre-compute instrument index `Map` for O(1) lookup in draw loops
- [x] Backend health-check ping + "offline" banner (`useHealthCheck` + `OfflineBanner`)
- [ ] Post-result BPM re-run UI — deferred, requires backend re-run endpoint

---

## Tech Stack Summary

| Category | Choice |
|----------|--------|
| Framework | Next.js 14+ (App Router, TypeScript) |
| Styling | TailwindCSS 4 |
| UI Components | shadcn/ui (Radix) |
| Icons | Lucide React |
| Data Fetching | Server Components + Server Actions + TanStack Query (polling) |
| Forms | React Hook Form + Zod |
| Audio | Web Audio API (custom hook) |
| Sheet Music | OpenSheetMusicDisplay (OSMD) — dynamic import |
| Animations | Framer Motion |
| Theme | next-themes (dark default) |
| Testing | Vitest + RTL + Playwright |

---

## Key Architecture Decisions

1. **Server Actions for job creation** — keeps backend URL server-side (BFF pattern)
2. **TanStack Query for polling only** — not for initial data fetching (RSC handles that)
3. **OSMD via `next/dynamic` with `ssr: false`** — DOM-dependent, ~1.5MB bundle
4. **Canvas for hit timeline** — performance with thousands of hits
5. **Dual env vars** — `API_URL` (server) + `NEXT_PUBLIC_API_URL` (client polling)
