"use client";

import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { BPM_MAX, BPM_MIN } from "@/lib/constants";

interface AdvancedOptionsProps {
  title: string;
  bpm: string;
  onTitleChange: (value: string) => void;
  onBpmChange: (value: string) => void;
  bpmError?: string;
}

export function AdvancedOptions({
  title,
  bpm,
  onTitleChange,
  onBpmChange,
  bpmError,
}: AdvancedOptionsProps) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="flex w-full items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronDown className="h-4 w-4 transition-transform [[data-state=open]>&]:rotate-180" />
        Advanced Options
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3 space-y-3">
        <div className="space-y-1.5">
          <label htmlFor="song-title" className="text-sm font-medium">
            Song Title
          </label>
          <input
            id="song-title"
            type="text"
            placeholder="Untitled"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="bpm" className="text-sm font-medium">
            BPM
          </label>
          <input
            id="bpm"
            type="number"
            placeholder="Auto-detect"
            min={BPM_MIN}
            max={BPM_MAX}
            value={bpm}
            onChange={(e) => onBpmChange(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          />
          {bpmError && (
            <p className="text-xs text-destructive">{bpmError}</p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
