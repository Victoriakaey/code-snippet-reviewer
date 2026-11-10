import { useEffect, useRef, useState } from "react";

import { getReview } from "../api";
import type { Review } from "../types";

/**
 * Poll a review until it reaches a terminal state. Non-overlapping: the next request is
 * scheduled only after the previous one resolves. On unmount or when `reviewId` changes,
 * the loop is cancelled and any in-flight response is ignored, so a stale response can
 * never overwrite the state of a newer page.
 */
export function useReviewPolling(
  reviewId: string | null,
  onTerminal: (review: Review) => void,
): Review | null {
  const [review, setReview] = useState<Review | null>(null);
  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;

  useEffect(() => {
    if (!reviewId) {
      setReview(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const r = await getReview(reviewId);
        if (cancelled) return;
        setReview(r);
        if (r.status === "completed" || r.status === "failed") {
          onTerminalRef.current(r);
          return; // stop polling
        }
      } catch {
        if (cancelled) return; // transient error — keep trying
      }
      if (!cancelled) timer = window.setTimeout(poll, 800);
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [reviewId]);

  return review;
}
