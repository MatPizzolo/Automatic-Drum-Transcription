import type { InstrumentLabel, JobStatus } from "@/types/api";

export const INSTRUMENT_COLORS: Record<InstrumentLabel, string> = {
  kick: "#3b82f6",
  snare: "#ef4444",
  hihat_closed: "#22c55e",
  hihat_open: "#16a34a",
  crash: "#eab308",
  ride: "#a855f7",
  tom_high: "#f97316",
  tom_mid: "#ea580c",
  tom_low: "#c2410c",
};

export const INSTRUMENT_LABELS: Record<InstrumentLabel, string> = {
  kick: "Kick",
  snare: "Snare",
  hihat_closed: "Hi-Hat (Closed)",
  hihat_open: "Hi-Hat (Open)",
  crash: "Crash",
  ride: "Ride",
  tom_high: "Tom (High)",
  tom_mid: "Tom (Mid)",
  tom_low: "Tom (Low)",
};

export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  separating_drums: "Separating Drums",
  predicting: "Predicting Hits",
  transcribing: "Building Sheet Music",
  completed: "Done",
  failed: "Failed",
};

export const STATUS_STEP_ORDER: JobStatus[] = [
  "queued",
  "separating_drums",
  "predicting",
  "transcribing",
  "completed",
];

export const ACCEPTED_AUDIO_TYPES = [
  "audio/wav",
  "audio/mpeg",
  "audio/flac",
  "audio/ogg",
  "audio/x-wav",
  "audio/mp3",
];

export const ACCEPTED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".flac", ".ogg"];

export const MAX_FILE_SIZE_MB = 50;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export const BPM_MIN = 40;
export const BPM_MAX = 300;

export const WARNING_MESSAGES: Record<string, string> = {
  low_confidence:
    "The AI had low confidence in some predictions — results may be less accurate for this track.",
  bpm_unreliable:
    "BPM auto-detection was uncertain. Consider re-running with a manual BPM value.",
};
