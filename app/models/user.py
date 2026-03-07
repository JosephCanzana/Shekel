from app.models.base import BaseModel
from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(BaseModel, UserMixin):
    __tablename__ = "Users"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
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
