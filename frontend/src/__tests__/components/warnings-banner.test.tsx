import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WarningsBanner } from "@/components/result/warnings-banner";

describe("WarningsBanner", () => {
  it("renders nothing when warnings array is empty", () => {
    const { container } = render(<WarningsBanner warnings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when warnings is undefined-like", () => {
    const { container } = render(
      <WarningsBanner warnings={undefined as unknown as string[]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders low_confidence warning message", () => {
    render(<WarningsBanner warnings={["low_confidence"]} />);

    expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
    expect(screen.getByText("Heads up")).toBeInTheDocument();
  });

  it("renders bpm_unreliable warning message", () => {
    render(<WarningsBanner warnings={["bpm_unreliable"]} />);

    expect(screen.getByText(/BPM auto-detection/i)).toBeInTheDocument();
  });

  it("renders multiple warnings", () => {
    render(
      <WarningsBanner warnings={["low_confidence", "bpm_unreliable"]} />
    );

    expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
    expect(screen.getByText(/BPM auto-detection/i)).toBeInTheDocument();
  });

  it("renders unknown warning as-is", () => {
    render(<WarningsBanner warnings={["some_unknown_warning"]} />);

    expect(screen.getByText("some_unknown_warning")).toBeInTheDocument();
  });
});
