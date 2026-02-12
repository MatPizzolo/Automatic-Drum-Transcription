"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, X, FileAudio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";
import {
  ACCEPTED_AUDIO_EXTENSIONS,
  ACCEPTED_AUDIO_TYPES,
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_MB,
} from "@/lib/constants";

interface DropZoneProps {
  file: File | null;
  onFileSelect: (file: File | null) => void;
  error?: string;
}

export function DropZone({ file, onFileSelect, error }: DropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback((f: File): string | null => {
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (
      !ACCEPTED_AUDIO_TYPES.includes(f.type) &&
      !ACCEPTED_AUDIO_EXTENSIONS.includes(ext)
    ) {
      return `Invalid file type. Accepted: ${ACCEPTED_AUDIO_EXTENSIONS.join(", ")}`;
    }
    if (f.size > MAX_FILE_SIZE_BYTES) {
      return `File too large. Maximum: ${MAX_FILE_SIZE_MB} MB`;
    }
    return null;
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      setDropError(null);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) {
        const err = validateFile(droppedFile);
        if (err) {
          setDropError(err);
          setTimeout(() => setDropError(null), 4000);
        } else {
          onFileSelect(droppedFile);
        }
      }
    },
    [onFileSelect, validateFile]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (selectedFile) {
        onFileSelect(selectedFile);
      }
    },
    [onFileSelect]
  );

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/50 p-4">
        <FileAudio className="h-8 w-8 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {formatBytes(file.size)}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => {
            onFileSelect(null);
            if (inputRef.current) inputRef.current.value = "";
          }}
          aria-label="Remove file"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors",
        isDragOver
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-primary/50",
        (error || dropError) && "border-destructive"
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      aria-label="Drop audio file here or click to browse"
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_AUDIO_EXTENSIONS.join(",")}
        onChange={handleFileInput}
        className="hidden"
        aria-hidden="true"
      />
      <Upload className="mb-3 h-10 w-10 text-muted-foreground" />
      <p className="text-sm font-medium">
        Drag & drop your audio file here
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        WAV, MP3, FLAC, OGG — up to {MAX_FILE_SIZE_MB} MB
      </p>
      {(error || dropError) && (
        <p className="mt-2 text-xs text-destructive">{dropError || error}</p>
      )}
    </div>
  );
}
