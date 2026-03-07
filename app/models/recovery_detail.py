from app.models.base import BaseModel
from app.extensions import db


class RecoveryDetail(BaseModel):
    __tablename__ = "Recovery_Details"

    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    reset_token = db.Column(db.String(255), nullable=True)
    token_expiry = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="recovery_detail")
