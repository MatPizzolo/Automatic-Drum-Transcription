import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DropZone } from "@/components/upload/drop-zone";

describe("DropZone", () => {
  it("renders empty state with instructions", () => {
    render(<DropZone file={null} onFileSelect={vi.fn()} />);

    expect(screen.getByText(/drag & drop/i)).toBeInTheDocument();
    expect(screen.getByText(/WAV, MP3, FLAC, OGG/)).toBeInTheDocument();
  });

  it("renders file info when a file is selected", () => {
    const file = new File(["audio"], "my-song.mp3", { type: "audio/mpeg" });
    Object.defineProperty(file, "size", { value: 1024 * 1024 * 3 });

    render(<DropZone file={file} onFileSelect={vi.fn()} />);

    expect(screen.getByText("my-song.mp3")).toBeInTheDocument();
    expect(screen.getByText("3 MB")).toBeInTheDocument();
  });

  it("shows remove button when file is selected", () => {
    const file = new File(["audio"], "track.wav", { type: "audio/wav" });
    render(<DropZone file={file} onFileSelect={vi.fn()} />);

    expect(
      screen.getByRole("button", { name: /remove file/i })
    ).toBeInTheDocument();
  });

  it("calls onFileSelect(null) when remove button is clicked", () => {
    const file = new File(["audio"], "track.wav", { type: "audio/wav" });
    const onFileSelect = vi.fn();
    render(<DropZone file={file} onFileSelect={onFileSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /remove file/i }));
    expect(onFileSelect).toHaveBeenCalledWith(null);
  });

  it("renders error message when error prop is set", () => {
    render(
      <DropZone
        file={null}
        onFileSelect={vi.fn()}
        error="Please select an audio file."
      />
    );

    expect(
      screen.getByText("Please select an audio file.")
    ).toBeInTheDocument();
  });

  it("has keyboard-accessible drop zone", () => {
    render(<DropZone file={null} onFileSelect={vi.fn()} />);

    const dropZone = screen.getByRole("button", {
      name: /drop audio file here/i,
    });
    expect(dropZone).toHaveAttribute("tabindex", "0");
  });
});
