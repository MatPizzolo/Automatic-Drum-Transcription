"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { DropZone } from "./drop-zone";
import { YouTubeInput } from "./youtube-input";
import { AdvancedOptions } from "./advanced-options";
import { createJob } from "@/app/actions";
import { useUploadProgress } from "@/hooks/use-upload-progress";
import { BPM_MAX, BPM_MIN } from "@/lib/constants";

export function UploadForm() {
  const router = useRouter();
  const [tab, setTab] = useState<"upload" | "youtube">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [title, setTitle] = useState("");
  const [bpm, setBpm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isPending, startTransition] = useTransition();
  const {
    progress: uploadProgress,
    isUploading,
    upload: xhrUpload,
    isLargeFile,
  } = useUploadProgress();

  const validateBpm = (value: string): string | undefined => {
    if (!value) return undefined;
    const num = Number(value);
    if (isNaN(num) || num < BPM_MIN || num > BPM_MAX) {
      return `BPM must be between ${BPM_MIN} and ${BPM_MAX}`;
    }
    return undefined;
  };

  const handleSubmit = () => {
    setErrors({});

    const bpmError = validateBpm(bpm);
    if (bpmError) {
      setErrors({ bpm: bpmError });
      return;
    }

    if (tab === "upload" && !file) {
      setErrors({ file: "Please select an audio file." });
      return;
    }

    if (tab === "youtube" && !youtubeUrl.trim()) {
      setErrors({ youtube_url: "Please enter a YouTube URL." });
      return;
    }

    const youtubeRegex =
      /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)[a-zA-Z0-9_-]+/;
    if (tab === "youtube" && !youtubeRegex.test(youtubeUrl)) {
      setErrors({ youtube_url: "Please enter a valid YouTube URL." });
      return;
    }

    const formData = new FormData();

    if (tab === "upload" && file) {
      formData.set("file", file);
      formData.set("mode", "upload");
    } else {
      formData.set("youtube_url", youtubeUrl);
      formData.set("mode", "youtube");
    }

    if (title.trim()) formData.set("title", title.trim());
    if (bpm) formData.set("bpm", bpm);

    // Large file uploads use XHR for progress tracking
    if (tab === "upload" && file && isLargeFile(file.size)) {
      const uploadData = new FormData();
      uploadData.set("file", file);
      if (title.trim()) uploadData.set("title", title.trim());
      if (bpm) uploadData.set("bpm", bpm);

      xhrUpload(uploadData).then((result) => {
        if ("error" in result) {
          toast.error(result.error);
          if ("detail" in result && result.detail) {
            setErrors({ form: result.detail });
          }
        } else if ("id" in result) {
          router.push(`/jobs/${result.id}`);
        }
      });
      return;
    }

    // Small files and YouTube use Server Action
    startTransition(async () => {
      const result = await createJob(formData);
      if (result?.error) {
        toast.error(result.error);
        if (result.detail) {
          setErrors({ form: result.detail });
        }
      }
    });
  };

  const isBusy = isPending || isUploading;

  return (
    <div className="w-full space-y-6">
      <Tabs
        value={tab}
        onValueChange={(v) => {
          setTab(v as "upload" | "youtube");
          setErrors({});
        }}
      >
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="upload">Upload File</TabsTrigger>
          <TabsTrigger value="youtube">YouTube URL</TabsTrigger>
        </TabsList>
        <TabsContent value="upload" className="mt-4">
          <DropZone
            file={file}
            onFileSelect={setFile}
            error={errors.file}
          />
        </TabsContent>
        <TabsContent value="youtube" className="mt-4">
          <YouTubeInput
            value={youtubeUrl}
            onChange={setYoutubeUrl}
            error={errors.youtube_url}
          />
        </TabsContent>
      </Tabs>

      <AdvancedOptions
        title={title}
        bpm={bpm}
        onTitleChange={setTitle}
        onBpmChange={setBpm}
        bpmError={errors.bpm}
      />

      {errors.form && (
        <p className="text-sm text-destructive">{errors.form}</p>
      )}

      {isUploading && (
        <div className="space-y-1">
          <Progress value={uploadProgress} className="h-2" />
          <p className="text-xs text-muted-foreground text-center">
            Uploading… {uploadProgress}%
          </p>
        </div>
      )}

      <Button
        onClick={handleSubmit}
        disabled={isBusy}
        className="w-full"
        size="lg"
      >
        {isBusy ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {isUploading ? "Uploading…" : "Processing…"}
          </>
        ) : (
          <>
            <Wand2 className="mr-2 h-4 w-4" />
            Transcribe Drums
          </>
        )}
      </Button>
    </div>
  );
}
