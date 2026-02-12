import { test, expect } from "@playwright/test";

test.describe("Landing Page", () => {
  test("renders hero and upload form", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /drum sheet music/i })
    ).toBeVisible();

    await expect(page.getByText("DrumScribe")).toBeVisible();

    await expect(page.getByRole("tab", { name: /upload file/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /youtube url/i })).toBeVisible();

    await expect(
      page.getByRole("button", { name: /transcribe drums/i })
    ).toBeVisible();
  });

  test("switches between upload and youtube tabs", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("tab", { name: /youtube url/i }).click();
    await expect(
      page.getByPlaceholder(/youtube\.com/)
    ).toBeVisible();

    await page.getByRole("tab", { name: /upload file/i }).click();
    await expect(page.getByText(/drag & drop/i)).toBeVisible();
  });

  test("shows how it works section", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText("How it works")).toBeVisible();
    await expect(page.getByText("1. Upload")).toBeVisible();
    await expect(page.getByText("2. AI Processing")).toBeVisible();
    await expect(page.getByText("3. Sheet Music")).toBeVisible();
  });

  test("shows validation error when submitting without file", async ({
    page,
  }) => {
    await page.goto("/");

    await page.getByRole("button", { name: /transcribe drums/i }).click();

    // Should show an error since no file is selected
    await expect(page.getByText(/please select/i)).toBeVisible({
      timeout: 3000,
    });
  });

  test("shows validation error for invalid youtube URL", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("tab", { name: /youtube url/i }).click();
    await page.getByPlaceholder(/youtube\.com/).fill("not-a-url");
    await page.getByRole("button", { name: /transcribe drums/i }).click();

    await expect(page.getByText(/valid youtube url/i)).toBeVisible({
      timeout: 3000,
    });
  });

  test("theme toggle works", async ({ page }) => {
    await page.goto("/");

    const html = page.locator("html");

    // Default is dark
    await expect(html).toHaveClass(/dark/);

    // Click toggle
    await page.getByRole("button", { name: /toggle theme/i }).click();

    // Should switch to light
    await expect(html).not.toHaveClass(/dark/, { timeout: 2000 });
  });

  test("404 page renders", async ({ page }) => {
    await page.goto("/nonexistent-page");

    await expect(page.getByText(/page not found/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /go home/i })).toBeVisible();
  });
});
