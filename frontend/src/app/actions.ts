"use server";

import { redirect } from "next/navigation";

const API_URL = process.env.API_URL || "http://localhost:8000/api/v1";

export async function createJob(
  formData: FormData
): Promise<{ error: string; detail?: string } | undefined> {
  const mode = formData.get("mode") as string;

  try {
    let res: Response;

    if (mode === "upload") {
      const file = formData.get("file") as File;
      if (!file || file.size === 0) {
        return { error: "No file provided." };
      }

      const uploadData = new FormData();
      uploadData.set("file", file);

      const title = formData.get("title") as string | null;
      const bpm = formData.get("bpm") as string | null;
      if (title) uploadData.set("title", title);
      if (bpm) uploadData.set("bpm", bpm);

      res = await fetch(`${API_URL}/jobs`, {
        method: "POST",
        body: uploadData,
      });
    } else {
      const youtubeUrl = formData.get("youtube_url") as string;
      if (!youtubeUrl) {
        return { error: "No YouTube URL provided." };
      }

      const body: Record<string, unknown> = { youtube_url: youtubeUrl };
      const title = formData.get("title") as string | null;
      const bpm = formData.get("bpm") as string | null;
      if (title) body.title = title;
      if (bpm) body.bpm = Number(bpm);

      res = await fetch(`${API_URL}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }

    if (res.status === 429) {
      return {
        error: "Too many active jobs. Please wait and try again.",
      };
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return {
        error: "Failed to create job.",
        detail: body.detail || body.error || `HTTP ${res.status}`,
      };
    }

    const job = await res.json();
    redirect(`/jobs/${job.id}`);
  } catch (error: unknown) {
    if (error instanceof Error && error.message === "NEXT_REDIRECT") {
      throw error;
    }
    if (
      typeof error === "object" &&
      error !== null &&
      "digest" in error &&
      typeof (error as { digest: unknown }).digest === "string" &&
      (error as { digest: string }).digest.startsWith("NEXT_REDIRECT")
    ) {
      throw error;
    }
    return {
      error: "Something went wrong. Please try again.",
      detail: error instanceof Error ? error.message : undefined,
    };
  }
}
