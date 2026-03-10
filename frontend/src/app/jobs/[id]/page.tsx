"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertCircle, AlertTriangle, ArrowLeft, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ProgressStepper } from "@/components/processing/progress-stepper";
import { ProgressBar } from "@/components/processing/progress-bar";
import { useJobEvents } from "@/hooks/use-job-events";
import { deleteJob } from "@/lib/api-client-browser";
import Link from "next/link";

const STALE_JOB_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes

export default function ProcessingPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { state: job, error } = useJobEvents(params.id);
  // Don't treat SSE fallback as error - it's expected in MVP mode
  const isError = false;
  const [isStale, setIsStale] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (job?.status === "completed") {
      router.push(`/jobs/${params.id}/result`);
    }
  }, [job?.status, params.id, router]);

  // Stale-job timeout
  useEffect(() => {
    if (job && job.status !== "completed" && job.status !== "failed") {
      staleTimerRef.current = setTimeout(() => setIsStale(true), STALE_JOB_TIMEOUT_MS);
    } else {
      setIsStale(false);
    }
    return () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
    };
  }, [job?.status]);

  useEffect(() => {
    if (isError && error) {
      toast.error(error.message || "Connection error — retrying.");
    }
  }, [isError, error]);

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await deleteJob(params.id);
      toast.success("Job cancelled.");
      router.push("/");
    } catch {
      toast.error("Failed to cancel job.");
      setIsCancelling(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <AnimatePresence mode="wait">
        <motion.div
          key={job?.status || "loading"}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3 }}
          className="space-y-8"
        >
          <div className="text-center">
            <h1 className="text-2xl font-bold">Processing your track</h1>
            <p className="mt-2 text-muted-foreground">
              This usually takes 2–5 minutes depending on the track length.
            </p>
          </div>

          {/* Always show progress UI, even while loading */}
          <ProgressStepper currentStatus={job?.status || "queued"} />
          <ProgressBar value={job?.progress ?? 0} />

          {job?.status === "failed" && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Transcription Failed</AlertTitle>
              <AlertDescription>
                {job.error_message || "An unexpected error occurred."}
              </AlertDescription>
            </Alert>
          )}

          {job?.status === "failed" && (
            <div className="flex justify-center">
              <Button asChild>
                <Link href="/">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Try Again
                </Link>
              </Button>
            </div>
          )}

          {isStale && job?.status !== "failed" && job?.status !== "completed" && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Taking longer than expected</AlertTitle>
              <AlertDescription>
                This job has been processing for over 15 minutes. You can continue waiting or cancel and try again.
              </AlertDescription>
            </Alert>
          )}

          {job && job.status !== "completed" && job.status !== "failed" && (
            <div className="flex justify-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCancel}
                disabled={isCancelling}
                className="text-muted-foreground"
              >
                <X className="mr-2 h-4 w-4" />
                {isCancelling ? "Cancelling…" : "Cancel Job"}
              </Button>
            </div>
          )}

          {/* Removed connection error banner - SSE fallback to polling is expected */}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
