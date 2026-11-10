"""Application settings, loaded from environment / .env.

Keeps secrets (e.g. OPENAI_API_KEY) server-side only. The LLM provider is selected
explicitly via LLM_PROVIDER — there is intentionally NO automatic fallback from a
local provider to a cloud one (privacy + reproducibility; see docs/DECISIONS.md D8).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider selection (Ollama-first).
    llm_provider: str = "ollama"  # "ollama" | "openai"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Persistence (SQLite by default; never in-memory for the real app).
    database_url: str = "sqlite:///./data/app.db"


settings = Settings()
