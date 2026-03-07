from app.models.base import BaseModel
from app.extensions import db


class Category(BaseModel):
    __tablename__ = "Categories"

    category_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)

    products = db.relationship("Product", back_populates="category")
