import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// CodeMirror is heavy/fragile in jsdom and irrelevant here — stub it out.
vi.mock("../components/CodeEditor", () => ({ CodeEditor: () => null }));
vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getSnippet: vi.fn(),
    listSnippetReviews: vi.fn(),
    getReview: vi.fn(),
    getMessages: vi.fn(),
    getRubric: vi.fn(),
  };
});

import { getReview, getSnippet, listSnippetReviews } from "../api";
import type { Finding, Review, ReviewRun, ReviewSummary, SnippetDetail as Detail } from "../types";
import { SnippetDetail } from "./SnippetDetail";

const mockGetSnippet = vi.mocked(getSnippet);
const mockListRuns = vi.mocked(listSnippetReviews);
const mockGetReview = vi.mocked(getReview);

function finding(id: string, desc: string): Finding {
  return {
    id, line_start: 1, line_end: 1, severity: "warning", category: "bug",
    description: desc, rationale: "r", suggested_fix: null,
    resolution_status: "open", resolution_reason: null, resolved_at: null,
  };
}
function summary(id: string, run: number, status: ReviewSummary["status"]): ReviewSummary {
  return {
    id, run_number: run, status, provider: "ollama", model_name: "qwen2.5-coder:7b",
    prompt_version: "v2", rubric_version: "B", rejected_finding_count: 0,
    error_message: null, created_at: "", started_at: "", completed_at: "",
  };
}
function run(id: string, n: number, status: ReviewRun["status"], fc: number): ReviewRun {
  return { id, run_number: n, status, provider: "ollama", model_name: "qwen2.5-coder:7b", error_message: null, created_at: "", completed_at: "", finding_count: fc };
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/snippets/s1"]}>
      <Routes>
        <Route path="/snippets/:id" element={<SnippetDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockGetSnippet.mockReset();
  mockListRuns.mockReset();
  mockGetReview.mockReset();
  // Latest = run #2 (completed), its finding is editable by default.
  const latest = summary("r2", 2, "completed");
  mockGetSnippet.mockResolvedValue({
    id: "s1", title: "T", language: "python", code: "x = 1\n", created_at: "",
    status: "reviewed", latest_review: latest, displayed_review: latest,
    findings: [finding("f2", "Latest finding")],
  } satisfies Detail);
  mockListRuns.mockResolvedValue([run("r2", 2, "completed", 1), run("r1", 1, "completed", 1)]);
  mockGetReview.mockResolvedValue({
    ...summary("r1", 1, "completed"), snippet_id: "s1", findings: [finding("f1", "Old finding")],
  } as Review);
});
afterEach(cleanup);

describe("SnippetDetail review-run selector", () => {
  it("defaults to the latest run (editable), and shows a run pill per run when >1 run exists", async () => {
    renderDetail();
    await waitFor(() => expect(screen.getByText("Latest finding")).toBeInTheDocument());
    // One pill button per run; the latest one is marked current (aria-pressed).
    const latestPill = screen.getByRole("button", { name: /^#2\b/ });
    expect(latestPill).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^#1\b/ })).toBeInTheDocument();
    expect(screen.queryByText(/historical run — read-only/i)).toBeNull();
  });

  it("selecting an older run pill loads it read-only and shows that run's findings", async () => {
    renderDetail();
    await waitFor(() => expect(screen.getByText("Latest finding")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^#1\b/ }));

    await waitFor(() => expect(mockGetReview).toHaveBeenCalledWith("r1"));
    await waitFor(() => expect(screen.getByText("Old finding")).toBeInTheDocument());
    // The older run's findings replace the latest ones, the read-only note shows, and its pill
    // becomes the current (pressed) one.
    expect(screen.queryByText("Latest finding")).toBeNull();
    expect(screen.getByText(/historical run — read-only/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^#1\b/ })).toHaveAttribute("aria-pressed", "true");

    // Expanding the historical finding offers "View discussion" (read-only), not resolve controls.
    fireEvent.click(screen.getByText("Old finding"));
    expect(screen.getByText(/view discussion/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Accept$/)).toBeNull();
  });

  it("clicking the latest run pill restores the default (editable) view", async () => {
    renderDetail();
    await waitFor(() => expect(screen.getByText("Latest finding")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^#1\b/ }));
    await waitFor(() => expect(screen.getByText("Old finding")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^#2\b/ }));
    await waitFor(() => expect(screen.getByText("Latest finding")).toBeInTheDocument());
    expect(screen.queryByText("Old finding")).toBeNull();
    expect(screen.queryByText(/historical run — read-only/i)).toBeNull();
    // Latest finding is editable: expanding it offers resolve controls.
    fireEvent.click(screen.getByText("Latest finding"));
    expect(screen.getByText("Accept")).toBeInTheDocument();
  });
});
