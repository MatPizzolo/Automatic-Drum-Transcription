import { redirect } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { getJob, getJobResult } from "@/lib/api-client";
import { formatDuration, formatComputeTime } from "@/lib/utils";
import { HitSummary } from "@/components/result/hit-summary";
import { WarningsBanner } from "@/components/result/warnings-banner";
import { ConfidenceBadge } from "@/components/result/confidence-badge";
import { DownloadButtons } from "@/components/result/download-buttons";
import { SheetMusicViewer } from "@/components/result/sheet-music-viewer";
import { HitTimeline } from "@/components/result/hit-timeline";
import { AudioPlayer } from "@/components/result/audio-player";

import type { Metadata } from "next";

interface ResultPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({
  params,
}: ResultPageProps): Promise<Metadata> {
  const { id } = await params;
  try {
    const result = await getJobResult(id);
    return {
      title: `Drum Transcription Result — DrumScribe`,
      description: `Detected BPM: ${result.detected_bpm ?? "—"}. Duration: ${result.duration_seconds != null ? formatDuration(result.duration_seconds) : "—"}.`,
    };
  } catch {
    return { title: "Result — DrumScribe" };
  }
}

export default async function ResultPage({ params }: ResultPageProps) {
  const { id } = await params;

  let job;
  try {
    job = await getJob(id);
  } catch {
    redirect("/");
  }

  if (job.status !== "completed") {
    redirect(`/jobs/${id}`);
  }

  let result;
  try {
    result = await getJobResult(id);
  } catch {
    redirect(`/jobs/${id}`);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold sm:text-3xl">
            {job.title && job.title !== "Untitled"
              ? job.title
              : "Drum Transcription Result"}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{result.detected_bpm ?? "—"} BPM</Badge>
          <Badge variant="secondary">
            {result.duration_seconds != null ? formatDuration(result.duration_seconds) : "—"}
          </Badge>
          <Badge variant="outline" className="text-muted-foreground">
            {result.model_version}
          </Badge>
          {result.confidence_score != null && (
            <ConfidenceBadge score={result.confidence_score} />
          )}
          {result.compute_time_ms != null && (
            <span className="text-xs text-muted-foreground">
              Processed in {formatComputeTime(result.compute_time_ms)}
            </span>
          )}
        </div>
      </div>

      {/* Warnings */}
      <WarningsBanner warnings={result.warnings} />

      {/* Hit Summary */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Hit Summary</h2>
        <HitSummary summary={result.hit_summary ?? {}} />
      </section>

      {/* Sheet Music */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Sheet Music</h2>
        <SheetMusicViewer jobId={id} />
      </section>

      {/* Hit Timeline */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Hit Timeline</h2>
        <HitTimeline
          hits={result.hits}
          durationSeconds={result.duration_seconds ?? 0}
        />
      </section>

      {/* Audio Player */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Audio</h2>
        <AudioPlayer />
      </section>

      {/* Downloads + Actions */}
      <section className="flex flex-wrap items-center gap-4 border-t border-border pt-6">
        <DownloadButtons jobId={id} />
        <Button variant="ghost" asChild>
          <Link href="/">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Transcribe Another
          </Link>
        </Button>
      </section>
    </div>
  );
}
