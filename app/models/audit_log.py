from app.models.base import BaseModel
from app.extensions import db


class AuditLog(BaseModel):
    __tablename__ = "Audit_Log"

    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    action_type = db.Column(
        db.Enum("INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", validate_strings=True),
        nullable=False,
    )
    # ⚠️  Values are PascalCase to match the existing DB enum exactly.
    #     'Settings' and 'Auth' are NEW values — run this ALTER before using them:
    #
    #       ALTER TABLE Audit_Log
    #         MODIFY COLUMN module
    #           ENUM('Products','Inventory','Sales','Defects',
    #                'Users','Stock_In','Settings','Auth')
    #           NOT NULL;
    #
    #     Alternatively: flask db migrate -m "expand audit_log module enum"
    #                    flask db upgrade
    module = db.Column(
        db.Enum(
            "Products",
            "Inventory",
            "Sales",
            "Defects",
            "Users",
            "Stock_In",
            "Settings",
            "Auth",
            validate_strings=True,
        ),
        nullable=False,
    )
    reference_id    = db.Column(db.String(100), nullable=True)
    reference_table = db.Column(db.String(50), nullable=True)
    description     = db.Column(db.Text, nullable=False)
    action_datetime = db.Column(
        db.DateTime, nullable=False, server_default=db.func.now()
    )

    user = db.relationship("User", back_populates="audit_logs")

    @classmethod
    def log(
        cls,
        action_type: str,
        module: str,
        description: str,
        *,
        reference_id: int | None = None,
        reference_table: str | None = None,
        user_id: int | None = None,
    ) -> "AuditLog | None":
        """
        Add an audit entry to the current session.  The caller must commit.

        Falls back to ``current_user`` when ``user_id`` is not supplied.
        Returns ``None`` if no user could be resolved (safe to ignore).

        Module must be one of (exact case):
            Products | Inventory | Sales | Defects | Users | Stock_In | Settings | Auth

        Example::

            AuditLog.log(
                "INSERT", "Sales",
                f"Sale #{sale.transaction_id} — ₱{sale.total_amount:.2f}",
                reference_id=sale.transaction_id,
                reference_table="Sales",
            )
            db.session.commit()
        """
        from flask_login import current_user

        uid = user_id
        if uid is None:
            try:
                if current_user and current_user.is_authenticated:
                    uid = current_user.user_id
            except RuntimeError:
                pass

        if uid is None:
            return None

        entry = cls(
            user_id         = uid,
            action_type     = action_type,
            module          = module,
            description     = description,
            reference_id    = reference_id,
            reference_table = reference_table,
        )
        db.session.add(entry)
        return entry