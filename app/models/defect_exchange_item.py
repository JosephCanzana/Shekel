from app.models.base import BaseModel
from app.extensions import db


class DefectExchangeItem(BaseModel):
    __tablename__ = "Defect_Exchange_Items"

    exchange_item_id  = db.Column(db.Integer, primary_key=True, autoincrement=True)

    defect_detail_id  = db.Column(
        db.Integer,
        db.ForeignKey("Defect_Details.defect_detail_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id        = db.Column(
        db.String(100),
        db.ForeignKey("Products.product_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )

    # How many units of this exchange product are given out
    quantity          = db.Column(db.Integer, nullable=False, default=1)

    # Price of the exchange product at the time of exchange
    price_at_exchange = db.Column(db.Numeric(10, 2), nullable=False)

    # True  → ignore the price difference; treat as a straight swap
    # False → price_at_exchange − original price_at_defect is charged / refunded
    no_money_exchange = db.Column(db.Boolean, nullable=False, default=False)

    # Set to True when adding this exchange item caused quantity_available < 0
    # on the exchange product's inventory — flags a stock discrepancy for auditing
    override_used     = db.Column(db.Boolean, nullable=False, default=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    defect_detail = db.relationship(
        "DefectDetail",
        back_populates="exchange_items",
    )
    product = db.relationship(
        "Product",
        foreign_keys=[product_id],
    )