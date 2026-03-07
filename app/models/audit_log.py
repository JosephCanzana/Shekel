from app.models.base import BaseModel
from app.extensions import db


class AuditLog(BaseModel):
    __tablename__ = "Audit_Log"

    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    action_type = db.Column(
        db.Enum("INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT"), nullable=False
    )
    module = db.Column(
        db.Enum("products", "inventory", "sales", "defects", "users", "stock_in"),
        nullable=False,
    )
    reference_id = db.Column(db.Integer, nullable=True)
    reference_table = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=False)
    action_datetime = db.Column(
        db.DateTime, nullable=False, server_default=db.func.now()
    )
    user = db.relationship("User", back_populates="audit_logs")
