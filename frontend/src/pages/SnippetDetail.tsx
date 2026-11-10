import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { createReview, getSnippet, ApiError } from "../api";
import { useReviewPolling } from "../hooks/useReviewPolling";
import type { Finding, Review, ReviewStatus, SnippetDetail as Detail } from "../types";
import { CodeEditor } from "../components/CodeEditor";
import { FindingsPanel } from "../components/FindingsPanel";
import { ReviewDetailsDrawer } from "../components/ReviewDetailsDrawer";
import { LangBadge } from "../components/badges";
import { isMockReviewer } from "../mock";

const ACTIVE: ReviewStatus[] = ["queued", "running"];

export function SnippetDetail() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [triggeredReviewId, setTriggeredReviewId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadDetail = useCallback(() => {
    getSnippet(id)
      .then(setDetail)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Failed to load."));
  }, [id]);

  // Reset per-snippet state and load whenever the id changes (also handles direct URL open).
  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    setRunError(null);
    setTriggeredReviewId(null);
    setSelectedId(null);
    loadDetail();
  }, [id, loadDetail]);

  const onTerminal = useCallback(() => {
    setTriggeredReviewId(null);
    loadDetail(); // refresh findings + E2 shape once the run finishes
  }, [loadDetail]);

  const { review: liveReview, pollError, retry } = useReviewPolling(
    triggeredReviewId,
    onTerminal,
  );

  const findings = detail?.findings ?? [];
  const codeLines = useMemo(() => (detail ? detail.code.split("\n") : []), [detail]);
  const selectedFinding = findings.find((f) => f.id === selectedId) ?? null;
  const selectedRange = selectedFinding
    ? { start: selectedFinding.line_start, end: selectedFinding.line_end }
    : null;

  // Findings are historical (read-only) when the run they belong to is not the latest attempt.
  const historical =
    !!detail?.latest_review &&
    !!detail?.displayed_review &&
    detail.latest_review.id !== detail.displayed_review.id;

  const headerStatus: ReviewStatus | null =
    liveReview?.status ?? detail?.latest_review?.status ?? null;
  const reviewActive = headerStatus !== null && ACTIVE.includes(headerStatus);

  function selectByLine(line: number) {
    const f = findings.find((f) => f.line_start <= line && line <= f.line_end);
    if (f) setSelectedId(f.id);
  }

  async function runReview() {
    setRunError(null);
    try {
      const review: Review = await createReview(id);
      setTriggeredReviewId(review.id);
      loadDetail(); // latest becomes the new queued run -> old findings go read-only immediately
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setRunError("A review is already in progress.");
        if (e.reviewId) setTriggeredReviewId(e.reviewId);
        loadDetail();
      } else {
        setRunError(e instanceof ApiError ? e.message : "Could not start a review.");
      }
    }
  }

  function onResolved(updated: Finding) {
    setDetail((d) =>
      d ? { ...d, findings: d.findings.map((f) => (f.id === updated.id ? updated : f)) } : d,
    );
  }

  if (loadError) return <div className="container"><div className="error-box">{loadError}</div></div>;
  if (!detail) return <div className="container"><div className="empty">Loading…</div></div>;

  const displayed = detail.displayed_review;

  return (
    <div className="container">
      <p style={{ marginTop: 0 }}>
        <Link to="/">← Dashboard</Link>
      </p>
      <div className="toolbar">
        <div>
          <h2 style={{ margin: "0 0 4px" }}>{detail.title}</h2>
          <LangBadge language={detail.language} />
          <span className="muted" style={{ marginLeft: 8, fontSize: 13 }}>
            created {new Date(detail.created_at).toLocaleString()}
          </span>
        </div>
        <div className="grow" />
        <button className="primary" disabled={reviewActive} onClick={runReview}>
          {reviewActive ? "Review running…" : "Run review"}
        </button>
      </div>

      <StatusHeader
        status={headerStatus}
        latest={detail.latest_review}
        displayed={displayed}
        historical={historical}
        liveError={liveReview?.status === "failed" ? liveReview.error_message : null}
        onOpenDrawer={() => setDrawerOpen(true)}
      />
      {runError && <div className="error-box" style={{ marginTop: 8 }}>{runError}</div>}

      {displayed && isMockReviewer(displayed.provider) && (
        <div className="mock-banner" style={{ marginTop: 10 }}>
          <strong>Mock review · Demo.</strong> These findings are deterministic test data from
          the mock provider, not real AI analysis. Run the backend with{" "}
          <code>LLM_PROVIDER=ollama</code> for a real review.
        </div>
      )}

      {pollError && (
        <div className="poll-error" style={{ marginTop: 10 }}>
          <span>Unable to refresh the review status. {pollError}</span>
          <button className="sm" onClick={retry}>
            Retry status check
          </button>
        </div>
      )}

      <div className="detail-grid" style={{ marginTop: 16 }}>
        <div className="panel">
          <div className="panel-head">
            <strong>Code</strong>
            <span className="muted" style={{ fontSize: 13 }}>
              {findings.length > 0 ? "click a severity dot to jump to a finding" : ""}
            </span>
          </div>
          <div className="code-pane">
            <CodeEditor
              value={detail.code}
              language={detail.language}
              editable={false}
              findings={findings}
              selectedRange={selectedRange}
              onLineClick={selectByLine}
            />
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <strong>Findings</strong>
            {displayed && displayed.rejected_finding_count > 0 && (
              <span className="muted" style={{ fontSize: 13 }}>
                {displayed.rejected_finding_count} filtered
              </span>
            )}
          </div>
          <div className="panel-body">
            {!displayed ? (
              <div className="empty">
                {reviewActive ? "Review in progress…" : "Not reviewed yet. Run a review to see findings."}
              </div>
            ) : findings.length === 0 ? (
              <div className="empty">No issues found in review #{displayed.run_number}.</div>
            ) : (
              <FindingsPanel
                findings={findings}
                codeLines={codeLines}
                selectedId={selectedId}
                onSelect={setSelectedId}
                readOnly={historical}
                onResolved={onResolved}
              />
            )}
          </div>

          <div className="panel-head" style={{ borderTop: "1px solid var(--border)", borderBottom: "none" }}>
            <strong>Discussion</strong>
            <span className="muted" style={{ fontSize: 13 }}>Coming in M6</span>
          </div>
          <div className="panel-body">
            <button className="sm" disabled title="Discuss lands in M6">
              Discuss a finding
            </button>
          </div>
        </div>
      </div>

      {drawerOpen && displayed && (
        <ReviewDetailsDrawer review={displayed} onClose={() => setDrawerOpen(false)} />
      )}
    </div>
  );
}

