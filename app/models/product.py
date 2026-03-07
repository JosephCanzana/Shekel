from app.models.base import BaseModel
from app.extensions import db


class Product(BaseModel):
    __tablename__ = "Products"

    product_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_name = db.Column(db.String(150), nullable=False)
    category_id = db.Column(
        db.Integer, db.ForeignKey("Categories.category_id"), nullable=True
    )
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    revenue_price = db.Column(db.Numeric(10, 2), nullable=False)
    product_price = db.Column(db.Numeric(10, 2), nullable=False)
    low_reorder_threshold = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum("active", "archived"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    category = db.relationship("Category", back_populates="products")
    inventory = db.relationship("Inventory", back_populates="product", uselist=False)
    stock_ins = db.relationship("StockIn", back_populates="product")
    sale_details = db.relationship("SaleDetail", back_populates="product")
    defect_details = db.relationship("DefectDetail", back_populates="product")
