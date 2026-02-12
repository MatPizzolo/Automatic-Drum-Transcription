"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchJobStatus } from "@/lib/api-client-browser";
import type { ApiError } from "@/types/api";

const DEFAULT_POLL_MS = 2000;
const BACKOFF_POLL_MS = 10_000;

export function useJobPolling(jobId: string) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => fetchJobStatus(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed") return false;
      const err = query.state.error as ApiError | null;
      if (err?.status === 429) {
        return (err.retryAfter ?? 10) * 1000;
      }
      return DEFAULT_POLL_MS;
    },
    retry: (failureCount, error) => {
      const err = error as ApiError;
      if (err?.status === 429) return false;
      return failureCount < 3;
    },
  });
}
