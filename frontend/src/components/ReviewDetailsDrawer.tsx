import { useEffect, useState } from "react";

import { getRubric } from "../api";
import type { ReviewSummary, Rubric } from "../types";

interface Props {
  review: ReviewSummary;
  onClose: () => void;
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
          <dt>Provider</dt>
          <dd>{review.provider ?? "—"}</dd>
          <dt>Model</dt>
          <dd>{review.model_name ?? "—"}</dd>
          <dt>Prompt</dt>
          <dd>{review.prompt_version ?? "—"}</dd>
          <dt>Rubric</dt>
          <dd>{review.rubric_version ?? "—"}</dd>
        </dl>

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
