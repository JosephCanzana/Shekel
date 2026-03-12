from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class AppSettings(db.Model):
    __tablename__ = "App_Settings"

    id               = db.Column(db.Integer, primary_key=True, default=1)
    user_counter     = db.Column(db.Integer, nullable=False, default=1000)
    counter_year     = db.Column(db.Integer, nullable=False)
    default_password = db.Column(db.String(255), nullable=False, default="shekel123")
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls):
        """Get the single settings row, creating it if it doesn't exist."""
        settings = cls.query.first()
        if not settings:
            settings = cls(
                id           = 1,
                counter_year = datetime.utcnow().year,
            )
            db.session.add(settings)
            db.session.commit()
        return settings

    @classmethod
    def next_user_id(cls):
        """
        Generate the next user ID in the format [counter][year].
        e.g. 10012026, 10022026, 10032026

        Resets counter to 1000 when the year changes.
        Uses row-level lock to prevent duplicates under concurrent requests.
        """
        settings = cls.query.with_for_update().first()
        if not settings:
            settings = cls(id=1, counter_year=datetime.utcnow().year)
            db.session.add(settings)

        current_year = datetime.utcnow().year

        # reset counter if year has changed
        if settings.counter_year != current_year:
            settings.counter_year = current_year
            settings.user_counter = 1000

        # build the ID: counter + year as a single integer
        # e.g. counter=1001, year=2026 → "10012026" → 10012026
        generated_id = int(f"{settings.user_counter}{current_year}")

        # increment for next use
        settings.user_counter += 1
        settings.updated_at = datetime.utcnow()

        db.session.commit()
        return generated_id

    @classmethod
    def get_default_password(cls):
        """Return the current default password."""
        return cls.get().default_password

    @classmethod
    def set_default_password(cls, new_password):
        """Update the default password."""
        settings = cls.get()
        settings.default_password = new_password
        settings.updated_at = datetime.utcnow()
        db.session.commit()

    def to_dict(self):
        return {
            "user_counter":     self.user_counter,
            "counter_year":     self.counter_year,
            "default_password": self.default_password,
            "updated_at":       self.updated_at.isoformat() if self.updated_at else None,
        }