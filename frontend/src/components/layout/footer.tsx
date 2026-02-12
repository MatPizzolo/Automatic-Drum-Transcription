export function Footer() {
  return (
    <footer className="border-t border-border/40 py-6">
      <div className="mx-auto max-w-5xl px-4 sm:px-6">
        <p className="text-center text-sm text-muted-foreground">
          &copy; {new Date().getFullYear()} DrumScribe. AI-powered drum
          transcription.
        </p>
      </div>
    </footer>
  );
}
