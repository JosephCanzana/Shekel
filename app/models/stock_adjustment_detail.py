from app.models.base import BaseModel
from app.extensions import db


class StockAdjustmentDetail(BaseModel):
    __tablename__ = "Stock_Adjustment_Details"

    detail_id            = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Foreign Keys ───────────────────────────────────────────
    request_id           = db.Column(
        db.Integer,
        db.ForeignKey("Stock_Adjustment_Requests.request_id", ondelete="CASCADE"),
        nullable=False
    )
    product_id           = db.Column(
        db.String(100),
        db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )

    # ── Quantities ─────────────────────────────────────────────
    # quantity_requested → what the stocking account entered
    # quantity_approved  → what admin approved (can be less — partial approval)
    #                      NULL means not yet reviewed
    quantity_requested   = db.Column(db.Integer, nullable=False)
    quantity_approved    = db.Column(db.Integer, nullable=True)

    # ── Per-item Status ────────────────────────────────────────
    status               = db.Column(
        db.Enum("pending", "approved", "rejected", validate_strings=True),
        nullable=False,
        default="pending"
    )

    # ── Notes ──────────────────────────────────────────────────
    # note              → stocking account's reason (required for "adjustment" type)
    # rejection_reason  → admin's reason for rejecting this item
    note                 = db.Column(db.Text, nullable=True)
    rejection_reason     = db.Column(db.Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────
    request = db.relationship("StockAdjustmentRequest", back_populates="details")
    product = db.relationship("Product", back_populates="adjustment_details")

    # ── Helpers ────────────────────────────────────────────────
    def approve(self, quantity_approved=None):
        """Approve this line item. Defaults to full requested qty."""
        self.status = "approved"
        self.quantity_approved = quantity_approved if quantity_approved is not None else self.quantity_requested

    def reject(self, reason=None):
        """Reject this line item with an optional reason."""
        self.status = "rejected"
        self.rejection_reason = reason

    def to_dict(self):
        return {
            "detail_id":           self.detail_id,
            "request_id":          self.request_id,
            "product_id":          self.product_id,
            "product_name":        self.product.product_name if self.product else "—",
            "quantity_requested":  self.quantity_requested,
            "quantity_approved":   self.quantity_approved,
            "status":              self.status,
            "note":                self.note or "",
            "rejection_reason":    self.rejection_reason or "",
        }