import type { CreateJobResponse, Job, JobResult, ApiError } from "@/types/api";

const API_URL = process.env.API_URL || "http://localhost:8000/api/v1";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message = body.detail || body.error || `HTTP ${res.status}`;
    const error: ApiError = Object.assign(new Error(message), {
      status: res.status,
    });
    throw error;
  }
  return res.json();
}

export async function createJobFromFile(
  formData: FormData
): Promise<CreateJobResponse> {
  const res = await fetch(`${API_URL}/jobs`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<CreateJobResponse>(res);
}

export async function createJobFromYouTube(data: {
  youtube_url: string;
  title?: string;
  bpm?: number;
}): Promise<CreateJobResponse> {
  const res = await fetch(`${API_URL}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<CreateJobResponse>(res);
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${API_URL}/jobs/${id}`, {
    cache: "no-store",
  });
  return handleResponse<Job>(res);
}

export async function getJobResult(id: string): Promise<JobResult> {
  const res = await fetch(`${API_URL}/jobs/${id}/result`, {
    cache: "no-store",
  });
  return handleResponse<JobResult>(res);
}

export async function deleteJob(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/jobs/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const error: ApiError = Object.assign(
      new Error(`Failed to delete job: HTTP ${res.status}`),
      { status: res.status }
    );
    throw error;
  }
}
