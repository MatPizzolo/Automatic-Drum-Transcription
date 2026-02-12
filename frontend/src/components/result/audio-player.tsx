"use client";

import { Play, Pause, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAudioPlayer } from "@/hooks/use-audio-player";
import { formatDuration } from "@/lib/utils";

interface AudioPlayerProps {
  src?: string;
  isYoutubeSource?: boolean;
}

export function AudioPlayer({ src, isYoutubeSource }: AudioPlayerProps) {
  const { isPlaying, currentTime, duration, isLoading, error, togglePlay, seek } =
    useAudioPlayer(src);

  if (isYoutubeSource || !src) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 p-4 text-sm text-muted-foreground">
        <Info className="h-4 w-4 shrink-0" />
        Audio playback not available for YouTube sources.
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        <Info className="h-4 w-4 shrink-0" />
        {error}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/50 p-3">
      <Button
        variant="ghost"
        size="icon"
        onClick={togglePlay}
        disabled={isLoading}
        aria-label={isPlaying ? "Pause" : "Play"}
        className="shrink-0"
      >
        {isPlaying ? (
          <Pause className="h-5 w-5" />
        ) : (
          <Play className="h-5 w-5" />
        )}
      </Button>

      <div className="flex flex-1 items-center gap-2">
        <span className="w-12 text-xs font-mono text-muted-foreground">
          {formatDuration(currentTime)}
        </span>
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={currentTime}
          onChange={(e) => seek(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-muted accent-primary"
          aria-label="Seek"
        />
        <span className="w-12 text-right text-xs font-mono text-muted-foreground">
          {formatDuration(duration)}
        </span>
      </div>
    </div>
  );
}
