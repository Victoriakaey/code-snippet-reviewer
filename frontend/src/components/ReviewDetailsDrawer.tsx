import { useEffect, useState } from "react";

import { getRubric } from "../api";
import type { ReviewStatus, ReviewSummary, Rubric } from "../types";

interface Props {
  review: ReviewSummary;
  onClose: () => void;
}

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

// Fields absent on an older/failed run are shown as "Unavailable" — never backfilled
// from another run's values (per the Review-details semantics fix).
function fieldOr(value: string | null | undefined): string {
  return value && value.length > 0 ? value : "Unavailable";
}
function timeOr(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "Unavailable";
}

export function ReviewDetailsDrawer({ review, onClose }: Props) {
  const [rubric, setRubric] = useState<Rubric | null>(null);

  useEffect(() => {
    let active = true;
    getRubric().then((r) => active && setRubric(r)).catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const versionMismatch =
    rubric && review.rubric_version && rubric.rubric_version !== review.rubric_version;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="ghost sm" style={{ float: "right" }} onClick={onClose}>
          Close
        </button>
        <h3>Review details</h3>

        <dl className="kv">
          <dt>Run</dt>
          <dd>#{review.run_number}</dd>
          <dt>Status</dt>
          <dd>{REVIEW_STATUS_LABEL[review.status as ReviewStatus] ?? review.status}</dd>
          <dt>Provider</dt>
          <dd>{fieldOr(review.provider)}</dd>
          <dt>Model</dt>
          <dd>{fieldOr(review.model_name)}</dd>
          <dt>Prompt</dt>
          <dd>{fieldOr(review.prompt_version)}</dd>
          <dt>Rubric</dt>
          <dd>{fieldOr(review.rubric_version)}</dd>
          <dt>Started at</dt>
          <dd>{timeOr(review.started_at)}</dd>
          <dt>Completed at</dt>
          <dd>{timeOr(review.completed_at)}</dd>
        </dl>

        {review.status === "failed" && (
          <div className="error-box" style={{ margin: "10px 0" }}>
            {fieldOr(review.error_message) === "Unavailable"
              ? "This run failed. No error detail was recorded."
              : review.error_message}
          </div>
        )}

        {versionMismatch && (
          <div className="historical-note" style={{ margin: "10px 0" }}>
            This review ran under rubric {review.rubric_version}. The rubric shown below is the
            current version ({rubric?.rubric_version}) and may differ from the one used then.
          </div>
        )}

        <h3 style={{ marginTop: 20 }}>Rubric {rubric ? `(${rubric.rubric_version})` : ""}</h3>
        {!rubric && <div className="muted">Loading rubric…</div>}
        {rubric && (
          <>
            <h5 style={{ color: "var(--muted)", fontSize: 12 }}>Dimensions</h5>
            <ul style={{ paddingLeft: 18, fontSize: 13 }}>
              {rubric.dimensions.map((d) => (
                <li key={d.category}>
                  <strong>{d.category}</strong> — {d.description}
                </li>
              ))}
            </ul>
            <h5 style={{ color: "var(--muted)", fontSize: 12 }}>Severity</h5>
            <ul style={{ paddingLeft: 18, fontSize: 13 }}>
              {rubric.severities.map((s) => (
                <li key={s.severity}>
                  <strong>{s.severity}</strong> — {s.definition}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
