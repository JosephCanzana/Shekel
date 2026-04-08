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

    # ── Origin ───────────────────────────────────────────────────────────────
    origin = db.Column(
        db.Enum("in_store", "customer", validate_strings=True),
        nullable=False,
        default="in_store",
    )

    # ── Reason ───────────────────────────────────────────────────────────────
    # defect + damage merged → damaged
    reason = db.Column(
        db.Enum("damaged", "expired", "change_of_mind", validate_strings=True),
        nullable=False,
    )

    # ── Workflow status ───────────────────────────────────────────────────────
    #   submitted → waiting for admin approval (stocking / cashier non-COM logs)
    #   active    → approved or admin-logged; inventory already adjusted
    #   rejected  → admin rejected the submission (no inventory change)
    status = db.Column(
        db.Enum("submitted", "active", "rejected", validate_strings=True),
        nullable=False,
        default="submitted",
    )

    # ── Customer compensation ─────────────────────────────────────────────────
    #   Only meaningful when origin = customer.
    #   In-store records always get 'none'.
    #
    #   full_refund        → 100% cash back to customer
    #   partial_refund     → cash refund with price difference handled
    #   exchange_same      → swap for the identical product
    #   exchange_different → swap for a different product (price_difference applies)
    #   none               → not applicable (in-store)
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
    #   pending        → on watch list, awaiting supplier decision
    #   loss           → supplier gives nothing; store absorbs cost
    #   same_item      → supplier replaces with identical item
    #   different_item → supplier replaces with a different item
    #   money          → supplier reimburses cash to store
    #   none           → not applicable (change_of_mind)
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

    # ── Exchange details (exchange_different only) ────────────────────────────
    exchange_product_id = db.Column(
        db.String(100),
        db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
    )
    # Positive  → customer pays more
    # Negative  → store gives change back
    # Null/zero → equal value
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
    product          = db.relationship("Product", foreign_keys=[product_id],          back_populates="defect_details", passive_deletes=True)
    exchange_product = db.relationship("Product", foreign_keys=[exchange_product_id])
    reviewer         = db.relationship("User",    foreign_keys=[reviewed_by])
    archiver = db.relationship("User", foreign_keys=[archived_by])
    sale             = db.relationship("Sale",    foreign_keys=[transaction_id])