import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBadge } from "@/components/result/confidence-badge";

describe("ConfidenceBadge", () => {
  it("renders high confidence for score >= 0.8", () => {
    render(<ConfidenceBadge score={0.92} />);

    expect(screen.getByText(/high confidence/i)).toBeInTheDocument();
    expect(screen.getByText(/92%/)).toBeInTheDocument();
  });

  it("renders medium confidence for score 0.5-0.79", () => {
    render(<ConfidenceBadge score={0.65} />);

    expect(screen.getByText(/medium confidence/i)).toBeInTheDocument();
    expect(screen.getByText(/65%/)).toBeInTheDocument();
  });

  it("renders low confidence for score < 0.5", () => {
    render(<ConfidenceBadge score={0.3} />);

    expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
    expect(screen.getByText(/30%/)).toBeInTheDocument();
  });

  it("renders exactly at boundary 0.8 as high", () => {
    render(<ConfidenceBadge score={0.8} />);
    expect(screen.getByText(/high confidence/i)).toBeInTheDocument();
  });

  it("renders exactly at boundary 0.5 as medium", () => {
    render(<ConfidenceBadge score={0.5} />);
    expect(screen.getByText(/medium confidence/i)).toBeInTheDocument();
  });

  it("rounds percentage correctly", () => {
    render(<ConfidenceBadge score={0.876} />);
    expect(screen.getByText(/88%/)).toBeInTheDocument();
  });
});
