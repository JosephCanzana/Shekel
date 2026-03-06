from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from config import DevelopmentConfig

# ─── Extensions ───────────────────────────────────────────────
# Initialized here but not tied to any app yet.
# They get connected to the app inside create_app() via .init_app()
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

def create_app():
    load_dotenv()

    app = Flask(__name__)
    # app.config.from_object(DevelopmentConfig)

    # # ─── Bind Extensions to App ───────────────────────────────
    # db.init_app(app)
    # login_manager.init_app(app)
    # migrate.init_app(app, db)
    # csrf.init_app(app)

    # # ─── Login Manager Config ─────────────────────────────────
    # # Where to redirect if a user tries to access a protected route
    # login_manager.login_view = "auth.login"
    # # Flash message shown when redirected
    # login_manager.login_message = "Please log in to access this page."
    # login_manager.login_message_category = "warning"

    # ─── User Loader ──────────────────────────────────────────
    # Flask-Login calls this to reload the user from the session.
    # Import is here (not top-level) to avoid circular imports.
    # from app.models.user import User

    # @login_manager.user_loader
    # def load_user(user_id):
    #     return User.query.get(int(user_id))

    # ─── Register Blueprints ──────────────────────────────────
    # Uncomment each one as you build and create the route file.

    # from app.routes.auth import auth_bp
    # app.register_blueprint(auth_bp)

    # from app.routes.sales import sales_bp
    # app.register_blueprint(sales_bp)

    # from app.routes.inventory import inventory_bp
    # app.register_blueprint(inventory_bp)

    # from app.routes.stock_in import stock_in_bp
    # app.register_blueprint(stock_in_bp)

    # from app.routes.defects import defects_bp
    # app.register_blueprint(defects_bp)

    # from app.routes.users import users_bp
    # app.register_blueprint(users_bp)

    # from app.routes.reports import reports_bp
    # app.register_blueprint(reports_bp)

    @app.route("/test")
    def test():
        return "It's Working!"
    return app