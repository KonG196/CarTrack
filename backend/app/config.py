"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT is HS256-signed with SECRET_KEY, so a known key = forge-any-user. These
# literals ship in the repo (code default + docker-compose fallback); booting on
# one in a real deployment is a silent full-takeover hole, so we refuse to start.
_INSECURE_SECRET_KEYS = frozenset(
    {"", "dev-secret-change-me", "change-me-in-production", "change-me-to-a-long-random-string"}
)


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # "production" turns on fail-closed guards (SMTP required, docs hidden).
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./kapot_tracker.db"
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200
    # The refresh token keeps a session alive across access-token expiry: the
    # client silently trades it for a fresh access token, so nobody is logged
    # out mid-use. Revoked all the same by a token_version bump.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
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
    # The owner's "new user / first car / verified / first OCR" alerts go to a
    # DEDICATED Telegram bot (not email — that burned the free SMTP tier, and not
    # the main bot, which users share). Both empty → admin alerts are disabled.
    # ADMIN_TELEGRAM_CHAT_ID is the owner's personal chat with that bot; get it by
    # messaging the bot then calling getUpdates.
    ADMIN_BOT_TOKEN: str = ""
    ADMIN_TELEGRAM_CHAT_ID: str = ""
    PUBLIC_URL: str = "http://localhost:5173"
    VERIFY_CODE_EXPIRE_HOURS: int = 24

    # Vehicle lookup by plate/VIN via baza-gai.com.ua. Empty key disables the
    # feature outright — the state register is closed to private services, so
    # an intermediary is the only lawful route and it is optional by design.
    BAZA_GAI_API_KEY: str = ""

    # Google Sign-In (Google Identity Services). The frontend sends a Google ID
    # token; the backend verifies its signature and that its `aud` matches this
    # client id. Same public client id as the frontend's VITE_GOOGLE_CLIENT_ID.
    # Empty → the /auth/google endpoint stays disabled (503).
    GOOGLE_CLIENT_ID: str = ""

    # OCR.space: the free vision fallback (25k/month, no card). The demo key
    # works without registration, so the fallback is on by default — Gemini's
    # free tier is unavailable to any account that has touched billing.
    OCR_SPACE_API_KEY: str = ""
    OCR_SPACE_USE_DEMO_KEY: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENV.strip().lower() in ("production", "prod")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _reject_insecure_config(self) -> "Settings":
        # Always fatal: a default signing key means anyone can mint tokens.
        if self.SECRET_KEY.strip() in _INSECURE_SECRET_KEYS:
            raise ValueError(
                "SECRET_KEY is unset or a known default — set a strong random value "
                '(python3 -c "import secrets; print(secrets.token_hex(32))").'
            )
        # In production an empty SMTP_HOST would auto-verify every registration
        # (no ownership proof); fine for local dev, never for a hosted instance.
        if self.is_production and not self.SMTP_HOST.strip():
            raise ValueError("SMTP_HOST is required when ENV=production (email verification).")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
