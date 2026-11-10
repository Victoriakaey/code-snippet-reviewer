// A review is a "mock" (demo) review when its PERSISTED provider is the mock provider.
// Derived from stored provenance, not the current environment setting.
export function isMockReviewer(provider: string | null | undefined): boolean {
  return provider === "mock";
}
