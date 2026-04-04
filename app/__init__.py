from flask import Flask, render_template, session
from flask_login import current_user, LoginManager
from dotenv import load_dotenv
from config import DevelopmentConfig
from app.extensions import db, login_manager, migrate, csrf, mail
from app.utils.helpers import to_pht

def create_app(test_config=None):
    load_dotenv()

    app = Flask(__name__)
    @app.template_filter("pht")
    def pht_filter(dt, fmt="%b %d, %Y %I:%M %p"):
        if dt is None:
            return ""
        return to_pht(dt).strftime(fmt)
    
    app.config.from_object(DevelopmentConfig)
    # For pytesting
    if test_config:
        app.config.update(test_config)

    # TODO: be removed later
    # Production error handler
    # if not app.debug and not app.testing:
    #     from app.errors.handlers import register_error_handlers
    #     register_error_handlers(app)


    # # ─── Bind Extensions to App ───────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    # ─── Login Manager Config ─────────────────────────────────
    # Where to redirect if a user tries to access a protected route
    login_manager.login_view = "auth.login"
    
    # Flash message shown when redirected
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ─── User Loader ──────────────────────────────────────────
    # Flask-Login calls this to reload the user from the session.
    from app.models.user import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ─── Register Blueprints ──────────────────────────────────

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    
    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    from app.routes.cashier import cashier_bp
    app.register_blueprint(cashier_bp)

    from app.routes.stocking import stocking_bp
    app.register_blueprint(stocking_bp)

    from app.routes.manage_users import manage_users_bp
    app.register_blueprint(manage_users_bp)

    from app.routes.manage_categories import manage_categories_bp
    app.register_blueprint(manage_categories_bp)

    from app.routes.inventory import inventory_bp
    app.register_blueprint(inventory_bp)

    from app.routes.defects import defects_bp
    app.register_blueprint(defects_bp)

    from app.routes.profile import profile_bp
    app.register_blueprint(profile_bp)

    from app.routes.info import info_bp
    app.register_blueprint(info_bp)

    from app.routes.settings import settings_bp
    app.register_blueprint(settings_bp)

    # ─── Context Processor ────────────────────────────────────────────────────────
    # Injects pending_requests_count into every template for the navbar badge.
    @app.context_processor
    def inject_pending_count():
        if current_user.is_authenticated and current_user.role in ("admin", "superadmin"):
            from app.models.stock_adjustment_request import StockAdjustmentRequest
            count = StockAdjustmentRequest.query.filter_by(status="pending").count()
            return {"pending_requests_count": count}
        return {"pending_requests_count": 0}   

    @app.route("/test")
    def test():
        return render_template("test.html")
    return app