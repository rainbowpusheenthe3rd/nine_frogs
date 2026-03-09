from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096

    # ── Embeddings ────────────────────────────────────────────────────────────
    embed_model: str = "BAAI/bge-base-en-v1.5"
    embed_device: str = "cpu"
    embed_dim: int = 768

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/ninefrogs"

    # ── AnkiConnect ───────────────────────────────────────────────────────────
    anki_url: str = "http://localhost:8765"
    anki_default_deck: str = "Nine Frogs"

    # ── Wikipedia ─────────────────────────────────────────────────────────────
    wiki_dataset: str = "NeuML/txtai-wikipedia-slim"
    wiki_cache_dir: str = ".cache"
    wiki_enabled: bool = True

    # ── Crawler ───────────────────────────────────────────────────────────────
    crawl_max_pages: int = 30
    crawl_timeout: int = 10

    # ── Web ───────────────────────────────────────────────────────────────────
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
