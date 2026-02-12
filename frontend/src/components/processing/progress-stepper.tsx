"use client";

import {
  Clock,
  AudioWaveform,
  BrainCircuit,
  Music,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { JobStatus } from "@/types/api";
import { STATUS_LABELS, STATUS_STEP_ORDER } from "@/lib/constants";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useReducedMotion } from "@/hooks/use-reduced-motion";

const STEP_ICONS: Record<string, React.ElementType> = {
  queued: Clock,
  separating_drums: AudioWaveform,
  predicting: BrainCircuit,
  transcribing: Music,
  completed: CheckCircle2,
};

interface ProgressStepperProps {
  currentStatus: JobStatus;
}

export function ProgressStepper({ currentStatus }: ProgressStepperProps) {
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const prefersReducedMotion = useReducedMotion();
  const currentIndex = STATUS_STEP_ORDER.indexOf(currentStatus);
  const isFailed = currentStatus === "failed";

  return (
    <div
      className={cn(
        "flex gap-2",
        isDesktop ? "flex-row items-start" : "flex-col"
      )}
      role="progressbar"
      aria-valuenow={currentIndex + 1}
      aria-valuemin={1}
      aria-valuemax={STATUS_STEP_ORDER.length}
    >
      {STATUS_STEP_ORDER.map((status, index) => {
        const Icon = STEP_ICONS[status];
        const isActive = status === currentStatus;
        const isCompleted = currentIndex > index;
        const isCurrent = isActive && !isFailed;

        return (
          <div
            key={status}
            className={cn(
              "flex items-center gap-3",
              isDesktop ? "flex-col flex-1 text-center" : "flex-row"
            )}
            aria-current={isActive ? "step" : undefined}
          >
            <motion.div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                isCompleted &&
                  "border-primary bg-primary text-primary-foreground",
                isCurrent &&
                  "border-primary bg-primary/10 text-primary",
                !isCompleted &&
                  !isCurrent &&
                  "border-muted-foreground/30 text-muted-foreground/50"
              )}
              animate={
                isCurrent && !prefersReducedMotion
                  ? {
                      boxShadow: [
                        "0 0 0 0 rgba(59,130,246,0)",
                        "0 0 0 8px rgba(59,130,246,0.15)",
                        "0 0 0 0 rgba(59,130,246,0)",
                      ],
                    }
                  : {}
              }
              transition={
                isCurrent && !prefersReducedMotion
                  ? { duration: 2, repeat: Infinity, ease: "easeInOut" }
                  : {}
              }
            >
              {isFailed && isActive ? (
                <XCircle className="h-5 w-5 text-destructive" />
              ) : (
                <Icon className="h-5 w-5" />
              )}
            </motion.div>
            <span
              className={cn(
                "text-sm",
                isCompleted && "font-medium text-foreground",
                isCurrent && "font-medium text-primary",
                !isCompleted &&
                  !isCurrent &&
                  "text-muted-foreground/50"
              )}
            >
              {STATUS_LABELS[status]}
            </span>
          </div>
        );
      })}
    </div>
  );
}
