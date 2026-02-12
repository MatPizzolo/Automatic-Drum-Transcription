import { describe, it, expect } from "vitest";
import { formatDuration, formatBytes, formatComputeTime } from "@/lib/utils";

describe("formatDuration", () => {
  it("formats 0 seconds", () => {
    expect(formatDuration(0)).toBe("0:00");
  });

  it("formats seconds under a minute", () => {
    expect(formatDuration(45)).toBe("0:45");
  });

  it("formats exact minutes", () => {
    expect(formatDuration(120)).toBe("2:00");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(185)).toBe("3:05");
  });

  it("pads single-digit seconds", () => {
    expect(formatDuration(63)).toBe("1:03");
  });

  it("handles fractional seconds by flooring", () => {
    expect(formatDuration(90.7)).toBe("1:30");
  });
});

describe("formatBytes", () => {
  it("formats 0 bytes", () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it("formats bytes", () => {
    expect(formatBytes(500)).toBe("500 B");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(1024)).toBe("1 KB");
  });

  it("formats megabytes", () => {
    expect(formatBytes(1048576)).toBe("1 MB");
  });

  it("formats fractional megabytes", () => {
    expect(formatBytes(5242880)).toBe("5 MB");
  });

  it("formats large files", () => {
    expect(formatBytes(52428800)).toBe("50 MB");
  });
});

describe("formatComputeTime", () => {
  it("formats milliseconds to seconds", () => {
    expect(formatComputeTime(1500)).toBe("1.5s");
  });

  it("formats zero", () => {
    expect(formatComputeTime(0)).toBe("0.0s");
  });

  it("formats large values", () => {
    expect(formatComputeTime(45200)).toBe("45.2s");
  });
});
