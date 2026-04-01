from app.models.base import BaseModel
from app.extensions import db

class RoleColumnSetting(BaseModel):
    __tablename__ = "Role_Column_Settings"

    id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role      = db.Column(db.String(50), nullable=False)  # "admin", "stocking"
    page      = db.Column(db.String(50), nullable=False)  # "inventory"
    available = db.Column(db.Text, nullable=False)         # JSON list of allowed column keys
    defaults  = db.Column(db.Text, nullable=False)         # JSON list of default column keys