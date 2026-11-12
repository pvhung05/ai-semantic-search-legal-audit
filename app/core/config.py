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

    # IS_LOCAL=true -> dung Qwen local (Ollama); false -> dung Claude.
    IS_LOCAL: bool = True

    # Cau hinh Qwen local
    LOCAL_LLM_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen3:14b"
    LOCAL_LLM_API_KEY: str = "ollama"

    # Cau hinh Gemini (endpoint OpenAI-compatible cua Google; API key = GEMINI_API_KEY)
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
    # Context cho Qwen local (gui qua options.num_ctx cua /api/chat; endpoint /v1 BO QUA num_ctx).
    LLM_NUM_CTX: int = 16384
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

    # Rerank cross-encoder (TEI /rerank). Rong -> bo qua rerank, giu thu tu hybrid.
    RERANK_URL: str = ""
    RERANK_MODEL: str = ""          # chi de ghi chu; TEI dinh model o server, khong gui kem
    RERANK_LAY_VE: int = 40         # so ung vien lay ra tu hybrid truoc khi rerank
    RERANK_TOP_N: int = 10          # so ung vien sau rerank gui len LLM (10: du can cu de suy luan vi pham thu hep/loai bo)

    # So luot hoi-dap gan nhat /ask ghi nho (0 = tat, khong nho). Chi nho VAN BAN hoi-dap,
    # KHONG kem khoi can cu cu -> tranh phinh context.
    HISTORY_CHAT: int = 10

    EMBED_URL: str = "http://localhost:11434/v1"
    EMBED_MODEL: str = "bge-m3"
    EMBED_DIM: int = 1024
    EMBED_API_KEY: str = "ollama"
    EMBED_BATCH_SIZE: int = 32
    ENABLE_FALLBACK: bool = False
    # Tier1 (dan chieu/hieu luc) con bam schema cu, chua port sang node/tac_dong -> mac dinh tat.
    ENABLE_TIER1: bool = False

    HIEU_LUC_MAC_DINH: str = "today"
    AUDIT_CHE_DO_MAC_DINH: str = "cay"
    AUDIT_TU_DONG_DUYET: bool = False
    AUDIT_MAX_DIEU_ME: int = 6
    AUDIT_MAX_TOKEN_PROMPT: int = 12000
    AUDIT_DIFF_NGUONG: float = 0.92
    AUDIT_NGUONG_FALLBACK: float = 0.45
    STORAGE_PATH: Path = Field(default=Path("./data/private"))

    # Rate-limit crawl (giay giua 2 request). robots.txt vbpl khong co Crawl-delay;
    # ha thap -> nhanh hon nhung rui ro bi chan. Giu 1 luong (khong song song).
    CRAWL_DELAY_MIN: float = 0.6
    CRAWL_DELAY_MAX: float = 1

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8010
    LOG_LEVEL: str = "INFO"


settings = Settings()
