// Shared API types — string-literal unions mirror the backend enums.

export type Language = "python" | "javascript" | "typescript" | "java" | "go";
export const LANGUAGES: Language[] = ["python", "javascript", "typescript", "java", "go"];

export type DerivedStatus = "not_reviewed" | "in_progress" | "reviewed" | "failed";
export type ReviewStatus = "queued" | "running" | "completed" | "failed";
export type Severity = "critical" | "warning" | "info";
export type Category = "bug" | "security" | "performance" | "maintainability";
export type ResolutionStatus = "open" | "accepted" | "dismissed";

export interface SnippetRow {
  id: string;
  title: string;
  language: Language;
  code: string;
  created_at: string;
  status: DerivedStatus;
  reviewer: string | null;
  reviewer_provider: string | null;
  finding_count: number;
}

export interface Finding {
  id: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  category: Category;
  description: string;
  rationale: string | null;
  suggested_fix: string | null;
  resolution_status: ResolutionStatus;
  resolution_reason: string | null;
  resolved_at: string | null;
}

export interface ReviewSummary {
  id: string;
  run_number: number;
  status: ReviewStatus;
  provider: string | null;
  model_name: string | null;
  prompt_version: string | null;
  rubric_version: string | null;
  rejected_finding_count: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Review extends ReviewSummary {
  snippet_id: string;
  findings: Finding[];
}

export interface SnippetDetail {
  id: string;
  title: string;
  language: Language;
  code: string;
  created_at: string;
  status: DerivedStatus;
  latest_review: ReviewSummary | null;
  displayed_review: ReviewSummary | null;
  findings: Finding[];
}

export interface FindingMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider: string | null;
  model_name: string | null;
  created_at: string;
}

export interface Rubric {
  name: string;
  rubric_version: string;
  prompt_version: string;
  dimensions: { category: string; description: string }[];
  severities: { severity: string; definition: string }[];
}

export interface ResolutionUpdate {
  resolution_status: ResolutionStatus;
  resolution_reason?: string | null;
}
