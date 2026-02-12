export type JobStatus =
  | "queued"
  | "processing"
  | "separating_drums"
  | "predicting"
  | "transcribing"
  | "completed"
  | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  created_at: string;
  updated_at: string;
  title: string;
  error_message?: string;
  compute_time_ms?: number;
  model_version?: string;
  warnings: string[];
}

export interface ApiError extends Error {
  status?: number;
  retryAfter?: number;
}

export interface Hit {
  time: number;
  instrument: InstrumentLabel;
  velocity: number;
}

export type InstrumentLabel =
  | "kick"
  | "snare"
  | "hihat_closed"
  | "hihat_open"
  | "ride"
  | "crash"
  | "tom_high"
  | "tom_mid"
  | "tom_low";

export type HitSummary = Partial<Record<InstrumentLabel, number>>;

export interface JobResult {
  id: string;
  detected_bpm: number | null;
  bpm_unreliable: boolean;
  duration_seconds: number | null;
  confidence_score: number | null;
  warnings: string[];
  compute_time_ms: number | null;
  model_version: string | null;
  hit_summary: HitSummary | null;
  hits: Hit[];
  download_urls: Record<string, string>;
}

export interface CreateJobResponse {
  id: string;
  status: "queued";
}

export interface CreateJobError {
  error: string;
  detail?: string;
}
