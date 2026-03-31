# Frontend

**Next.js 15 + React 19** frontend for DrumScribe's AI-powered drum transcription service.

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | Next.js | 15+ |
| **React** | React | 19+ |
| **Language** | TypeScript | 5+ |
| **State Management** | TanStack Query | 5+ |
| **Styling** | Tailwind CSS | 3+ |
| **UI Components** | shadcn/ui | Latest |
| **Sheet Music** | OpenSheetMusicDisplay | Latest |
| **Icons** | Lucide React | Latest |

---

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── (routes)/
│   │   │   ├── page.tsx        # Home page (upload interface)
│   │   │   └── jobs/
│   │   │       └── [id]/
│   │   │           └── page.tsx # Job status & results
│   │   ├── actions/            # Server Actions
│   │   │   └── jobs.ts         # Job creation (server-side)
│   │   ├── layout.tsx          # Root layout
│   │   └── globals.css         # Global styles
│   │
│   ├── components/             # React components
│   │   ├── upload/
│   │   │   ├── AudioUploader.tsx
│   │   │   └── YouTubeInput.tsx
│   │   ├── processing/
│   │   │   ├── ProgressBar.tsx
│   │   │   └── StatusIndicator.tsx
│   │   ├── result/
│   │   │   ├── SheetMusicViewer.tsx  # OpenSheetMusicDisplay wrapper
│   │   │   ├── DownloadButtons.tsx
│   │   │   └── MetadataDisplay.tsx
│   │   └── ui/                 # shadcn/ui components
│   │       ├── button.tsx
│   │       ├── card.tsx
│   │       └── ...
│   │
│   ├── hooks/                  # Custom React hooks
│   │   ├── useJobPolling.ts    # Real-time job status polling
│   │   ├── useUpload.ts        # File upload with progress
│   │   └── useAudioPlayer.ts   # Audio playback control
│   │
│   ├── lib/                    # Utilities
│   │   ├── api.ts              # API client
│   │   ├── utils.ts            # Helper functions
│   │   └── constants.ts        # App constants
│   │
│   └── types/                  # TypeScript types
│       └── api.ts              # API response types
│
├── public/                     # Static assets
│   ├── favicon.ico
│   └── assets/
│
├── next.config.mjs             # Next.js configuration
├── tailwind.config.ts          # Tailwind CSS configuration
├── tsconfig.json               # TypeScript configuration
└── package.json                # Dependencies
```

---

## Local Development

### Prerequisites

- Node.js 18+
- npm or yarn

### Setup

```bash
# 1. Install dependencies
npm install

# 2. Configure environment
cp .env.example .env.local
# Edit .env.local with your settings

# 3. Start development server
npm run dev
```

**Application will be available at:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (must be running)

---

## Configuration

### Environment Variables

```bash
# .env.local

# API endpoint (server-side)
API_URL=http://localhost:8000

# API endpoint (client-side)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Production:**
```bash
API_URL=https://api.drumscribe.ai
NEXT_PUBLIC_API_URL=https://api.drumscribe.ai
```

---

## Key Features

### 1. Server Actions for Job Creation

**Benefits:**
- No CORS configuration needed
- Secure API calls (server-side only)
- Progressive enhancement
- Type-safe with TypeScript

**Implementation:**

```typescript
// app/actions/jobs.ts
'use server'

export async function createJob(formData: FormData) {
  const file = formData.get('audio') as File
  
  // Server-side API call (uses API_URL, not NEXT_PUBLIC_API_URL)
  const response = await fetch(`${process.env.API_URL}/api/jobs`, {
    method: 'POST',
    body: formData,
  })
  
  if (!response.ok) {
    throw new Error('Failed to create job')
  }
  
  return response.json()
}
```

**Usage:**

