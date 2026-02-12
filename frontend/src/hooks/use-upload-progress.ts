"use client";

import { useState, useCallback, useRef } from "react";

interface UploadState {
  progress: number;
  isUploading: boolean;
  error: string | null;
}

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const LARGE_FILE_THRESHOLD = 5 * 1024 * 1024; // 5MB

export function useUploadProgress() {
  const [state, setState] = useState<UploadState>({
    progress: 0,
    isUploading: false,
    error: null,
  });
  const xhrRef = useRef<XMLHttpRequest | null>(null);

  const upload = useCallback(
    (formData: FormData): Promise<{ id: string } | { error: string; detail?: string }> => {
      return new Promise((resolve) => {
        setState({ progress: 0, isUploading: true, error: null });

        const xhr = new XMLHttpRequest();
        xhrRef.current = xhr;

        xhr.upload.addEventListener("progress", (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            setState((prev) => ({ ...prev, progress: pct }));
          }
        });

        xhr.addEventListener("load", () => {
          xhrRef.current = null;
          setState((prev) => ({ ...prev, isUploading: false, progress: 100 }));

          if (xhr.status === 429) {
            resolve({ error: "Too many active jobs. Please wait and try again." });
            return;
          }

          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch {
              resolve({ error: "Invalid response from server." });
            }
          } else {
            try {
              const body = JSON.parse(xhr.responseText);
              resolve({
                error: "Failed to create job.",
                detail: body.detail || body.error || `HTTP ${xhr.status}`,
              });
            } catch {
              resolve({ error: `Upload failed: HTTP ${xhr.status}` });
            }
          }
        });

        xhr.addEventListener("error", () => {
          xhrRef.current = null;
          setState({ progress: 0, isUploading: false, error: "Network error during upload." });
          resolve({ error: "Network error during upload." });
        });

        xhr.addEventListener("timeout", () => {
          xhrRef.current = null;
          setState({ progress: 0, isUploading: false, error: "Upload timed out." });
          resolve({ error: "Upload timed out." });
        });

        xhr.open("POST", `${API_URL}/jobs`);
        xhr.timeout = 120_000; // 2 min timeout for large files
        xhr.send(formData);
      });
    },
    []
  );

  const abort = useCallback(() => {
    if (xhrRef.current) {
      xhrRef.current.abort();
      xhrRef.current = null;
      setState({ progress: 0, isUploading: false, error: null });
    }
  }, []);

  return { ...state, upload, abort, isLargeFile: (size: number) => size > LARGE_FILE_THRESHOLD };
}
