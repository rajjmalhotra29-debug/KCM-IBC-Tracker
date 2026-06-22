"""Application settings, loaded from environment / .env file.

Every external integration (AI, payments) is OFF by default and switches ON the
moment its credentials are supplied — so the app runs fully today and upgrades
later with zero code changes.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    app_name: str = "Jarvis — IBC Origination Desk"
    environment: str = "development"
    database_url: str = f"sqlite:///{(BASE_DIR / 'ibc.db').as_posix()}"

    # Access model. "open" = completely free, every match visible, no login.
    # "freemium" = matches gated behind a paid login.
    access_mode: str = "open"

    # Brand/theme of the active prototype: "kcm" (KCM IBC Finder, Navy & Gold)
    # or "jarvis" (the original warm-cream desk). Both share one codebase.
    brand: str = "kcm"

    # Where "Engage KCM on this asset" enquiries route.
    contact_email: str = "mna.advisory@kcmehta.com"
    # Engage form delivery. Preferred: a Microsoft Form URL (M365-native) — use {ASSET}
    # in the link to pre-fill the company name. Falls back to Web3Forms key, then mailto.
    engage_form_url: str = ""
    engage_key: str = ""

    # --- Confidential master build (app.build_master) ---
    master_password: str = ""      # encrypts the client list inside master.html (never stored in the file)
    master_xlsx: str = ""          # path to KCM_IBC_Client_Master.xlsx (blank = default OneDrive path)
    master_feed_url: str = ""      # Pages data.json URL the master pulls after deploy (blank = embedded snapshot)

    # --- Auth ---
    secret_key: str = "CHANGE-ME-IN-PRODUCTION-please-use-a-long-random-string"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- AI matching (Anthropic). Empty key => rules-only mode. ---
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-8"

    # --- Source site for the IBC feed ---
    # Default adapter is IBBI public announcements. Override per deployment.
    source_url: str = "https://www.ibbi.gov.in/en/public-announcement"
    source_adapter: str = "ibbi"  # "ibbi" | "generic"

    # How many IBBI pages (20 records each) to walk per scrape.
    scrape_max_pages: int = 12
    # Retention window: keep a record if it was announced within this many days
    # OR its bidding window is still open. Older + lapsed live records are pruned.
    retention_days: int = 30

    # --- Payments (Razorpay). Empty keys => paywall runs in "demo unlock" mode. ---
    payments_enabled: bool = False
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    subscription_price_inr: int = 4999  # monthly, illustrative

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    @property
    def is_open(self) -> bool:
        return self.access_mode.strip().lower() == "open"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
