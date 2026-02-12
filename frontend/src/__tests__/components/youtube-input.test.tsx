import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { YouTubeInput } from "@/components/upload/youtube-input";

describe("YouTubeInput", () => {
  it("renders input with placeholder", () => {
    render(<YouTubeInput value="" onChange={vi.fn()} />);

    expect(
      screen.getByPlaceholderText(/youtube\.com/)
    ).toBeInTheDocument();
  });

  it("displays the current value", () => {
    render(
      <YouTubeInput
        value="https://youtube.com/watch?v=abc"
        onChange={vi.fn()}
      />
    );

    expect(screen.getByDisplayValue("https://youtube.com/watch?v=abc")).toBeInTheDocument();
  });

  it("calls onChange when user types", () => {
    const onChange = vi.fn();
    render(<YouTubeInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByRole("textbox", { name: /youtube url/i }), {
      target: { value: "https://youtu.be/test" },
    });

    expect(onChange).toHaveBeenCalledWith("https://youtu.be/test");
  });

  it("shows error message when error prop is set", () => {
    render(
      <YouTubeInput
        value=""
        onChange={vi.fn()}
        error="Please enter a valid YouTube URL."
      />
    );

    expect(
      screen.getByText("Please enter a valid YouTube URL.")
    ).toBeInTheDocument();
  });

  it("does not show error when no error prop", () => {
    render(<YouTubeInput value="" onChange={vi.fn()} />);

    expect(
      screen.queryByText(/valid youtube/i)
    ).not.toBeInTheDocument();
  });
});
