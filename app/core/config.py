"""Application settings.

Everything comes from environment variables (or a local .env file). Secrets are never
hard-coded. The validator at the bottom refuses to start the app in unsafe combinations,
for example development authentication in production.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def csv_list(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ---- runtime -------------------------------------------------------------------
    # Defaults to "production" on purpose: you have to opt in to development behaviour.
    environment: Literal["development", "test", "production"] = "production"
    app_name: str = "Tech Radar API"
    log_level: str = "INFO"
    cors_origins: str = ""  # comma separated list of allowed browser origins

    # ---- data stores ---------------------------------------------------------------
    database_url: str = "postgresql+psycopg://techradar:techradar@localhost:5432/techradar"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False  # run tasks inline (tests / no-Redis dev only)

    # ---- authentication ------------------------------------------------------------
    auth_mode: Literal["entra", "dev"] = "entra"
    allow_dev_auth: bool = False  # second switch; both must be set for dev auth
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_audience: str = ""  # defaults to the client id
    entra_admin_role: str = "TechRadar.Admin"
    entra_moderator_role: str = "TechRadar.Moderator"
    allowed_email_domains: str = "neuleap.ai"

    # ---- storage / uploads ---------------------------------------------------------
    storage_dir: str = "./var/storage"
    max_upload_bytes: int = 100 * 1024 * 1024
    client_name_denylist: str = ""  # comma separated; flagged during artifact scans

    # ---- outbound fetching (SSRF guard) -------------------------------------------
    fetch_timeout_seconds: float = 10.0
    fetch_max_bytes: int = 2 * 1024 * 1024
    fetch_max_redirects: int = 3
    fetch_allowed_ports: str = "80,443"
    max_items_per_source: int = 20

    # ---- AI providers --------------------------------------------------------------
    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    search_provider: Literal["none", "mock"] = "none"

    # ---- integrations (all optional; "none" means not configured) -----------------
    directory_provider: Literal["none", "mock", "graph"] = "none"
    mail_provider: Literal["none", "mock", "graph"] = "none"
    teams_provider: Literal["none", "mock", "webhook"] = "none"
    sharepoint_provider: Literal["none", "mock", "graph"] = "none"
    buddy_provider: Literal["none", "mock"] = "none"
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    mail_sender: str = ""
    teams_webhook_url: str = ""
    sharepoint_drive_id: str = ""
    sharepoint_folder: str = "Tech Radar"
    directory_create_users: bool = False  # directory sync may also create users (otherwise users appear at first sign-in)

    # ---- schedules (minutes) -------------------------------------------------------
    discovery_interval_minutes: int = 360
    reminder_interval_minutes: int = 60
    sharepoint_sync_interval_minutes: int = 5
    directory_sync_interval_minutes: int = 60
    reaper_interval_minutes: int = 10
    notification_delivery_interval_minutes: int = 1
    job_lease_minutes: int = 30  # a "running" job older than this is considered dead

    # ------------------------------------------------------------------ helpers
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def dev_auth_active(self) -> bool:
        return self.auth_mode == "dev" and self.allow_dev_auth and not self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        return csv_list(self.cors_origins)

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [d.lower() for d in csv_list(self.allowed_email_domains)]

    @property
    def client_denylist(self) -> list[str]:
        return csv_list(self.client_name_denylist)

    @property
    def fetch_port_list(self) -> list[int]:
        return [int(p) for p in csv_list(self.fetch_allowed_ports)]

    @model_validator(mode="after")
    def _refuse_unsafe_combinations(self) -> "Settings":
        if self.auth_mode == "dev":
            if self.is_production:
                raise ValueError("AUTH_MODE=dev is never allowed when ENVIRONMENT=production")
            if not self.allow_dev_auth:
                raise ValueError("AUTH_MODE=dev also needs ALLOW_DEV_AUTH=true (second switch)")
        if self.is_production:
            if self.allow_dev_auth:
                raise ValueError("ALLOW_DEV_AUTH must not be set in production")
            if self.auth_mode == "entra" and not (self.entra_tenant_id and self.entra_client_id):
                raise ValueError("ENTRA_TENANT_ID and ENTRA_CLIENT_ID are required in production")
            mocks = [
                n for n in ("llm_provider", "search_provider", "directory_provider", "mail_provider",
                            "teams_provider", "sharepoint_provider", "buddy_provider")
                if getattr(self, n) == "mock"
            ]
            if mocks:
                raise ValueError(f"Mock providers are not allowed in production: {', '.join(mocks)}")
            if self.celery_task_always_eager:
                raise ValueError("CELERY_TASK_ALWAYS_EAGER must not be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
