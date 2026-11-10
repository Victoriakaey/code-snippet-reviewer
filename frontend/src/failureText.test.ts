import { describe, expect, it } from "vitest";

import { reviewFailureSentence } from "./failureText";

describe("reviewFailureSentence", () => {
  it("does not double the period when the message already ends in one", () => {
    // Regression: backend messages end in "." and the UI used to append another → "..".
    const out = reviewFailureSentence(1, "The review could not be completed (the model call failed).");
    expect(out).toBe("Review #1 failed: The review could not be completed (the model call failed).");
    expect(out).not.toMatch(/\.\.$/);
  });

  it("adds a single period when the message has no terminal punctuation", () => {
    expect(reviewFailureSentence(2, "connection refused")).toBe(
      "Review #2 failed: connection refused.",
    );
  });

  it("keeps existing ! or ? and does not append a period", () => {
    expect(reviewFailureSentence(3, "timed out!")).toBe("Review #3 failed: timed out!");
    expect(reviewFailureSentence(4, "really?")).toBe("Review #4 failed: really?");
  });

  it("never strips characters from the message (trailing whitespace preserved)", () => {
    expect(reviewFailureSentence(5, "boom.  ")).toBe("Review #5 failed: boom.  ");
  });

  it("falls back to a bare sentence when there is no message", () => {
    expect(reviewFailureSentence(6, null)).toBe("Review #6 failed.");
    expect(reviewFailureSentence(7, "")).toBe("Review #7 failed.");
  });

  it("omits the run number when it is unknown", () => {
    expect(reviewFailureSentence(null, "nope")).toBe("Review failed: nope.");
  });
});
