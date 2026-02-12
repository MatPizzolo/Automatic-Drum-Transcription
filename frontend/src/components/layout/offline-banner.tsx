"use client";

import { WifiOff } from "lucide-react";
import { useHealthCheck } from "@/hooks/use-health-check";

export function OfflineBanner() {
  const { isHealthy } = useHealthCheck();

  if (isHealthy) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-destructive px-4 py-2 text-sm text-destructive-foreground">
      <WifiOff className="h-4 w-4" />
      <span>Backend is unreachable. Some features may not work.</span>
    </div>
  );
}
