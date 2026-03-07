from app.models.base import BaseModel
from app.extensions import db


class Inventory(BaseModel):
    __tablename__ = "Inventory"

    inventory_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("Products.product_id"), nullable=False, unique=True
    )
    quantity_available = db.Column(db.Integer, nullable=False, default=0)
    quantity_defective = db.Column(db.Integer, nullable=False, default=0)
    last_updated = db.Column(db.DateTime, nullable=False)

    product = db.relationship("Product", back_populates="inventory")
