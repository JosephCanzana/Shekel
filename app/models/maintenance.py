from app.extensions import db
from datetime import datetime

class MaintenanceSettings(db.Model):
    __tablename__ = "maintenance_settings"

    id              = db.Column(db.Integer, primary_key=True)
    is_active       = db.Column(db.Boolean, default=False, nullable=False)
    # When maintenance will start (None = not scheduled)
    scheduled_start = db.Column(db.DateTime, nullable=True)
    # Optional: estimated restoration time shown on maintenance page
    estimated_end   = db.Column(db.DateTime, nullable=True)
    auto_end        = db.Column(db.Boolean, default=True, nullable=False)
    # Whether to show the end-time countdown on the maintenance page
    show_countdown  = db.Column(db.Boolean, default=True, nullable=False)
    message         = db.Column(db.Text, nullable=True)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get():
        """Always returns a single settings row, creating one if needed."""
        row = MaintenanceSettings.query.first()
        if not row:
            row = MaintenanceSettings(
                is_active=False,
                show_countdown=True,
                message="We're performing scheduled maintenance. Be right back!"
            )
            db.session.add(row)
            db.session.commit()
        return row