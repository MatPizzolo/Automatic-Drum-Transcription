import type { Job, ApiError } from "@/types/api";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const FETCH_TIMEOUT_MS = 10_000;

export async function fetchJobStatus(id: string): Promise<Job> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/jobs/${id}`, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      const error: ApiError = Object.assign(
        new Error("Request timed out. The server may be overloaded."),
        { status: 408 }
      );
      throw error;
    }
    if (err instanceof TypeError) {
      const error: ApiError = Object.assign(
        new Error("Network error. Check your connection or CORS configuration."),
        { status: 0 }
      );
      throw error;
    }
    throw err;
  }
  if (res.status === 429) {
    const retryAfter = res.headers.get("Retry-After");
    const error: ApiError = Object.assign(
      new Error("Too many active jobs. Please wait."),
      {
        status: 429,
        retryAfter: retryAfter ? parseInt(retryAfter, 10) : 10,
      }
    );
    throw error;
  }
  if (!res.ok) {
    const error: ApiError = Object.assign(
      new Error(`Failed to fetch job status: HTTP ${res.status}`),
      { status: res.status }
    );
    throw error;
  }
  return res.json();
}

export async function deleteJob(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/jobs/${id}`, {
    method: "DELETE",
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });
  if (!res.ok) {
    const error: ApiError = Object.assign(
      new Error(`Failed to cancel job: HTTP ${res.status}`),
      { status: res.status }
    );
    throw error;
  }
}

export async function checkHealth(): Promise<boolean> {
  try {
    const baseUrl = API_URL.replace(/\/api\/v1$/, "");
    const res = await fetch(`${baseUrl}/health`, {
      signal: AbortSignal.timeout(5000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export function getDownloadUrl(jobId: string, format: "musicxml" | "pdf") {
  return `${API_URL}/jobs/${jobId}/download/${format}`;
}
