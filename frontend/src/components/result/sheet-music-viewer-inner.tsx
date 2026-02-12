"use client";

import { useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { getDownloadUrl } from "@/lib/api-client-browser";

interface SheetMusicViewerInnerProps {
  jobId: string;
}

export default function SheetMusicViewerInner({
  jobId,
}: SheetMusicViewerInnerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadOSMD() {
      try {
        const xmlUrl = getDownloadUrl(jobId, "musicxml");
        const res = await fetch(xmlUrl);
        if (!res.ok) throw new Error("Failed to fetch MusicXML");
        const xmlString = await res.text();

        const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");

        if (cancelled || !containerRef.current) return;

        const osmd = new OpenSheetMusicDisplay(containerRef.current, {
          autoResize: true,
          drawTitle: false,
        });

        await osmd.load(xmlString);
        osmd.render();
        setIsLoading(false);

        const observer = new ResizeObserver(() => {
          try {
            osmd.render();
          } catch {
            // ignore resize errors
          }
        });
        observer.observe(containerRef.current);

        return () => observer.disconnect();
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load sheet music"
          );
          setIsLoading(false);
        }
      }
    }

    loadOSMD();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (error) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-destructive/50 bg-destructive/10 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <div className="relative overflow-x-auto rounded-lg border border-border bg-white dark:bg-zinc-950">
      {isLoading && <Skeleton className="absolute inset-0 h-96 w-full" />}
      <div
        ref={containerRef}
        className="min-h-[24rem] p-4"
        aria-label="Drum sheet music"
      />
    </div>
  );
}
