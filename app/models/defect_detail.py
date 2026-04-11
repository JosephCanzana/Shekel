from app.models.base import BaseModel
from app.extensions import db


class DefectDetail(BaseModel):
    __tablename__ = "Defect_Details"

    defect_detail_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    defect_id = db.Column(db.Integer, db.ForeignKey("Defects.defect_id"), nullable=False)
    product_id = db.Column(
        db.String(100),
        db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity = db.Column(db.Integer, nullable=False)

    # ── Origin ────────────────────────────────────────────────────────────────
    origin = db.Column(
        db.Enum("in_store", "customer", validate_strings=True),
        nullable=False,
        default="in_store",
    )

    # ── Reason ────────────────────────────────────────────────────────────────
    reason = db.Column(
        db.Enum("damaged", "expired", "change_of_mind", validate_strings=True),
        nullable=False,
    )

    # ── Workflow status ───────────────────────────────────────────────────────
    status = db.Column(
        db.Enum("submitted", "active", "rejected", validate_strings=True),
        nullable=False,
        default="submitted",
    )

    # ── Customer compensation ─────────────────────────────────────────────────
    customer_compensation = db.Column(
        db.Enum(
            "full_refund",
            "partial_refund",
            "exchange_same",
            "exchange_different",
            "none",
            validate_strings=True,
        ),
        nullable=False,
        default="none",
    )

    # ── Supplier compensation ─────────────────────────────────────────────────
    supplier_compensation = db.Column(
        db.Enum(
            "pending",
            "loss",
            "same_item",
            "different_item",
            "money",
            "none",
            validate_strings=True,
        ),
        nullable=False,
        default="pending",
    )

    # ── DEPRECATED — kept for rows created before the Defect_Exchange_Items
    #    migration. Do NOT write to this column for new records. All new
    #    exchange_different entries use the Defect_Exchange_Items child table.
    #    price_difference is also deprecated for the same reason; the computed
    #    value is sum(exchange_items.price_at_exchange * qty) - subtotal_amount.
    exchange_product_id = db.Column(
        db.String(100),
        db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
    )
    price_difference = db.Column(db.Numeric(10, 2), nullable=True)

    proposed_supplier_compensation = db.Column(
        db.Enum("loss", "same_item", "different_item", "money", validate_strings=True),
        nullable=True,
    )

    # ── Price snapshot ────────────────────────────────────────────────────────
    cost_price_at_defect    = db.Column(db.Numeric(10, 2), nullable=False)
    revenue_price_at_defect = db.Column(db.Numeric(10, 2), nullable=False)
    price_at_defect         = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_unit           = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_revenue        = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_amount         = db.Column(db.Numeric(10, 2), nullable=False)

    # ── Transaction reference (customer returns only) ─────────────────────────
    transaction_id = db.Column(
        db.Integer,
        db.ForeignKey("Sales.transaction_id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Approval / review ─────────────────────────────────────────────────────
    reviewed_by    = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=True)
    reviewed_at    = db.Column(db.DateTime, nullable=True)
    rejection_note = db.Column(db.Text, nullable=True)

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    archived_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=True)
    archived_at = db.Column(db.DateTime, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    defect           = db.relationship("Defect",  back_populates="defect_details", passive_deletes=True)
    product          = db.relationship("Product", foreign_keys=[product_id], back_populates="defect_details", passive_deletes=True)
    exchange_product = db.relationship("Product", foreign_keys=[exchange_product_id])  # deprecated
    reviewer         = db.relationship("User",    foreign_keys=[reviewed_by])
    archiver         = db.relationship("User",    foreign_keys=[archived_by])
    sale             = db.relationship("Sale",    foreign_keys=[transaction_id])

    # New: one DefectDetail → many DefectExchangeItems
    exchange_items   = db.relationship(
        "DefectExchangeItem",
        back_populates="defect_detail",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def computed_price_difference(self):
        """
        Sum of (price_at_exchange × quantity) across all exchange items,
        minus the original subtotal_amount of this detail.
        Positive  → customer / store pays extra.
        Negative  → store gives change back.
        None      → no exchange items recorded.
        """
        if not self.exchange_items:
            return None
        exchange_total = sum(
            float(ei.price_at_exchange) * ei.quantity
            for ei in self.exchange_items
            if not ei.no_money_exchange
        )
        return round(exchange_total - float(self.subtotal_amount), 2)