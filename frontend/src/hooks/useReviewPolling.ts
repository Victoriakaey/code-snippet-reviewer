import { useEffect, useRef, useState } from "react";

import { getReview, ApiError } from "../api";
import type { Review } from "../types";

export const MAX_POLL_FAILURES = 5;

export interface PollingState {
  review: Review | null;
  /** Set when polling GAVE UP (retry cap hit, or a 404). This is a status-check failure, NOT
   *  a review-execution failure — the backend job may still be running. */
  pollError: string | null;
  /** Re-query the SAME review id. Never creates a new review. */
  retry: () => void;
}

/**
 * Poll a review until it reaches a terminal state, with bounded failure handling:
 * - non-overlapping (next request scheduled only after the previous resolves);
 * - a definite 404 stops immediately (not a transient error);
 * - up to MAX_POLL_FAILURES consecutive transient failures, then stop with a pollError;
 * - a successful poll resets the failure count and clears pollError;
 * - cleanup cancels the loop and ignores in-flight responses on unmount or id change.
 *
 * A pollError is kept distinct from `review.status === "failed"`: a network/status-check
 * failure must not be shown as "the review failed".
 */
export function useReviewPolling(
  reviewId: string | null,
  onTerminal: (review: Review) => void,
): PollingState {
  const [review, setReview] = useState<Review | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bumping this restarts polling (manual retry)
  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;

  function retry() {
    setPollError(null);
    setAttempt((a) => a + 1);
  }

  useEffect(() => {
    if (!reviewId) {
      setReview(null);
      setPollError(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    let failures = 0;

    const poll = async () => {
      try {
        const r = await getReview(reviewId);
        if (cancelled) return;
        failures = 0;
        setReview(r);
        setPollError(null);
        if (r.status === "completed" || r.status === "failed") {
          onTerminalRef.current(r);
          return; // terminal — stop
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setPollError("This review could not be found.");
          return; // definite — stop, do not retry
        }
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          setPollError(
            "We couldn't reach the server after several attempts. Your review may still be running.",
          );
          return; // give up auto-polling; user can retry
        }
      }
      if (!cancelled) timer = window.setTimeout(poll, 800);
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [reviewId, attempt]);

  return { review, pollError, retry };
}
