from app.models.base import BaseModel
from app.extensions import db


class Defect(BaseModel):
    """
    Header record — one per log session, acts as a defect 'transaction'.
    Totals snapshotted at commit for fast reporting, same pattern as Sale.
    """
    __tablename__ = "Defects"

    defect_id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    defect_datetime     = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    user_id             = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)

    # snapshotted totals across all details in this log
    total_unit_price    = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_revenue_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_amount        = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    user           = db.relationship("User",         back_populates="defects")
    defect_details = db.relationship("DefectDetail", back_populates="defect",
                                     cascade="all, delete-orphan")