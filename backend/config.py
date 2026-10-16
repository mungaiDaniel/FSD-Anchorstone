"""
Application configuration.

Every secret and connection string comes from the environment (or a local .env
file, loaded below). Nothing sensitive has a hardcoded fallback: in production
a missing SECRET_KEY or DATABASE_URI stops the app at startup instead of
silently running with a guessable key. See .env.example for every variable.

Select the config with APP_ENV = development | production | testing
(default: development).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


class BaseConfig:
    COMPANY_NAME = "Anchorstone Capital Ltd"
    COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "")
    COMPANY_CONTACT = os.environ.get("COMPANY_CONTACT", "")
    CURRENCY = "KES"

    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    CORS_ORIGINS = _env_list("CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])

    # SMTP — credentials only ever come from the environment or from the
    # encrypted Settings -> Email Sending override (see app/Settings/service.py).
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.office365.com")
    MAIL_PORT = _env_int("MAIL_PORT", 587)
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
    MAIL_BCC = os.environ.get("MAIL_BCC")
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", False)
    MAIL_DEBUG = _env_bool("MAIL_DEBUG", False)

    # Background jobs (email send queue, daily backup). Off in tests.
    SCHEDULER_ENABLED = _env_bool("SCHEDULER_ENABLED", True)
    EMAIL_QUEUE_INTERVAL_MINUTES = _env_int("EMAIL_QUEUE_INTERVAL_MINUTES", 2)
    EMAIL_QUEUE_BATCH_SIZE = _env_int("EMAIL_QUEUE_BATCH_SIZE", 100)

    # Daily pg_dump -> OneDrive backups. Off until Azure credentials are set up.
    DB_BACKUP_ENABLED = _env_bool("DB_BACKUP_ENABLED", False)
    DB_BACKUP_HOUR_UTC = _env_int("DB_BACKUP_HOUR_UTC", 1)
    DB_BACKUP_MINUTE_UTC = _env_int("DB_BACKUP_MINUTE_UTC", 0)
    PG_DUMP_PATH = os.environ.get("PG_DUMP_PATH") or "pg_dump"
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    ONEDRIVE_USER_ID = os.environ.get("ONEDRIVE_USER_ID")
    ONEDRIVE_BACKUP_FOLDER = os.environ.get("ONEDRIVE_BACKUP_FOLDER") or "Anchorstone-DB-Backups"

    JWT_ACCESS_TOKEN_HOURS = _env_int("JWT_ACCESS_TOKEN_HOURS", 12)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI") or "postgresql://localhost/anchorstone"
    # Never email real investors from a dev machine unless explicitly enabled.
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", True)


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-only-secret-key-not-for-real-use-0123456789"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URI") or "postgresql://localhost/anchorstone_test"
    MAIL_SUPPRESS_SEND = True
    MAIL_DEFAULT_SENDER = "statements@anchorstone.test"
    SCHEDULER_ENABLED = False
    DB_BACKUP_ENABLED = False


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None):
    env = (name or os.environ.get("APP_ENV") or "development").strip().lower()
    if env not in CONFIGS:
        raise RuntimeError(f"Unknown APP_ENV '{env}'. Use one of: {', '.join(CONFIGS)}")
    return CONFIGS[env]
