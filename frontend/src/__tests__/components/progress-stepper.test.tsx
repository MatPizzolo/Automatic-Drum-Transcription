import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProgressStepper } from "@/components/processing/progress-stepper";
import type { JobStatus } from "@/types/api";

// Mock framer-motion to render plain divs
vi.mock("framer-motion", () => ({
  motion: {
    div: ({
      children,
      className,
      animate,
      transition,
      ...rest
    }: React.HTMLAttributes<HTMLDivElement> & {
      animate?: unknown;
      transition?: unknown;
    }) => (
      <div className={className} {...rest}>
        {children}
      </div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

// Mock hooks
vi.mock("@/hooks/use-media-query", () => ({
  useMediaQuery: () => true,
}));

vi.mock("@/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => false,
}));

describe("ProgressStepper", () => {
  it("renders all 5 step labels", () => {
    render(<ProgressStepper currentStatus="queued" />);

    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Separating Drums")).toBeInTheDocument();
    expect(screen.getByText("Predicting Hits")).toBeInTheDocument();
    expect(screen.getByText("Building Sheet Music")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("has progressbar role", () => {
    render(<ProgressStepper currentStatus="queued" />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("sets aria-valuenow=1 for queued status", () => {
    render(<ProgressStepper currentStatus="queued" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "1");
  });

  it("sets aria-valuenow=2 for separating_drums status", () => {
    render(<ProgressStepper currentStatus="separating_drums" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "2");
  });

  it("sets aria-valuenow=3 for predicting status", () => {
    render(<ProgressStepper currentStatus="predicting" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "3");
  });

  it("sets aria-valuenow=4 for transcribing status", () => {
    render(<ProgressStepper currentStatus="transcribing" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "4");
  });

  it("sets aria-valuenow=5 for completed status", () => {
    render(<ProgressStepper currentStatus="completed" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "5");
  });

  it("marks the active step with aria-current=step", () => {
    render(<ProgressStepper currentStatus="predicting" />);

    const steps = screen.getAllByText(
      /Queued|Separating Drums|Predicting Hits|Building Sheet Music|Done/
    );

    // Find the parent div with aria-current for "Predicting Hits"
    const predictingStep = screen
      .getByText("Predicting Hits")
      .closest("[aria-current]");
    expect(predictingStep).toHaveAttribute("aria-current", "step");

    // Other steps should not have aria-current
    const queuedStep = screen.getByText("Queued").closest("div");
    expect(queuedStep).not.toHaveAttribute("aria-current");
  });

  it("sets aria-valuemax to 5", () => {
    render(<ProgressStepper currentStatus="queued" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemax", "5");
  });

  it("sets aria-valuemin to 1", () => {
    render(<ProgressStepper currentStatus="queued" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemin", "1");
  });

  it("handles failed status (aria-valuenow=0 since failed is not in step order)", () => {
    render(<ProgressStepper currentStatus="failed" />);
    const bar = screen.getByRole("progressbar");
    // failed is not in STATUS_STEP_ORDER, indexOf returns -1, so valuenow = 0
    expect(bar).toHaveAttribute("aria-valuenow", "0");
  });
});
