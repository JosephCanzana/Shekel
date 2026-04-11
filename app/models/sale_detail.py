from app.models.base import BaseModel
from app.extensions import db


class SaleDetail(BaseModel):
    __tablename__ = "Sales_Details"

    sale_detail_id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transaction_id        = db.Column(db.Integer, db.ForeignKey("Sales.transaction_id"), nullable=False)
    product_id            = db.Column(
        db.String(100),
        db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity              = db.Column(db.Integer,       nullable=False)
    cost_price_at_sale    = db.Column(db.Numeric(10, 2), nullable=False)
    revenue_price_at_sale = db.Column(db.Numeric(10, 2), nullable=False)
    price_at_sale         = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_unit         = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_revenue      = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_amount       = db.Column(db.Numeric(10, 2), nullable=False)

    # Set to True when the cashier charged this specific line item despite
    # quantity exceeding quantity_available at charge time.
    # Pinpoints exactly which product caused the stock discrepancy.
    # Does NOT block the sale.
    override_used         = db.Column(db.Boolean, nullable=False, default=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    sale    = db.relationship("Sale",    back_populates="sale_details", passive_deletes=True)
    product = db.relationship("Product", back_populates="sale_details", passive_deletes=True)