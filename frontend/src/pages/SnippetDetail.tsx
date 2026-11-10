import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { createReview, getSnippet, getReview, listSnippetReviews, ApiError } from "../api";
import { useReviewPolling } from "../hooks/useReviewPolling";
import type { Finding, Review, ReviewRun, ReviewStatus, SnippetDetail as Detail } from "../types";
import { CodeEditor } from "../components/CodeEditor";
import { FindingsPanel } from "../components/FindingsPanel";
import { DiscussionView } from "../components/DiscussionView";
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
  const [discussingId, setDiscussingId] = useState<string | null>(null);
  const [runs, setRuns] = useState<ReviewRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);

  const loadDetail = useCallback(() => {
    getSnippet(id)
      .then(setDetail)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Failed to load."));
  }, [id]);

  const loadRuns = useCallback(() => {
    listSnippetReviews(id)
      .then(setRuns)
      .catch(() => setRuns([])); // the run selector is additive; its failure must not break the page
  }, [id]);

  // Reset per-snippet state and load whenever the id changes (also handles direct URL open).
  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    setRunError(null);
    setTriggeredReviewId(null);
    setSelectedId(null);
    setDiscussingId(null);
    setSelectedRunId(null);
    setSelectedReview(null);
    loadDetail();
    loadRuns();
  }, [id, loadDetail, loadRuns]);

  const onTerminal = useCallback(() => {
    setTriggeredReviewId(null);
    setSelectedRunId(null); // a new run finished -> snap the view back to the latest
    setSelectedReview(null);
    loadDetail(); // refresh findings + E2 shape once the run finishes
    loadRuns();
  }, [loadDetail, loadRuns]);

  const { review: liveReview, pollError, retry } = useReviewPolling(
    triggeredReviewId,
    onTerminal,
  );

  // Findings are historical (read-only) when the DEFAULT-shown run is not the latest attempt.
  const historical =
    !!detail?.latest_review &&
    !!detail?.displayed_review &&
    detail.latest_review.id !== detail.displayed_review.id;

  // The run selector can point the view at an OLDER run (always read-only). With no explicit
  // selection we show the default E2 view (last-successful findings, editable iff it is latest).
  const viewedFindings = selectedReview ? selectedReview.findings : (detail?.findings ?? []);
  const viewedReadOnly = selectedReview ? true : historical;

  const codeLines = useMemo(() => (detail ? detail.code.split("\n") : []), [detail]);
  const selectedFinding = viewedFindings.find((f) => f.id === selectedId) ?? null;
  const discussingFinding = viewedFindings.find((f) => f.id === discussingId) ?? null;
  const selectedRange = selectedFinding
    ? { start: selectedFinding.line_start, end: selectedFinding.line_end }
    : null;

  const headerStatus: ReviewStatus | null =
    liveReview?.status ?? detail?.latest_review?.status ?? null;
  const reviewActive = headerStatus !== null && ACTIVE.includes(headerStatus);

  const latestRunId = detail?.latest_review?.id ?? null;
  // Switching runs is view-only: an older run loads read-only; picking the latest (or clearing)
  // falls back to the default editable/E2 view. The backend enforces read-only regardless.
  function onSelectRun(runId: string) {
    setSelectedId(null);
    setDiscussingId(null);
    setRunError(null);
    if (!runId || runId === latestRunId) {
      setSelectedRunId(null);
      setSelectedReview(null);
      return;
    }
    setSelectedRunId(runId);
    setSelectedReview(null);
    getReview(runId)
      .then(setSelectedReview)
      .catch((e) => setRunError(e instanceof ApiError ? e.message : "Could not load that run."));
  }

  function selectByLine(line: number) {
    const f = viewedFindings.find((f) => f.line_start <= line && line <= f.line_end);
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
  // The run whose findings are on screen (the selected older run, else the default E2 run).
  const viewedRun = selectedReview ?? displayed;
  const viewedFailed = selectedReview?.status === "failed";

  return (
    <div className="container detail-page">
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

      {runs.length > 1 && (
        <div className="run-history" style={{ marginTop: 10 }}>
          <div className="run-history-head">
            <span className="muted" style={{ fontSize: 13 }}>Review history</span>
            <span className="muted" style={{ fontSize: 12 }}>{runs.length} runs</span>
          </div>
          {/* A scrollable row of native-button pills — many runs scroll horizontally rather than
              wrapping or overflowing the page. The latest/selected/failed runs are visually
              distinct; selection uses aria-pressed, focus is keyboard-visible. */}
          <div className="run-pills" role="group" aria-label="Review runs">
            {runs.map((r) => {
              const current = r.id === (selectedRunId ?? latestRunId);
              return (
                <button
                  key={r.id}
                  type="button"
                  className={`run-pill${current ? " current" : ""}${r.status === "failed" ? " failed" : ""}`}
                  aria-pressed={current}
                  onClick={() => onSelectRun(r.id)}
                  title={`Review #${r.run_number} · ${r.status} · ${r.finding_count} finding${r.finding_count === 1 ? "" : "s"}`}
                >
                  <span className="run-pill-n">#{r.run_number}</span>
                  {r.id === latestRunId && <span className="run-pill-tag latest">latest</span>}
                  {r.status === "failed" && <span className="run-pill-tag failed">failed</span>}
                </button>
              );
            })}
          </div>
          {selectedReview && (
            <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>Viewing a historical run — read-only.</div>
          )}
        </div>
      )}
      {runError && <div className="error-box" style={{ marginTop: 8 }}>{runError}</div>}

      {viewedRun && isMockReviewer(viewedRun.provider) && (
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

      <div className="review-workspace">
        <section className="workspace-panel code-panel">
          <div className="panel-head">
            <strong>Code</strong>
            <span className="muted" style={{ fontSize: 13 }}>
              {detail.language} · read-only
              {viewedFindings.length > 0 ? " · click a severity dot to jump to a finding" : ""}
            </span>
          </div>
          <div className="panel-scroll code-scroll">
            <CodeEditor
              value={detail.code}
              language={detail.language}
              editable={false}
              findings={viewedFindings}
              selectedRange={selectedRange}
              onLineClick={selectByLine}
              height="100%"
            />
          </div>
        </section>

        <section className="workspace-panel findings-panel">
          {discussingFinding ? (
            <DiscussionView
              finding={discussingFinding}
              readOnly={viewedReadOnly}
              onBack={() => setDiscussingId(null)}
            />
          ) : (
            <>
              <div className="panel-head">
                <strong>Findings</strong>
                <span className="muted" style={{ fontSize: 13 }}>
                  {!viewedFailed && viewedRun && viewedFindings.length > 0 ? `${viewedFindings.length} shown` : ""}
                  {!viewedFailed && viewedRun && viewedRun.rejected_finding_count > 0
                    ? ` · ${viewedRun.rejected_finding_count} filtered`
                    : ""}
                </span>
              </div>
              <div className="panel-scroll">
                {viewedFailed && selectedReview ? (
                  <div className="empty">
                    Review #{selectedReview.run_number} failed
                    {selectedReview.error_message ? `: ${selectedReview.error_message}` : ""}. No findings for this run.
                  </div>
                ) : !viewedRun ? (
                  <div className="empty">
                    {reviewActive ? "Review in progress…" : "Not reviewed yet. Run a review to see findings."}
                  </div>
                ) : viewedFindings.length === 0 ? (
                  <div className="empty">No issues found in review #{viewedRun.run_number}.</div>
                ) : (
                  <FindingsPanel
                    findings={viewedFindings}
                    codeLines={codeLines}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    readOnly={viewedReadOnly}
                    onResolved={onResolved}
                    onDiscuss={setDiscussingId}
                  />
                )}
              </div>
            </>
          )}
        </section>
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
