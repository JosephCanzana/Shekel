from app.models.base import BaseModel
from app.extensions import db


class DefectDetail(BaseModel):
    __tablename__ = "Defect_Details"

    defect_detail_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    defect_id = db.Column(
        db.Integer, db.ForeignKey("Defects.defect_id"), nullable=False
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("Products.product_id"), nullable=False
    )
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(
        db.Enum("defect", "damage", "expired", "change_of_mind"), nullable=False
    )
    compensation = db.Column(
        db.Enum("pending", "loss", "returned", "replacement"), nullable=False
    )
    unit_price_at_defect = db.Column(db.Numeric(10, 2), nullable=False)
    revenue_price_at_defect = db.Column(db.Numeric(10, 2), nullable=False)
    price_at_defect = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_unit = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_revenue = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_amount = db.Column(db.Numeric(10, 2), nullable=False)

    defect = db.relationship("Defect", back_populates="defect_details")
    product = db.relationship("Product", back_populates="defect_details")
