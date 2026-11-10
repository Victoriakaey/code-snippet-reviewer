import type { DerivedStatus, Severity } from "../types";

const STATUS_LABEL: Record<DerivedStatus, string> = {
  not_reviewed: "Not reviewed",
  in_progress: "In progress",
  reviewed: "Reviewed",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: DerivedStatus }) {
  return <span className={`badge status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`badge sev-badge sev-${severity}`}>{severity}</span>;
}

export function LangBadge({ language }: { language: string }) {
  return <span className="badge lang">{language}</span>;
}
