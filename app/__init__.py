from flask import Flask, render_template
from dotenv import load_dotenv
from config import DevelopmentConfig
from app.extensions import db, login_manager, migrate, csrf

def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(DevelopmentConfig)

    # # ─── Bind Extensions to App ───────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # # ─── Login Manager Config ─────────────────────────────────
    # # Where to redirect if a user tries to access a protected route
    login_manager.login_view = "auth.login"
    
    # # # Flash message shown when redirected
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

    @app.route("/test")
    def test():
        return render_template("test.html")
    return app