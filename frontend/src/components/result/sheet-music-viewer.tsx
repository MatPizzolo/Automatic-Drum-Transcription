"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

const SheetMusicViewerInner = dynamic(
  () => import("./sheet-music-viewer-inner"),
  {
    ssr: false,
    loading: () => <Skeleton className="h-96 w-full rounded-lg" />,
  }
);

interface SheetMusicViewerProps {
  jobId: string;
}

export function SheetMusicViewer({ jobId }: SheetMusicViewerProps) {
  return <SheetMusicViewerInner jobId={jobId} />;
}
