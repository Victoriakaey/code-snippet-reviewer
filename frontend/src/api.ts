// Typed API client. Every call goes through `request`, which parses the backend's
// { error: { code, message, ... } } envelope into an ApiError carrying the HTTP status and
// error code (so callers can special-case 409 conflicts, etc.).

import type {
  Review,
  ReviewRun,
  Rubric,
  SnippetDetail,
  SnippetRow,
  ResolutionUpdate,
  Finding,
  FindingMessage,
} from "./types";

export interface HealthResponse {
  status: string;
  llm_provider: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  reviewId?: string;

  constructor(status: number, code: string, message: string, reviewId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.reviewId = reviewId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server.");
  }

  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; review_id?: string } })
      ?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? `Request failed (${res.status})`,
      err?.review_id,
    );
  }
  return body as T;
}

export const getHealth = () => request<HealthResponse>("/api/health");

export const listSnippets = () => request<SnippetRow[]>("/api/snippets");

export const createSnippet = (body: { title: string; language: string; code: string }) =>
  request<SnippetRow>("/api/snippets", { method: "POST", body: JSON.stringify(body) });

export const getSnippet = (id: string) => request<SnippetDetail>(`/api/snippets/${id}`);

export const createReview = (snippetId: string) =>
  request<Review>(`/api/snippets/${snippetId}/reviews`, { method: "POST" });

export const getReview = (id: string) => request<Review>(`/api/reviews/${id}`);

export const listSnippetReviews = (snippetId: string) =>
  request<ReviewRun[]>(`/api/snippets/${snippetId}/reviews`);

export const patchFinding = (id: string, body: ResolutionUpdate) =>
  request<Finding>(`/api/findings/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const getRubric = () => request<Rubric>("/api/rubric");

export const getMessages = (findingId: string) =>
  request<FindingMessage[]>(`/api/findings/${findingId}/messages`);

export const postMessage = (findingId: string, question: string) =>
  request<FindingMessage[]>(`/api/findings/${findingId}/messages`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
