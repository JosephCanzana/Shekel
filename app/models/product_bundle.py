from app.models.base import BaseModel
from app.extensions import db


class ProductBundle(BaseModel):
    __tablename__ = "ProductBundles"

    bundle_id    = db.Column(db.String(100), primary_key=True)  # bundle barcode / SKU
    product_id = db.Column(db.String(100), db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    bundle_name  = db.Column(db.String(100), nullable=False)    # e.g. "12-pack"
    bundle_count = db.Column(db.Integer, nullable=False)        # units per bundle e.g. 24

    product = db.relationship("Product", back_populates="bundle")