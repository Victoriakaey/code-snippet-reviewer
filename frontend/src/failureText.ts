/**
 * Compose the "Review #N failed[: message]" sentence without doubling end punctuation.
 *
 * Backend failure messages already end in a period (see app/worker.py `_SAFE_ERROR`),
 * so the UI must not blindly append its own. We add a trailing period ONLY when the
 * message does not already end in sentence punctuation. We never strip characters from
 * the message itself — an arbitrary error string is shown verbatim.
 */
export function reviewFailureSentence(
  runNumber: number | null | undefined,
  message: string | null | undefined,
): string {
  const head = runNumber == null ? "Review failed" : `Review #${runNumber} failed`;
  if (!message) return `${head}.`;
  const endsWithPunct = /[.!?]\s*$/.test(message);
  return `${head}: ${message}${endsWithPunct ? "" : "."}`;
}
