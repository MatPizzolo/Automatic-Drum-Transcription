"use client";

import { useQuery } from "@tanstack/react-query";
import { checkHealth } from "@/lib/api-client-browser";

const HEALTH_CHECK_INTERVAL_MS = 30_000; // 30 seconds

export function useHealthCheck() {
  const { data: isHealthy = true } = useQuery({
    queryKey: ["health"],
    queryFn: checkHealth,
    refetchInterval: HEALTH_CHECK_INTERVAL_MS,
    refetchOnWindowFocus: true,
    staleTime: HEALTH_CHECK_INTERVAL_MS,
  });

  return { isHealthy };
}
