import { describe, it, expect } from "vitest";
import {
  INSTRUMENT_COLORS,
  INSTRUMENT_LABELS,
  STATUS_LABELS,
  STATUS_STEP_ORDER,
  WARNING_MESSAGES,
} from "@/lib/constants";

describe("INSTRUMENT_COLORS", () => {
  it("has a color for every instrument", () => {
    const instruments = [
      "kick",
      "snare",
      "hihat_closed",
      "hihat_open",
      "crash",
      "ride",
      "tom_high",
      "tom_mid",
      "tom_low",
    ] as const;

    instruments.forEach((inst) => {
      expect(INSTRUMENT_COLORS[inst]).toBeDefined();
      expect(INSTRUMENT_COLORS[inst]).toMatch(/^#[0-9a-f]{6}$/i);
    });
  });

  it("maps kick to blue", () => {
    expect(INSTRUMENT_COLORS.kick).toBe("#3b82f6");
  });

  it("maps snare to red", () => {
    expect(INSTRUMENT_COLORS.snare).toBe("#ef4444");
  });
});

describe("INSTRUMENT_LABELS", () => {
  it("has a label for every instrument", () => {
    Object.keys(INSTRUMENT_COLORS).forEach((key) => {
      expect(
        INSTRUMENT_LABELS[key as keyof typeof INSTRUMENT_LABELS]
      ).toBeDefined();
      expect(
        INSTRUMENT_LABELS[key as keyof typeof INSTRUMENT_LABELS].length
      ).toBeGreaterThan(0);
    });
  });
});

describe("STATUS_LABELS", () => {
  it("has a label for every status", () => {
    const statuses = [
      "queued",
      "processing",
      "separating_drums",
      "predicting",
      "transcribing",
      "completed",
      "failed",
    ] as const;

    statuses.forEach((s) => {
      expect(STATUS_LABELS[s]).toBeDefined();
    });
  });
});

describe("STATUS_STEP_ORDER", () => {
  it("starts with queued and ends with completed", () => {
    expect(STATUS_STEP_ORDER[0]).toBe("queued");
    expect(STATUS_STEP_ORDER[STATUS_STEP_ORDER.length - 1]).toBe("completed");
  });

  it("has 5 steps", () => {
    expect(STATUS_STEP_ORDER).toHaveLength(5);
  });
});

describe("WARNING_MESSAGES", () => {
  it("has a message for low_confidence", () => {
    expect(WARNING_MESSAGES.low_confidence).toBeDefined();
    expect(WARNING_MESSAGES.low_confidence.length).toBeGreaterThan(0);
  });

  it("has a message for bpm_unreliable", () => {
    expect(WARNING_MESSAGES.bpm_unreliable).toBeDefined();
    expect(WARNING_MESSAGES.bpm_unreliable.length).toBeGreaterThan(0);
  });
});
