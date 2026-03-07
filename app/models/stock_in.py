from app.models.base import BaseModel
from app.extensions import db


class StockIn(BaseModel):
    __tablename__ = "Stock_In"

    stockin_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("Products.product_id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    quantity_received = db.Column(db.Integer, nullable=False)
    stockin_datetime = db.Column(
        db.DateTime, nullable=False, server_default=db.func.now()
    )
    notes = db.Column(db.Text, nullable=True)

    product = db.relationship("Product", back_populates="stock_ins")
    user = db.relationship("User", back_populates="stock_ins")