interface HeaderProps {
  status: ReviewStatus | null;
  latest: Detail["latest_review"];
  displayed: Detail["displayed_review"];
  historical: boolean;
  liveError: string | null;
  onOpenDrawer: () => void;
}

function StatusHeader({ status, latest, displayed, historical, liveError, onOpenDrawer }: HeaderProps) {
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="panel-body">
        <div className="review-status">
          {status === null && <span className="muted">Not reviewed yet.</span>}
          {(status === "queued" || status === "running") && (
            <>
              <span className="spinner" />
              <span>Review #{latest?.run_number} {status}…</span>
            </>
          )}
          {status === "completed" && (
            <>
              <span className="status-reviewed badge">Reviewed</span>
              <span>
                Review #{latest?.run_number} · {latest?.model_name ?? "model"}
              </span>
            </>
          )}
          {status === "failed" && (
            <>
              <span className="status-failed badge">Latest failed</span>
              <span className="muted">
                Review #{latest?.run_number} failed{liveError || latest?.error_message ? `: ${liveError ?? latest?.error_message}` : ""}.
              </span>
            </>
          )}
          <div style={{ flex: 1 }} />
          {displayed && (
            <button className="ghost sm" onClick={onOpenDrawer}>
              Review details
            </button>
          )}
        </div>

        {historical && displayed && (
          <div className="historical-note" style={{ marginTop: 10 }}>
            Showing findings from review #{displayed.run_number} (last successful). These are{" "}
            <strong>historical and read-only</strong> — they were not produced by the latest
            attempt.
          </div>
        )}
      </div>
    </div>
  );
}
