import { Upload, BrainCircuit, Music } from "lucide-react";
import { UploadForm } from "@/components/upload/upload-form";

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6">
      {/* Hero */}
      <section className="flex flex-col items-center py-16 text-center sm:py-24">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
          Turn any song into{" "}
          <span className="text-primary">drum sheet music</span>{" "}
          with AI
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted-foreground">
          Upload an audio file or paste a YouTube URL. DrumScribe uses AI to
          detect every kick, snare, and hi-hat — then generates professional
          drum notation you can download as PDF or MusicXML.
        </p>
      </section>

      {/* Upload Form */}
      <section className="mx-auto max-w-lg pb-16">
        <UploadForm />
      </section>

      {/* How it works */}
      <section className="border-t border-border/40 py-16">
        <h2 className="mb-10 text-center text-2xl font-semibold">
          How it works
        </h2>
        <div className="grid gap-8 sm:grid-cols-3">
          <div className="flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <Upload className="h-6 w-6 text-primary" />
            </div>
            <h3 className="font-medium">1. Upload</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Drop an audio file or paste a YouTube link. We support WAV, MP3,
              FLAC, and OGG.
            </p>
          </div>
          <div className="flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <BrainCircuit className="h-6 w-6 text-primary" />
            </div>
            <h3 className="font-medium">2. AI Processing</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Our model separates the drum track, detects every hit, and
              identifies each instrument.
            </p>
          </div>
          <div className="flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <Music className="h-6 w-6 text-primary" />
            </div>
            <h3 className="font-medium">3. Sheet Music</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Get professional drum notation rendered in your browser. Download
              as PDF or MusicXML.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
