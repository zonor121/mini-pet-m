import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def create_app():
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

    from services.formatters import fmt_date, fmt_short_date
    from services.security import get_current_user

    app.jinja_env.globals.update(
        get_current_user=get_current_user,
        fmt_date=fmt_date,
        fmt_short_date=fmt_short_date,
    )

    from routes.admin import admin_bp
    from routes.auth import auth_bp
    from routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)