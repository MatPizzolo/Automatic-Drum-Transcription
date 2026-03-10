"use client";

import { useEffect, useRef, useState } from "react";
import { fetchJobStatus } from "@/lib/api-client-browser";
import type { JobStatus } from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);
const SSE_MAX_RECONNECTS = 1; // Fail fast in MVP mode
const POLL_INTERVAL_MS = 5000; // Poll every 2s for smoother updates

export interface JobState {
  job_id: string;
  status: JobStatus;
  progress: number;
  error_message?: string;
}

/**
 * useJobEvents — real-time job status via Server-Sent Events.
 *
 * Connects to GET /api/jobs/{id}/events and streams status updates.
 * Falls back to polling every 3 s if the SSE connection fails after
 * SSE_MAX_RECONNECTS attempts (e.g. behind a proxy that buffers streams).
 */
export function useJobEvents(jobId: string) {
  const [state, setState] = useState<JobState | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const reconnectCount = useRef(0);
  const pollingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    function startPollingFallback() {
      if (pollingTimer.current) return;
      pollingTimer.current = setInterval(async () => {
        try {
          const job = await fetchJobStatus(jobId);
          setState({
            job_id: jobId,
            status: job.status,
            progress: job.progress ?? 0,
            error_message: job.error_message,
          });
          if (TERMINAL_STATUSES.has(job.status)) {
            clearInterval(pollingTimer.current!);
            pollingTimer.current = null;
          }
        } catch (err) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      }, POLL_INTERVAL_MS);
    }

    function connect() {
      const es = new EventSource(`${API_URL}/jobs/${jobId}/events`);
      esRef.current = es;

      es.onmessage = (event) => {
        try {
          const payload: JobState = JSON.parse(event.data);
          setState(payload);
          reconnectCount.current = 0;
          if (TERMINAL_STATUSES.has(payload.status)) {
            es.close();
          }
        } catch {
          // ignore malformed frames
        }
      };

      es.onerror = () => {
        es.close();
        reconnectCount.current += 1;
        if (reconnectCount.current >= SSE_MAX_RECONNECTS) {
          // SSE failed - fall back to polling silently (expected in MVP mode)
          // Don't set error state - this is normal behavior
          startPollingFallback();
        } else {
          // Exponential backoff before reconnecting
          const delay = Math.min(1000 * 2 ** reconnectCount.current, 15000);
          setTimeout(connect, delay);
        }
      };
    }

    connect();

    return () => {
      esRef.current?.close();
      esRef.current = null;
      if (pollingTimer.current) {
        clearInterval(pollingTimer.current);
        pollingTimer.current = null;
      }
    };
  }, [jobId]);

  return { state, error };
}
