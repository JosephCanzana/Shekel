from app.models.base import BaseModel
from app.extensions import db


class DefectDetail(BaseModel):
    __tablename__ = "Defect_Details"

    defect_detail_id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    defect_id               = db.Column(db.Integer, db.ForeignKey("Defects.defect_id"),    nullable=False)
    product_id = db.Column(db.String(100), db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    quantity                = db.Column(db.Integer,                                         nullable=False)

    # why the item is being reported
    reason                  = db.Column(
        db.Enum("defect", "damage", "expired", "change_of_mind", validate_strings=True),
        nullable=False
    )

    # the inventory outcome:
    #   pending  → available -qty, defective +qty        (on watch)
    #   loss     → available -qty (fresh log)
    #              OR defective -qty (reviewed from pending)  (gone)
    #   returned → defective -qty, available +qty        (back to shelf, from pending only)
    #              also auto-set when reason = change_of_mind (straight back, skips defective)
    compensation            = db.Column(
        db.Enum("pending", "loss", "returned", validate_strings=True),
        nullable=False,
        default="pending"
    )

    # price snapshot at time of logging
    cost_price_at_defect    = db.Column(db.Numeric(10, 2), nullable=False)
    revenue_price_at_defect = db.Column(db.Numeric(10, 2), nullable=False)
    price_at_defect         = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_unit           = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_revenue        = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal_amount         = db.Column(db.Numeric(10, 2), nullable=False)

    # optional — only for change_of_mind returns where cashier links to original receipt
    # NULL for stocking-logged defects (expired/damage/loss) — no originating sale
    transaction_id          = db.Column(
        db.Integer,
        db.ForeignKey("Sales.transaction_id", ondelete="SET NULL"),
        nullable=True
    )

    # who reviewed and changed compensation from pending → returned/loss
    # NULL until admin/co-admin acts on it
    reviewed_by             = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=True)
    reviewed_at             = db.Column(db.DateTime,                                nullable=True)

    defect   = db.relationship("Defect",  back_populates="defect_details", passive_deletes=True)
    product  = db.relationship("Product", back_populates="defect_details", passive_deletes=True)
    reviewer = db.relationship("User",    foreign_keys=[reviewed_by])
    sale     = db.relationship("Sale",    foreign_keys=[transaction_id])