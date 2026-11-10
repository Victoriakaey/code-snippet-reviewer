import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, listSnippets: vi.fn() };
});

import { listSnippets } from "../api";
import type { SnippetRow } from "../types";
import { Dashboard } from "./Dashboard";

const mockList = vi.mocked(listSnippets);

function row(over: Partial<SnippetRow>): SnippetRow {
  return {
    id: "s", title: "t", language: "python", code: "", created_at: new Date().toISOString(),
    status: "not_reviewed", reviewer: null, reviewer_provider: null,
    finding_count: 0, review_count: 0, ...over,
  };
}

beforeEach(() => mockList.mockReset());
afterEach(cleanup);

describe("Dashboard Reviews column", () => {
  it("shows a Reviews column with each snippet's run count, distinct from findings", async () => {
    mockList.mockResolvedValue([
      row({ id: "a", title: "Thrice", status: "reviewed", reviewer: "qwen", reviewer_provider: "ollama", review_count: 3, finding_count: 2 }),
      row({ id: "b", title: "Never", status: "not_reviewed", review_count: 0, finding_count: 0 }),
    ]);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Thrice")).toBeInTheDocument());

    expect(screen.getByRole("columnheader", { name: "Reviews" })).toBeInTheDocument();

    // Reviewed-thrice row: 3 runs AND 2 findings both visible (distinct columns).
    const thrice = screen.getByText("Thrice").closest("tr")!;
    expect(within(thrice).getByText("3")).toBeInTheDocument();
    expect(within(thrice).getByText("2")).toBeInTheDocument();

    // Never-reviewed row: review count shows 0 (not "—"); findings shows "—".
    const never = screen.getByText("Never").closest("tr")!;
    expect(within(never).getByText("0")).toBeInTheDocument(); // review count shows 0, not a dash
    expect(within(never).getAllByText("—").length).toBeGreaterThanOrEqual(1); // findings dash
  });
});
