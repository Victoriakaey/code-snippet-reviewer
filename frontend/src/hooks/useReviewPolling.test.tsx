import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, getReview: vi.fn() };
});

import { ApiError, getReview } from "../api";
import type { Review } from "../types";
import { MAX_POLL_FAILURES, useReviewPolling } from "./useReviewPolling";

const mockGet = vi.mocked(getReview);

function review(status: Review["status"]): Review {
  return {
    id: "r1",
    snippet_id: "s1",
    run_number: 1,
    status,
    provider: "mock",
    model_name: "mock-deterministic",
    prompt_version: "v2",
    rubric_version: "v2",
    rejected_finding_count: 0,
    error_message: null,
    created_at: "",
    started_at: null,
    completed_at: null,
    findings: [],
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  mockGet.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useReviewPolling", () => {
  it("stops after MAX_POLL_FAILURES consecutive transient failures and sets pollError", async () => {
    mockGet.mockRejectedValue(new ApiError(500, "server_error", "boom"));
    const { result } = renderHook(() => useReviewPolling("r1", () => {}));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800 * MAX_POLL_FAILURES);
    });

    expect(mockGet).toHaveBeenCalledTimes(MAX_POLL_FAILURES);
    expect(result.current.pollError).toMatch(/couldn't reach the server/i);
  });

  it("stops immediately on a 404 without retrying", async () => {
    mockGet.mockRejectedValue(new ApiError(404, "not_found", "nope"));
    const { result } = renderHook(() => useReviewPolling("r1", () => {}));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800 * 3);
    });

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(result.current.pollError).toMatch(/could not be found/i);
  });

  it("calls onTerminal and stops polling when the review completes", async () => {
    mockGet.mockResolvedValue(review("completed"));
    const onTerminal = vi.fn();
    const { result } = renderHook(() => useReviewPolling("r1", onTerminal));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(onTerminal).toHaveBeenCalledTimes(1);
    expect(result.current.review?.status).toBe("completed");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(mockGet).toHaveBeenCalledTimes(1); // no further polls after terminal
  });

  it("does NOT set pollError when the review itself fails (job failure != poll failure)", async () => {
    mockGet.mockResolvedValue(review("failed"));
    const { result } = renderHook(() => useReviewPolling("r1", () => {}));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.review?.status).toBe("failed");
    expect(result.current.pollError).toBeNull();
  });

  it("retry re-queries the SAME review id and clears pollError", async () => {
    mockGet.mockRejectedValue(new ApiError(500, "server_error", "boom"));
    const { result } = renderHook(() => useReviewPolling("r1", () => {}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800 * MAX_POLL_FAILURES);
    });
    expect(result.current.pollError).toBeTruthy();
    const callsBefore = mockGet.mock.calls.length;

    mockGet.mockResolvedValue(review("running"));
    await act(async () => {
      result.current.retry();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.pollError).toBeNull();
    expect(mockGet.mock.calls.length).toBeGreaterThan(callsBefore);
    expect(mockGet).toHaveBeenLastCalledWith("r1");
  });

  it("stops polling after unmount", async () => {
    mockGet.mockRejectedValue(new ApiError(500, "server_error", "boom"));
    const { unmount } = renderHook(() => useReviewPolling("r1", () => {}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    const callsAtUnmount = mockGet.mock.calls.length;
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(mockGet.mock.calls.length).toBe(callsAtUnmount);
  });

  it("polls the new id when the review id changes", async () => {
    mockGet.mockResolvedValue(review("running"));
    const { rerender } = renderHook(({ id }) => useReviewPolling(id, () => {}), {
      initialProps: { id: "r1" },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    rerender({ id: "r2" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockGet).toHaveBeenLastCalledWith("r2");
  });
});