```typescript
// components/upload/AudioUploader.tsx
'use client'

import { createJob } from '@/app/actions/jobs'

export function AudioUploader() {
  async function handleSubmit(formData: FormData) {
    const job = await createJob(formData)
    router.push(`/jobs/${job.id}`)
  }
  
  return (
    <form action={handleSubmit}>
      <input type="file" name="audio" accept="audio/*" />
      <button type="submit">Upload</button>
    </form>
  )
}
```

### 2. Real-Time Polling with TanStack Query

**Implementation:**

```typescript
// hooks/useJobPolling.ts
import { useQuery } from '@tanstack/react-query'

export function useJobPolling(jobId: string) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/jobs/${jobId}`
      )
      return response.json()
    },
    refetchInterval: (data) => {
      // Stop polling when job is complete or failed
      if (data?.status === 'completed') return false
      if (data?.status === 'failed') return false
      
      // Poll every second while processing
      return 1000
    },
    retry: 3,
  })
}
```

**Usage:**

```typescript
// app/jobs/[id]/page.tsx
'use client'

import { useJobPolling } from '@/hooks/useJobPolling'

export default function JobPage({ params }: { params: { id: string } }) {
  const { data: job, isLoading } = useJobPolling(params.id)
  
  if (isLoading) return <LoadingSpinner />
  if (job.status === 'failed') return <ErrorMessage error={job.error_message} />
  if (job.status === 'completed') return <ResultView job={job} />
  
  return <ProcessingView job={job} />
}
```

### 3. Interactive Sheet Music Rendering

**OpenSheetMusicDisplay Integration:**

```typescript
// components/result/SheetMusicViewer.tsx
'use client'

import { useEffect, useRef } from 'react'
import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay'

export function SheetMusicViewer({ musicXmlUrl }: { musicXmlUrl: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null)
  
  useEffect(() => {
    if (!containerRef.current) return
    
    // Initialize OpenSheetMusicDisplay
    osmdRef.current = new OpenSheetMusicDisplay(containerRef.current, {
      autoResize: true,
      backend: 'svg',
      drawTitle: true,
    })
    
    // Load MusicXML
    osmdRef.current.load(musicXmlUrl).then(() => {
      osmdRef.current?.render()
    })
    
    return () => {
      osmdRef.current?.clear()
    }
  }, [musicXmlUrl])
  
  return (
    <div className="sheet-music-container">
      <div ref={containerRef} />
      
      {/* Zoom controls */}
      <div className="controls">
        <button onClick={() => osmdRef.current?.zoom(1.2)}>Zoom In</button>
        <button onClick={() => osmdRef.current?.zoom(0.8)}>Zoom Out</button>
      </div>
    </div>
  )
}
```

### 4. File Upload with Progress

```typescript
// hooks/useUpload.ts
import { useState } from 'react'

export function useUpload() {
  const [progress, setProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  
  async function upload(file: File) {
    setIsUploading(true)
    setProgress(0)
    
    const formData = new FormData()
    formData.append('audio', file)
    
    const xhr = new XMLHttpRequest()
    
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        setProgress((e.loaded / e.total) * 100)
      }
    })
    
    return new Promise((resolve, reject) => {
      xhr.addEventListener('load', () => {
        setIsUploading(false)
        if (xhr.status === 200) {
          resolve(JSON.parse(xhr.responseText))
        } else {
          reject(new Error('Upload failed'))
        }
      })
      
      xhr.addEventListener('error', () => {
        setIsUploading(false)
        reject(new Error('Upload failed'))
      })
      
      xhr.open('POST', `${process.env.NEXT_PUBLIC_API_URL}/api/jobs`)
      xhr.send(formData)
    })
  }
  
  return { upload, progress, isUploading }
}
```

---

## Component Architecture

### Server Components (Default)

```typescript
// app/page.tsx
export default async function HomePage() {
  // Server-side data fetching (no client bundle)
  const stats = await fetchStats()
  
  return (
    <div>
      <h1>DrumScribe</h1>
      <Stats data={stats} />
      <AudioUploader />  {/* Client component */}
    </div>
  )
}
```

### Client Components (Interactive)

```typescript
// components/upload/AudioUploader.tsx
'use client'

