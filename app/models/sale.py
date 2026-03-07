from app.models.base import BaseModel
from app.extensions import db


class Sale(BaseModel):
    __tablename__ = "Sales"

    transaction_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sale_datetime = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    total_unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_revenue_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)

    user = db.relationship("User", back_populates="sales")
    sale_details = db.relationship("SaleDetail", back_populates="sale")
