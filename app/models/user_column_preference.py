from app.models.base import BaseModel
from app.extensions import db

class UserColumnPreference(BaseModel):
    __tablename__ = "User_Column_Preferences"

    id      = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    page    = db.Column(db.String(50), nullable=False)
    columns = db.Column(db.Text, nullable=False)  # JSON list of enabled column keys

    user = db.relationship("User", back_populates="column_preferences")