import { useState } from 'react'

export function AudioUploader() {
  const [file, setFile] = useState<File | null>(null)
  
  // Interactive logic here
  
  return <form>...</form>
}
```

---

## Styling

### Tailwind CSS

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#0070f3',
        secondary: '#ff6b6b',
      },
    },
  },
  plugins: [],
}
```

### shadcn/ui Components

```bash
# Add components
npx shadcn-ui@latest add button
npx shadcn-ui@latest add card
npx shadcn-ui@latest add dialog
```

**Usage:**

```typescript
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

export function MyComponent() {
  return (
    <Card>
      <Button variant="primary">Upload Audio</Button>
    </Card>
  )
}
```

---

## State Management

### TanStack Query Setup

```typescript
// app/providers.tsx
'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,  // 1 minute
        retry: 3,
      },
    },
  }))
  
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}
```

```typescript
// app/layout.tsx
import { Providers } from './providers'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
```

---

## Testing

### Unit Tests (Jest + React Testing Library)

```typescript
// components/__tests__/AudioUploader.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { AudioUploader } from '../upload/AudioUploader'

describe('AudioUploader', () => {
  it('renders upload button', () => {
    render(<AudioUploader />)
    expect(screen.getByText('Upload Audio')).toBeInTheDocument()
  })
  
  it('handles file selection', () => {
    render(<AudioUploader />)
    const input = screen.getByLabelText('audio-input')
    const file = new File(['audio'], 'test.mp3', { type: 'audio/mp3' })
    
    fireEvent.change(input, { target: { files: [file] } })
    
    expect(screen.getByText('test.mp3')).toBeInTheDocument()
  })
})
```

### E2E Tests (Playwright)

```typescript
// e2e/upload.spec.ts
import { test, expect } from '@playwright/test'

test('upload audio file', async ({ page }) => {
  await page.goto('/')
  
  // Upload file
  const fileInput = page.locator('input[type="file"]')
  await fileInput.setInputFiles('test-audio.mp3')
  
  // Submit
  await page.click('button:has-text("Upload")')
  
  // Wait for redirect to job page
  await expect(page).toHaveURL(/\/jobs\/[a-f0-9-]+/)
  
  // Wait for completion
  await expect(page.locator('text=Completed')).toBeVisible({ timeout: 60000 })
})
```

**Run tests:**

```bash
# Unit tests
npm test

# E2E tests
npm run test:e2e

# E2E tests (headed mode)
npm run test:e2e -- --headed
```

---

## Performance Optimization

### Image Optimization

```typescript
import Image from 'next/image'

<Image
  src="/screenshot.png"
  width={800}
  height={600}
  alt="DrumScribe"
  loading="lazy"
  placeholder="blur"
/>
```

### Code Splitting

```typescript
// Lazy load heavy components
import dynamic from 'next/dynamic'

const SheetMusicViewer = dynamic(
  () => import('@/components/result/SheetMusicViewer'),
  { ssr: false, loading: () => <LoadingSpinner /> }
)
```

### Incremental Static Regeneration

```typescript
// app/page.tsx
export const revalidate = 60  // Revalidate every 60 seconds

export default async function HomePage() {
  const stats = await fetchStats()
  return <StatsDisplay stats={stats} />
}
```

---

## Deployment

### Vercel Deployment

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy to production
vercel --prod

# Environment variables
vercel env add NEXT_PUBLIC_API_URL production
```

**Automatic deployment:**
- Push to `main` branch → automatic production deployment
- Push to other branches → preview deployments

### Build Optimization

```bash
# Build for production
npm run build

# Analyze bundle size
npm run build -- --analyze
```

---

## Related Documentation

- **[System Architecture](../docs/ARCHITECTURE.md)** — Serverless design overview
- **[API Reference](../docs/API_REFERENCE.md)** — REST API documentation
- **[Deployment Guide](../docs/DEPLOYMENT.md)** — Production deployment

---

**Last Updated:** March 2026
