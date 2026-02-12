"use client";

import { Progress } from "@/components/ui/progress";

interface ProgressBarProps {
  value: number;
}

export function ProgressBar({ value }: ProgressBarProps) {
  return (
    <div className="space-y-2">
      <Progress value={value} className="h-2" />
      <p className="text-center text-sm text-muted-foreground">
        {Math.round(value)}% complete
      </p>
    </div>
  );
}
