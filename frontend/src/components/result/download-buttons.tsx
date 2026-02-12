"use client";

import { FileDown, FileCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getDownloadUrl } from "@/lib/api-client-browser";

interface DownloadButtonsProps {
  jobId: string;
}

export function DownloadButtons({ jobId }: DownloadButtonsProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <Button variant="outline" asChild>
        <a href={getDownloadUrl(jobId, "pdf")} download>
          <FileDown className="mr-2 h-4 w-4" />
          Download PDF
        </a>
      </Button>
      <Button variant="outline" asChild>
        <a href={getDownloadUrl(jobId, "musicxml")} download>
          <FileCode className="mr-2 h-4 w-4" />
          Download MusicXML
        </a>
      </Button>
    </div>
  );
}
