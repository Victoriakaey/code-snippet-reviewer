import { useState } from "react";

import { createSnippet, ApiError } from "../api";
import { LANGUAGES, type Language } from "../types";
import { CodeEditor } from "./CodeEditor";

interface Props {
  onCreated: (snippetId: string) => void;
  onCancel: () => void;
}

export function CreateSnippet({ onCreated, onCancel }: Props) {
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState<Language>("python");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = title.trim().length > 0 && code.trim().length > 0 && !submitting;

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const snippet = await createSnippet({ title: title.trim(), language, code });
      onCreated(snippet.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create snippet.");
      setSubmitting(false);
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 20 }}>
      <div className="panel-head">
        <strong>New snippet</strong>
        <button className="ghost sm" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <div className="panel-body">
        <div className="create-form">
          <div className="form-row">
            <div style={{ flex: 2 }}>
              <label htmlFor="title">Title</label>
              <input
                id="title"
                value={title}
                maxLength={200}
                placeholder="e.g. Fibonacci helper"
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="language">Language</label>
              <select
                id="language"
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language)}
              >
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label>Code</label>
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
              <CodeEditor
                value={code}
                language={language}
                editable
                onChange={setCode}
                minHeight="220px"
              />
            </div>
          </div>
          {error && <div className="error-box">{error}</div>}
          <div>
            <button className="primary" disabled={!canSubmit} onClick={submit}>
              {submitting ? "Creating…" : "Create snippet"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
