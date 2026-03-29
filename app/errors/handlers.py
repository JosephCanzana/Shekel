from flask import render_template, redirect, url_for, flash, current_app
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

def register_error_handlers(app):

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash("Session expired. Please resubmit the form.", "warning")
        return redirect(url_for("auth.login"))

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        return render_template(
            "errors/http_error.html",
            code=e.code,
            name=e.name,
            description=e.description
        ), e.code

    @app.errorhandler(Exception)
    def handle_exception(e):
        current_app.logger.error(e)
        return render_template("errors/500.html"), 500