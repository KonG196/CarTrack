"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./kapot_tracker.db"
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200
    CORS_ORIGINS: str = "http://localhost:5173"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""
    LINK_CODE_EXPIRE_MINUTES: int = 15
    UPLOADS_DIR: str = "./uploads"
    BACKUP_DIR: str = "./backups"
    BACKUP_KEEP: int = 14
    # Admin-only chat for daily backup delivery: in hosted mode the backup
    # holds EVERY user's data, so it must never be broadcast to linked users.
    BACKUP_TELEGRAM_CHAT_ID: str = ""
    # Gemini vision fallback for receipt OCR: empty key disables it and the
    # app stays fully offline on tesseract alone.
    GEMINI_API_KEY: str = ""
    # "-latest" alias tracks the current flash generation: Google retires
    # concrete versions for new accounts (2.5-flash already returns 404).
    GEMINI_MODEL: str = "gemini-flash-latest"

    # Plain SMTP so any provider works (Brevo, Gmail app password, Mailgun...).
    # Empty SMTP_HOST disables sending: registration then auto-verifies, which
    # is what local development wants and what production must never do.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Kapot Tracker <noreply@localhost>"
    SMTP_STARTTLS: bool = True
    PUBLIC_URL: str = "http://localhost:5173"
    VERIFY_CODE_EXPIRE_HOURS: int = 24

    # Vehicle lookup by plate/VIN via baza-gai.com.ua. Empty key disables the
    # feature outright — the state register is closed to private services, so
    # an intermediary is the only lawful route and it is optional by design.
    BAZA_GAI_API_KEY: str = ""

    # OCR.space: the free vision fallback (25k/month, no card). The demo key
    # works without registration, so the fallback is on by default — Gemini's
    # free tier is unavailable to any account that has touched billing.
    OCR_SPACE_API_KEY: str = ""
    OCR_SPACE_USE_DEMO_KEY: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
