"""
Anchorstone Capital Ltd — statement system API.

    flask --app main db upgrade                  # create / migrate the schema
    flask --app main create-superadmin           # first login account
    flask --app main run --port 4455             # dev server
    gunicorn main:app                            # production
"""
import logging
import os
import secrets
import threading
from datetime import timedelta

import click
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from app.database.database import db
from config import get_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("anchorstone")

migrate = Migrate()


def _import_models():
    # Registers every table on db.metadata (for Alembic and relationships).
    from app.Admin.model import User  # noqa: F401
    from app.Backup.model import BackupLog  # noqa: F401
    from app.Emails.model import EmailAttachment, OutboxEmail  # noqa: F401
    from app.Interest.model import InterestPayout, InterestPeriod, InterestRate  # noqa: F401
    from app.Investors.model import Investor  # noqa: F401
    from app.Reports.model import ReportSchedule  # noqa: F401
    from app.Settings.model import EmailSettings  # noqa: F401
    from app.Transactions.model import Deposit, Withdrawal  # noqa: F401
    from app.utils.audit_log import AuditLog  # noqa: F401


def _check_secrets(app: Flask, env_name: str) -> None:
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URI is not set.")
    if app.config.get("SECRET_KEY"):
        return
    if env_name == "production":
        raise RuntimeError("SECRET_KEY is not set. Refusing to start in production without it.")
    # Development only: a throwaway key. Sessions end on every restart, and any
    # SMTP password saved in Settings can't be decrypted after a restart.
    app.config["SECRET_KEY"] = secrets.token_urlsafe(48)
    logger.warning("SECRET_KEY not set — using a temporary random key (development only). Set it in .env.")


def create_app(config_name: str | None = None) -> Flask:
    config = get_config(config_name)
    env_name = (config_name or os.environ.get("APP_ENV") or "development").lower()

    app = Flask(__name__)
    app.config.from_object(config)
    _check_secrets(app, env_name)
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=app.config["JWT_ACCESS_TOKEN_HOURS"])
    # Header only: a token in the URL would end up in server and proxy logs.
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    JWTManager(app)
    db.init_app(app)
    _import_models()
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(__file__), "migrations"))

    from app.Emails.sender import mail
    mail.init_app(app)

    from app.utils.http import register_error_handlers
    register_error_handlers(app, db)

    from app.Admin.route import user_v1
    from app.Audit.route import audit_v1
    from app.Backup.route import backup_v1
    from app.Emails.route import emails_v1
    from app.Interest.route import interest_v1
    from app.Investors.route import investors_v1
    from app.Reports.route import reports_v1
    from app.Settings.route import settings_v1
    from app.Stats.route import stats_v1
    from app.Transactions.route import transactions_v1

    for bp in (user_v1, investors_v1, transactions_v1, interest_v1, emails_v1, stats_v1,
               settings_v1, audit_v1, backup_v1, reports_v1):
        app.register_blueprint(bp)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    _register_cli(app)
    _start_background_jobs(app)
    return app


def _start_background_jobs(app: Flask) -> None:
    """Start the scheduler in the process that actually serves requests — on its
    first request. The debug reloader's watcher process and CLI commands
    (db upgrade, create-superadmin) never serve requests, so they never start
    a second scheduler (which would re-queue in-flight emails and race the
    live server). Every email is queued by a request, so nothing waits on this."""
    if not app.config.get("SCHEDULER_ENABLED"):
        return
    lock = threading.Lock()
    state = {"started": False}

    @app.before_request
    def _ensure_background_jobs():
        if state["started"]:
            return
        with lock:
            if state["started"]:
                return
            state["started"] = True
            try:
                from app.Settings.service import apply_email_settings_to_app
                apply_email_settings_to_app(app, db.session)
                from app.logic.scheduler import start_scheduler
                start_scheduler(app)
            except Exception:
                logger.error("Background jobs failed to start (has `flask db upgrade` been run?)", exc_info=True)


def _register_cli(app: Flask) -> None:
    @app.cli.command("create-superadmin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_superadmin(name, email, password):
        """Create (or promote) an active super admin account. The password is
        chosen here by the person running the command, so no forced change."""
        from app.Admin.model import User
        from app.Admin.route import validate_new_password
        from app.utils.dates import utcnow
        from app.utils.http import ValidationError

        email = email.strip().lower()
        try:
            validate_new_password(password, email=email)
        except ValidationError as e:
            raise click.ClickException(e.message)
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user is None:
            user = User(name=name.strip(), email=email)
            db.session.add(user)
        user.password = User.generate_password_hash(password)
        user.role = "super_admin"
        user.status = "active"
        user.must_change_password = False
        user.password_changed_at = utcnow()
        db.session.commit()
        click.echo(f"Super admin ready: {email}")


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 4455)))
