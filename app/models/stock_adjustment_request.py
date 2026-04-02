from app.models.base import BaseModel
from app.extensions import db


class StockAdjustmentRequest(BaseModel):
    __tablename__ = "Stock_Adjustment_Requests"

    request_id    = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Who & When ────────────────────────────────────────────
    requested_by  = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=False)
    reviewed_by   = db.Column(db.Integer, db.ForeignKey("Users.user_id"), nullable=True)
    submitted_at  = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    reviewed_at   = db.Column(db.DateTime, nullable=True)

    # ── Type: "stock_in" or "adjustment" ──────────────────────
    # stock_in   → stocking account reporting new stock received
    # adjustment → stocking account correcting a discrepancy (requires note per item)
    request_type  = db.Column(
        db.Enum("stock_in", "adjustment", validate_strings=True),
        nullable=False,
        default="stock_in"
    )

    # ── Overall Batch Status ───────────────────────────────────
    # pending            → awaiting admin review
    # approved           → all items approved
    # partially_approved → some items approved, some rejected
    # rejected           → all items rejected
    status        = db.Column(
        db.Enum("pending", "approved", "partially_approved", "rejected", validate_strings=True),
        nullable=False,
        default="pending"
    )

    # ── Relationships ──────────────────────────────────────────
    requester = db.relationship(
        "User",
        foreign_keys=[requested_by],
        back_populates="adjustment_requests_made"
    )
    reviewer  = db.relationship(
        "User",
        foreign_keys=[reviewed_by],
        back_populates="adjustment_requests_reviewed"
    )
    details   = db.relationship(
        "StockAdjustmentDetail",
        back_populates="request",
        cascade="all, delete-orphan"
    )

    # ── Helpers ────────────────────────────────────────────────
    @property
    def pending_count(self):
        return sum(1 for d in self.details if d.status == "pending")

    @property
    def approved_count(self):
        return sum(1 for d in self.details if d.status == "approved")

    @property
    def rejected_count(self):
        return sum(1 for d in self.details if d.status == "rejected")

    def recompute_status(self):
        """Call after reviewing details to sync the batch-level status."""
        statuses = {d.status for d in self.details}
        if statuses == {"approved"}:
            self.status = "approved"
        elif statuses == {"rejected"}:
            self.status = "rejected"
        elif "approved" in statuses:
            self.status = "partially_approved"
        # else: still has pending items — leave as pending

    def to_dict(self):
        return {
            "request_id":      self.request_id,
            "request_type":    self.request_type,
            "status":          self.status,
            "requested_by":    self.requester.full_name if self.requester else "—",
            "reviewed_by":     self.reviewer.full_name  if self.reviewer  else "—",
            "submitted_at":    self.submitted_at.strftime("%b %d, %Y %I:%M %p") if self.submitted_at else "—",
            "reviewed_at":     self.reviewed_at.strftime("%b %d, %Y %I:%M %p")  if self.reviewed_at  else "—",
            "pending_count":   self.pending_count,
            "approved_count":  self.approved_count,
            "rejected_count":  self.rejected_count,
            "details":         [d.to_dict() for d in self.details],
        }