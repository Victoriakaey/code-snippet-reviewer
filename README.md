# Code Snippet Reviewer

A lightweight, self-service tool for AI-powered review of ad-hoc code snippets.
Submit a snippet, trigger an LLM review, and work through the structured findings —
accept, dismiss, or discuss each one.

> **Status:** project scaffolding in progress. Setup instructions, architecture
> overview, and the AI Usage Log will land here as implementation proceeds.

## Planned stack

- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI + Pydantic
- **Database:** SQLite + SQLAlchemy (persistent)
- **AI:** single LLM provider (server-side key) + a mock provider for tests

Setup (one command), architecture, and "what I'd change in production" follow.
