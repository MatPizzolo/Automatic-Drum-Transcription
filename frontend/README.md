# Frontend

Next.js 16 frontend for DrumScribe. Upload audio, track job progress in real-time, and view rendered drum sheet music.

## Stack

- **Next.js 16** — App Router, React 19, React Compiler
- **TailwindCSS 4** + **shadcn/ui** — Component library with Radix primitives
- **TanStack Query** — Server state management, job polling
- **OpenSheetMusicDisplay** — MusicXML rendering in the browser
- **Framer Motion** — Animations and transitions
- **Vitest** + **Playwright** — Unit and E2E testing

## Structure

```
src/
  app/                    Next.js App Router
    page.tsx               Landing / upload page
    jobs/[id]/page.tsx     Job status + results page
    actions.ts             Server Actions (job creation)
    layout.tsx             Root layout with providers
  components/
    upload/                File upload, YouTube URL input
    processing/            Job progress indicators
    result/                Sheet music viewer, hit summary, downloads
    layout/                Header, footer, navigation
    ui/                    shadcn/ui primitives
  hooks/
    use-job-polling.ts     TanStack Query polling for job status
    use-upload-progress.ts Upload progress tracking
    use-audio-player.ts    Audio playback controls
    use-health-check.ts    API health monitoring
  lib/                     API client, utilities
  providers/               React Query, theme providers
```

## Development

```bash
npm install
npm run dev          # http://localhost:3000
```

The frontend expects the API at `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`). In Docker Compose, server-side requests use `API_URL=http://api:8000` (internal network), while client-side requests use the public URL.

## Testing

```bash
npm run test         # Vitest unit tests
npm run test:watch   # Vitest watch mode
npm run test:e2e     # Playwright E2E tests
npm run lint         # ESLint
```
