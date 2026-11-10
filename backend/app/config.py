"""Application settings, loaded from environment / .env.

Keeps secrets (e.g. OPENAI_API_KEY) server-side only. The LLM provider is selected
explicitly via LLM_PROVIDER — there is intentionally NO automatic fallback from a
local provider to a cloud one (privacy + reproducibility; see docs/DECISIONS.md D8).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider selection (Ollama-first).
    llm_provider: str = "ollama"  # "ollama" | "openai" | "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_timeout: float = 120.0  # seconds; raise for slow local models / large snippets.
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_timeout: float = 60.0  # seconds for an OpenAI request.
    # Optional gpt-5-family reasoning control ("minimal"|"low"|"medium"|"high"); None = omit the
    # param (the model's default). We do NOT send `temperature` for OpenAI — gpt-5 reasoning
    # models reject/ignore it — so generation is tuned via reasoning effort instead.
    openai_reasoning_effort: str | None = None
    # Optional cap on output tokens (None = omit). gpt-5 uses `max_completion_tokens`.
    openai_max_output_tokens: int | None = None

    # Persistence (SQLite by default; never in-memory for the real app).
    database_url: str = "sqlite:///./data/app.db"


settings = Settings()
