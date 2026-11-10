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
    <div className="findings-list">
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

  const status = finding.resolution_status;
  const lineRef =
    finding.line_end !== finding.line_start
      ? `Lines ${finding.line_start}–${finding.line_end}`
      : `Line ${finding.line_start}`;

  return (
    <div className={`finding${selected ? " selected" : ""}${status !== "open" ? " resolved" : ""}`}>
      <button className="finding-head" onClick={onSelect} aria-expanded={selected}>
        <div className="finding-meta">
          <SeverityBadge severity={finding.severity} />
          <span className="badge cat-badge">{finding.category}</span>
          {status === "accepted" && <span className="res-pill res-accepted">Accepted</span>}
          {status === "dismissed" && <span className="res-pill res-dismissed">Dismissed</span>}
          <span className="finding-line">{lineRef}</span>
        </div>
        <div className="finding-title">{finding.description}</div>
      </button>

      {selected && (
        <div className="finding-body">
          {finding.rationale && (
            <section className="finding-section">
              <h5>Why it matters</h5>
              <p>{finding.rationale}</p>
            </section>
          )}
          <section className="finding-section">
            <h5>Evidence</h5>
            <pre>{evidence(codeLines, finding.line_start, finding.line_end)}</pre>
          </section>
          {finding.suggested_fix && (
            <section className="finding-section">
              <h5>Suggested fix</h5>
              <p>{finding.suggested_fix}</p>
            </section>
          )}

          <section className="finding-section resolution">
            <h5>Resolution</h5>
            {readOnly ? (
              <div className="historical-note">
                Historical review — read-only. Run a new review to resolve findings.
              </div>
            ) : (
              <Resolution
                status={status}
                reason={reason}
                busy={busy}
                setReason={setReason}
                resolve={resolve}
              />
            )}
            {error && <div className="error-box" style={{ marginTop: 8 }}>{error}</div>}
          </section>
        </div>
      )}
    </div>
  );
}

interface ResolutionProps {
  status: ResolutionStatus;
  reason: string;
  busy: boolean;
  setReason: (v: string) => void;
  resolve: (status: ResolutionStatus) => void;
}

function Resolution({ status, reason, busy, setReason, resolve }: ResolutionProps) {
  const reasonInput = (
    <input
      className="reason"
      placeholder="Optional reason…"
      maxLength={1000}
      value={reason}
      onChange={(e) => setReason(e.target.value)}
      disabled={busy}
    />
  );

  if (status === "open") {
    return (
      <div className="resolution-controls">
        {reasonInput}
        <div className="resolution-buttons">
          <button className="sm" disabled={busy} onClick={() => resolve("accepted")}>
            Accept
          </button>
          <button className="sm" disabled={busy} onClick={() => resolve("dismissed")}>
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  // Already resolved: show the decision, let the reason be edited, and offer the opposite
  // decision + reopen. (Backend: same-status + new reason is an idempotent reason edit.)
  const other: ResolutionStatus = status === "accepted" ? "dismissed" : "accepted";
  const otherLabel = other === "accepted" ? "Accept instead" : "Dismiss instead";
  return (
    <div className="resolution-controls">
      {reasonInput}
      <div className="resolution-buttons">
        <button className="sm" disabled={busy} onClick={() => resolve(status)}>
          Save reason
        </button>
        <button className="sm" disabled={busy} onClick={() => resolve(other)}>
          {otherLabel}
        </button>
        <button className="sm ghost" disabled={busy} onClick={() => resolve("open")}>
          Reopen
        </button>
      </div>
    </div>
  );
}
