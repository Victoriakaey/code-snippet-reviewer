import { useState } from "react";

import { patchFinding, ApiError } from "../api";
import type { Finding, ResolutionStatus } from "../types";
import { SeverityBadge } from "./badges";

interface Props {
  findings: Finding[];
  codeLines: string[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  readOnly: boolean;
  onResolved: (updated: Finding) => void;
}

export function FindingsPanel({
  findings,
  codeLines,
  selectedId,
  onSelect,
  readOnly,
  onResolved,
}: Props) {
  if (findings.length === 0) {
    return <div className="empty">No findings in this review.</div>;
  }
  return (
    <div>
      {findings.map((f) => (
        <FindingItem
          key={f.id}
          finding={f}
          codeLines={codeLines}
          selected={selectedId === f.id}
          onSelect={() => onSelect(f.id)}
          readOnly={readOnly}
          onResolved={onResolved}
        />
      ))}
    </div>
  );
}

function evidence(codeLines: string[], start: number, end: number): string {
  return codeLines
    .slice(start - 1, end)
    .map((line, i) => `${start + i}  ${line}`)
    .join("\n");
}

interface ItemProps {
  finding: Finding;
  codeLines: string[];
  selected: boolean;
  onSelect: () => void;
  readOnly: boolean;
  onResolved: (updated: Finding) => void;
}

function FindingItem({ finding, codeLines, selected, onSelect, readOnly, onResolved }: ItemProps) {
  const [reason, setReason] = useState(finding.resolution_reason ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resolve(status: ResolutionStatus) {
    setBusy(true);
    setError(null);
    try {
      const updated = await patchFinding(finding.id, {
        resolution_status: status,
        resolution_reason: status === "open" ? null : reason.trim() || null,
      });
      onResolved(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const resolved = finding.resolution_status !== "open";

  return (
    <div className={`finding${selected ? " selected" : ""}${resolved ? " resolved" : ""}`}>
      <div className="finding-head" onClick={onSelect}>
        <SeverityBadge severity={finding.severity} />
        <span className="badge cat-badge">{finding.category}</span>
        <span className="finding-title">{finding.description}</span>
        {finding.resolution_status === "accepted" && (
          <span className="res-pill res-accepted">accepted</span>
        )}
        {finding.resolution_status === "dismissed" && (
          <span className="res-pill res-dismissed">dismissed</span>
        )}
        <span className="finding-line">
          L{finding.line_start}
          {finding.line_end !== finding.line_start ? `–${finding.line_end}` : ""}
        </span>
      </div>

      {selected && (
        <div className="finding-body">
          <h5>What</h5>
          <div>{finding.description}</div>
          {finding.rationale && (
            <>
              <h5>Why it matters</h5>
              <div>{finding.rationale}</div>
            </>
          )}
          <h5>Evidence (from the snippet)</h5>
          <pre>{evidence(codeLines, finding.line_start, finding.line_end)}</pre>
          {finding.suggested_fix && (
            <>
              <h5>Suggested fix</h5>
              <div>{finding.suggested_fix}</div>
            </>
          )}

          {readOnly ? (
            <div className="historical-note" style={{ marginTop: 12 }}>
              Historical review — read-only. Run a new review to resolve findings.
            </div>
          ) : (
            <div className="resolution-row">
              <input
                className="reason"
                placeholder="Optional reason…"
                maxLength={1000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={busy}
              />
              <button
                className="sm"
                disabled={busy || finding.resolution_status === "accepted"}
                onClick={() => resolve("accepted")}
              >
                Accept
              </button>
              <button
                className="sm"
                disabled={busy || finding.resolution_status === "dismissed"}
                onClick={() => resolve("dismissed")}
              >
                Dismiss
              </button>
              <button
                className="sm ghost"
                disabled={busy || !resolved}
                onClick={() => resolve("open")}
              >
                Reopen
              </button>
            </div>
          )}
          {error && <div className="error-box" style={{ marginTop: 8 }}>{error}</div>}
        </div>
      )}
    </div>
  );
}
