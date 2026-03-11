from app.models.base import BaseModel
from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(BaseModel, UserMixin):
    __tablename__ = "Users"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(
        db.Enum("admin", "cashier", "stocking", "co-admin"), nullable=False
    )
    password = db.Column(db.String(255), nullable=False)
    status = db.Column(
        db.Enum("activated", "not_activated", "suspended", "archived"), nullable=False
    )

    # relationships
    recovery_detail = db.relationship(
        "RecoveryDetail", back_populates="user", uselist=False
    )
    stock_ins = db.relationship("StockIn", back_populates="user")
    sales = db.relationship("Sale", back_populates="user")
    defects = db.relationship("Defect", back_populates="user")
    audit_logs = db.relationship("AuditLog", back_populates="user")

    # Flask-Login requires get_id() to return a string
    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def set_status(self, status):
        self.status = status
    
    def to_dict(self):
        return {
        "user_id":    self.user_id,
        "first_name": self.first_name,
        "last_name":  self.last_name,
        "role":       self.role,
        "status":     self.status,
    }

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @classmethod
    def generate_id(cls):
        """
        Generate the next user ID in format [counter][year].
        e.g. 10012026, 10022026
        Imported inside method to avoid circular import.
        """
        from app.models.app_settings import AppSettings
        return AppSettings.next_user_id()

    @classmethod
    def get_default_password(cls):
        from app.models.app_settings import AppSettings
        return AppSettings.get_default_password()
