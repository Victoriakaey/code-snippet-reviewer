import { describe, expect, it } from "vitest";

import { isMockReviewer } from "./mock";

describe("isMockReviewer", () => {
  it("is true only for the persisted mock provider", () => {
    expect(isMockReviewer("mock")).toBe(true);
    expect(isMockReviewer("ollama")).toBe(false);
    expect(isMockReviewer("openai")).toBe(false);
    expect(isMockReviewer(null)).toBe(false);
    expect(isMockReviewer(undefined)).toBe(false);
  });
});
