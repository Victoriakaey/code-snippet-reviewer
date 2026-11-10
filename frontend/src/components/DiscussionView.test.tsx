import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, getMessages: vi.fn(), postMessage: vi.fn() };
});

import { ApiError, getMessages, postMessage } from "../api";
import type { Finding, FindingMessage } from "../types";
import { DiscussionView } from "./DiscussionView";

const mockGet = vi.mocked(getMessages);
const mockPost = vi.mocked(postMessage);

const finding: Finding = {
  id: "f1",
  line_start: 1,
  line_end: 1,
  severity: "warning",
  category: "bug",
  description: "mutable default arg",
  rationale: "shared across calls",
  suggested_fix: null,
  resolution_status: "open",
  resolution_reason: null,
  resolved_at: null,
};

function msg(role: "user" | "assistant", content: string): FindingMessage {
  return { id: role + content, role, content, provider: role === "assistant" ? "mock" : null, model_name: role === "assistant" ? "mock-deterministic" : null, created_at: "" };
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockGet.mockResolvedValue([]);
});
afterEach(cleanup);

describe("DiscussionView", () => {
  it("sends a question and shows the returned thread", async () => {
    mockPost.mockResolvedValue([msg("user", "why?"), msg("assistant", "because X")]);
    render(<DiscussionView finding={finding} readOnly={false} onBack={() => {}} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText(/ask about this finding/i), { target: { value: "why?" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Send"));
    });

    expect(mockPost).toHaveBeenCalledWith("f1", "why?");
    expect(screen.getByText("because X")).toBeInTheDocument();
    expect(screen.getByText(/AI · mock-deterministic/)).toBeInTheDocument();
  });

  it("guards against duplicate sends while a request is in flight", async () => {
    let resolve!: (v: FindingMessage[]) => void;
    mockPost.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<DiscussionView finding={finding} readOnly={false} onBack={() => {}} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText(/ask about this finding/i), { target: { value: "q" } });
    fireEvent.click(screen.getByText("Send"));
    // Button now shows "Sending…" and is disabled — a second click does nothing.
    const btn = screen.getByRole("button", { name: /sending/i });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(mockPost).toHaveBeenCalledTimes(1);

    await act(async () => resolve([msg("user", "q"), msg("assistant", "a")]));
  });

  it("shows a retryable error on send failure without losing the draft conversation", async () => {
    mockPost.mockRejectedValue(new ApiError(503, "discuss_failed", "Please retry."));
    render(<DiscussionView finding={finding} readOnly={false} onBack={() => {}} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText(/ask about this finding/i), { target: { value: "q" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Send"));
    });
    expect(screen.getByText(/please retry/i)).toBeInTheDocument();
  });

  it("is read-only for a historical finding (no input)", async () => {
    render(<DiscussionView finding={finding} readOnly={true} onBack={() => {}} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(screen.queryByPlaceholderText(/ask about this finding/i)).toBeNull();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });
});
