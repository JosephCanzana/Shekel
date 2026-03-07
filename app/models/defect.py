from app.models.base import BaseModel
from app.extensions import db


class Defect(BaseModel):
    __tablename__ = "Defects"

    defect_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    defect_datetime = db.Column(
        db.DateTime, nullable=False, server_default=db.func.now()
    )
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    total_unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_revenue_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)

    user = db.relationship("User", back_populates="defects")
    defect_details = db.relationship("DefectDetail", back_populates="defect")
