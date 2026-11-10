import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listSnippets, ApiError } from "../api";
import { LANGUAGES, type DerivedStatus, type Language, type SnippetRow } from "../types";
import { CreateSnippet } from "../components/CreateSnippet";
import { LangBadge, StatusBadge } from "../components/badges";
import { isMockReviewer } from "../mock";

const STATUS_FILTERS: { value: DerivedStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "not_reviewed", label: "Not reviewed" },
  { value: "in_progress", label: "In progress" },
  { value: "reviewed", label: "Reviewed" },
  { value: "failed", label: "Failed" },
];

export function Dashboard() {
  const navigate = useNavigate();
  const [snippets, setSnippets] = useState<SnippetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [langFilter, setLangFilter] = useState<Language | "all">("all");
  const [statusFilter, setStatusFilter] = useState<DerivedStatus | "all">("all");

  function load() {
    setError(null);
    listSnippets()
      .then(setSnippets)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load snippets."));
  }

  useEffect(load, []);

  const filtered = (snippets ?? []).filter(
    (s) =>
      (langFilter === "all" || s.language === langFilter) &&
      (statusFilter === "all" || s.status === statusFilter),
  );

  return (
    <div className="container">
      {creating ? (
        <CreateSnippet
          onCreated={(id) => navigate(`/snippets/${id}`)}
          onCancel={() => setCreating(false)}
        />
      ) : (
        <div className="toolbar">
          <div>
            <label htmlFor="f-lang">Language</label>
            <select
              id="f-lang"
              value={langFilter}
              onChange={(e) => setLangFilter(e.target.value as Language | "all")}
            >
              <option value="all">All languages</option>
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="f-status">Status</label>
            <select
              id="f-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as DerivedStatus | "all")}
            >
              {STATUS_FILTERS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grow" />
          <button className="primary" onClick={() => setCreating(true)}>
            + New snippet
          </button>
        </div>
      )}

      {error && <div className="error-box">{error}</div>}

      {snippets === null && !error && <div className="empty">Loading snippets…</div>}

      {snippets !== null && filtered.length === 0 && !creating && (
        <div className="empty">
          {snippets.length === 0
            ? "No snippets yet. Create one to start a review."
            : "No snippets match the current filters."}
        </div>
      )}

      {filtered.length > 0 && (
        <table className="snippets">
          <thead>
            <tr>
              <th>Title</th>
              <th>Language</th>
              <th>Reviewer</th>
              <th>Reviews</th>
              <th>Findings</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.id} onClick={() => navigate(`/snippets/${s.id}`)}>
                <td>{s.title}</td>
                <td>
                  <LangBadge language={s.language} />
                </td>
                <td className="muted">
                  {s.reviewer === null ? (
                    "—"
                  ) : isMockReviewer(s.reviewer_provider) ? (
                    <span className="mock-tag">Mock · Demo</span>
                  ) : (
                    s.reviewer
                  )}
                </td>
                <td className="muted">{s.review_count}</td>
                <td className="muted">{s.status === "reviewed" ? s.finding_count : "—"}</td>
                <td>
                  <StatusBadge status={s.status} />
                </td>
                <td className="muted">{new Date(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
