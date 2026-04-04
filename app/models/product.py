from app.models.base import BaseModel
from app.extensions import db


class Product(BaseModel):
    __tablename__ = "Products"

    product_id            = db.Column(db.String(100), primary_key=True)  # barcode / SKU
    product_name          = db.Column(db.String(150), nullable=False)
    category_id           = db.Column(db.Integer, db.ForeignKey("Categories.category_id"), nullable=True)
    cost_price            = db.Column(db.Numeric(10, 2), nullable=False)
    revenue_price         = db.Column(db.Numeric(10, 2), nullable=False)
    total_price         = db.Column(db.Numeric(10, 2), nullable=False)
    low_reorder_threshold = db.Column(db.Integer, nullable=False)
    status                = db.Column(db.Enum("active", "archived", validate_strings=True), nullable=False)
    created_at            = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # relationships
    category       = db.relationship("Category",      back_populates="products")
    inventory      = db.relationship("Inventory",     back_populates="product", uselist=False)
    bundle         = db.relationship("ProductBundle", back_populates="product", uselist=False)
    stock_ins      = db.relationship("StockIn",       back_populates="product")
    sale_details   = db.relationship("SaleDetail",    back_populates="product", passive_deletes=True)
    defect_details = db.relationship(
        "DefectDetail",
        foreign_keys="[DefectDetail.product_id]",
        back_populates="product",
        passive_deletes=True,)
    adjustment_details = db.relationship("StockAdjustmentDetail", back_populates="product")

    def to_dict(self):
        return {
            "product_id":            self.product_id,
            "product_name":          self.product_name,
            "category_id":           self.category_id,
            "category_name":         self.category.category_name if self.category else "—",
            "bundle_id":             self.bundle.bundle_id    if self.bundle else None,
            "bundle_name":           self.bundle.bundle_name  if self.bundle else "—",
            "bundle_count":          self.bundle.bundle_count if self.bundle else None,
            "cost_price":            float(self.cost_price),
            "revenue_price":         float(self.revenue_price),
            "total_price":           float(self.total_price),
            "low_reorder_threshold": self.low_reorder_threshold,
            "status":                self.status,
            "stock":                 self.inventory.quantity_available if self.inventory else 0,
            "created_at":            self.created_at.strftime("%b %d, %Y") if self.created_at else "",
            "last_updated":          self.inventory.last_updated.strftime("%b %d, %Y") if self.inventory and self.inventory.last_updated else "—",  # ← add
        }