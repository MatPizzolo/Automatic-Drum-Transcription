"use client";

import { Youtube } from "lucide-react";

interface YouTubeInputProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

export function YouTubeInput({ value, onChange, error }: YouTubeInputProps) {
  return (
    <div className="space-y-2">
      <div className="relative">
        <Youtube className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="url"
          placeholder="https://youtube.com/watch?v=..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 pl-10 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label="YouTube URL"
        />
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
