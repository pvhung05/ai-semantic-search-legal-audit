from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_URL: str

    # IS_LOCAL=true -> dung Qwen local (Ollama); false -> dung Gemini.
    IS_LOCAL: bool = True

    # Cau hinh Qwen local
    LOCAL_LLM_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen3:14b"
    LOCAL_LLM_API_KEY: str = "ollama"

    # Cau hinh Gemini
    GEMINI_LLM_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_LLM_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_LLM_API_KEY: str = ""

    # LLM_URL/MODEL/API_KEY duoc chon tu dong theo IS_LOCAL (xem _chon_llm).
    LLM_URL: str = "http://localhost:11434/v1"
    LLM_MODEL: str = "qwen3:14b"
    LLM_API_KEY: str = "ollama"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4000
    LLM_DISABLE_THINKING: bool = True
    LLM_SONG_SONG: int = 4

    @model_validator(mode="after")
    def _chon_llm(self) -> "Settings":
        url, model, key = self.cau_hinh_llm(self.IS_LOCAL)
        self.LLM_URL, self.LLM_MODEL, self.LLM_API_KEY = url, model, key
        return self

    def cau_hinh_llm(self, is_local: bool | None = None) -> tuple[str, str, str]:
        """Tra (url, model, api_key) theo is_local. None -> dung IS_LOCAL mac dinh."""
        dung_local = self.IS_LOCAL if is_local is None else is_local
        if dung_local:
            return self.LOCAL_LLM_URL, self.LOCAL_LLM_MODEL, self.LOCAL_LLM_API_KEY
        return self.GEMINI_LLM_URL, self.GEMINI_LLM_MODEL, self.GEMINI_LLM_API_KEY

    EMBED_URL: str = "http://localhost:11434/v1"
    EMBED_MODEL: str = "bge-m3"
    EMBED_DIM: int = 1024
    EMBED_API_KEY: str = "ollama"
    EMBED_BATCH_SIZE: int = 32
    ENABLE_FALLBACK: bool = False

    HIEU_LUC_MAC_DINH: str = "today"
    AUDIT_CHE_DO_MAC_DINH: str = "cay"
    AUDIT_TU_DONG_DUYET: bool = False
    AUDIT_MAX_DIEU_ME: int = 6
    AUDIT_MAX_TOKEN_PROMPT: int = 12000
    AUDIT_DIFF_NGUONG: float = 0.92
    AUDIT_NGUONG_FALLBACK: float = 0.45
    STORAGE_PATH: Path = Field(default=Path("./data/private"))

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8010
    LOG_LEVEL: str = "INFO"


settings = Settings()
