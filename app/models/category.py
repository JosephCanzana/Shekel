from datetime import datetime
from app.models.base import BaseModel
from app.extensions import db

class Category(BaseModel):
    __tablename__ = "Categories"  # lowercase is convention

    category_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_name = db.Column(db.String(100), nullable=False, unique=True)
    description   = db.Column(db.Text, nullable=True)
    status        = db.Column(db.String(20), nullable=False, default="active")
    default_low_stock_threshold = db.Column(db.Integer, default=5, nullable=False)

    products = db.relationship("Product", back_populates="category")

    def to_dict(self):
        return {
            "category_id":                  self.category_id,
            "name":                         self.category_name,
            "description":                  self.description or "",
            "status":                       self.status,
            "default_low_stock_threshold":  int(self.default_low_stock_threshold),  # ← wrap in int()
        }