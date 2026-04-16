# utils/seed_superadmin.py
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app()

with app.app_context():
    existing = User.query.filter_by(role="superadmin").first()

    if existing:
        print(f"Superadmin already exists → ID: {existing.user_id}, Name: {existing.full_name}")
    else:
        superadmin = User(
            user_id=User.generate_id(),
            first_name="Super",
            last_name="Admin",
            role="superadmin",
            status="activated"
        )
        superadmin.set_password("Shekel_123")

        db.session.add(superadmin)
        db.session.commit()

        print(f"Superadmin created → ID: {superadmin.user_id}, Name: {superadmin.full_name}")