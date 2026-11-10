import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { getMessages, postMessage, ApiError } from "../api";
import type { Finding, FindingMessage } from "../types";
import { SeverityBadge } from "./badges";

interface Props {
  finding: Finding;
  readOnly: boolean;
  onBack: () => void;
}

export function DiscussionView({ finding, readOnly, onBack }: Props) {
  const [messages, setMessages] = useState<FindingMessage[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    setMessages(null);
    setLoadError(null);
    getMessages(finding.id)
      .then((m) => active && setMessages(m))
      .catch((e) => active && setLoadError(e instanceof ApiError ? e.message : "Failed to load."));
    return () => {
      active = false;
    };
  }, [finding.id]);

  // Keep the latest message in view.
  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function send() {
    const question = draft.trim();
    if (!question || sending) return; // duplicate-send guard
    setSending(true);
    setSendError(null);
    try {
      const thread = await postMessage(finding.id, question);
      setMessages(thread);
      setDraft("");
    } catch (e) {
      // A send failure is NOT a lost conversation — the backend saved nothing; let the user retry.
      setSendError(e instanceof ApiError ? e.message : "Could not send. Please retry.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="discussion-view">
      <div className="discussion-header">
        <button className="ghost sm" onClick={onBack}>
          ← Findings
        </button>
        <div className="discussion-context">
          <div className="finding-meta">
            <SeverityBadge severity={finding.severity} />
            <span className="badge cat-badge">{finding.category}</span>
            <span className="finding-line">
              {finding.line_end !== finding.line_start
                ? `Lines ${finding.line_start}–${finding.line_end}`
                : `Line ${finding.line_start}`}
            </span>
          </div>
          <div className="finding-title">{finding.description}</div>
        </div>
      </div>

      <div className="discussion-messages" ref={messagesRef}>
        {loadError && <div className="error-box">{loadError}</div>}
        {messages === null && !loadError && <div className="muted">Loading…</div>}
        {messages !== null && messages.length === 0 && (
          <div className="muted">
            {readOnly
              ? "No discussion on this historical finding."
              : "Ask a question about this finding."}
          </div>
        )}
        {messages?.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            <div className="bubble-role">
              {m.role === "assistant" ? `AI · ${m.model_name ?? "model"}` : "You"}
            </div>
            <div className="bubble-content">
              {m.role === "assistant" ? (
                <ReactMarkdown>{m.content}</ReactMarkdown>
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="discussion-composer">
        {readOnly ? (
          <div className="historical-note">
            Historical review — read-only. Run a new review to discuss findings.
          </div>
        ) : (
          <>
            {sendError && <div className="error-box" style={{ marginBottom: 8 }}>{sendError}</div>}
            <textarea
              placeholder="Ask about this finding…"
              value={draft}
              maxLength={2000}
              rows={2}
              disabled={sending}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
              }}
            />
            <button className="primary sm" disabled={sending || !draft.trim()} onClick={send}>
              {sending ? "Sending…" : "Send"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
