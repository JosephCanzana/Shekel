"""
tests/defect_test.py

Pytest suite for Defect model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - defect_datetime auto-populated via server_default
   - transaction_id autoincrements
   - Multiple defects allowed per user (no unique constraint)

2. Foreign Key Constraints
   - user_id must reference an existing User row
   - Invalid user_id is blocked
   - Inserting after user deletion is blocked

3. Numeric Precision — financial totals
   - total_cost_price, total_revenue_price, total_amount stored as Decimal
   - Correct 2dp precision confirmed
   - Zero and large values accepted

4. Update Behavior
   - Total fields can be updated and persisted after save()

5. Relationship — User ↔ Defect
   - defect.user returns the linked User instance
   - user.defects returns list of user's defect records

6. Relationship — Defect ↔ DefectDetail (cascade="all, delete-orphan")
   - Deleting a Defect cascades and removes all child DefectDetail rows
   - defect.defect_details returns the list of detail rows
   - A new Defect with no details has an empty list

7. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with Defect's specific schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from app.extensions import db
from app.models.defect import Defect
from app.models.defect_detail import DefectDetail
from app.models.user import User


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(user):
    """
    Returns a dict of all valid fields for a Defect.
    Depends on the shared `user` fixture from conftest.py.
    """
    return dict(
        user_id=user.user_id,
        total_cost_price=Decimal("20.00"),
        total_revenue_price=Decimal("24.00"),
        total_amount=Decimal("30.00"),
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are enforced by the DB.
#    WHY:  Defect records are financial and audit-critical. A defect saved
#          without a total or without a user reference would silently corrupt
#          loss reports and make the record untraceable.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_defect_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should commit cleanly
        Defect(**valid_data).save()
        assert Defect.query.count() == 1

    def test_user_id_is_required(self, app, valid_data):
        # user_id is FK and NOT NULL — every defect must belong to a user
        valid_data.pop("user_id")
        with pytest.raises(Exception):
            Defect(**valid_data).save()

    def test_total_cost_price_is_required(self, app, valid_data):
        # total_cost_price is NOT NULL — omitting raises
        valid_data.pop("total_cost_price")
        with pytest.raises(Exception):
            Defect(**valid_data).save()

    def test_total_revenue_price_is_required(self, app, valid_data):
        # total_revenue_price is NOT NULL — omitting raises
        valid_data.pop("total_revenue_price")
        with pytest.raises(Exception):
            Defect(**valid_data).save()

    def test_total_amount_is_required(self, app, valid_data):
        # total_amount is NOT NULL — omitting raises
        valid_data.pop("total_amount")
        with pytest.raises(Exception):
            Defect(**valid_data).save()

    def test_defect_id_autoincrements(self, app, valid_data):
        # Each new Defect gets a higher defect_id automatically
        d1 = Defect(**valid_data).save()
        d2 = Defect(**{**valid_data}).save()

        assert d2.defect_id > d1.defect_id

    def test_defect_datetime_is_set_automatically(self, app, defect):
        # defect_datetime uses server_default=db.func.now() —
        # it should be populated without being set manually
        result = Defect.get_by_id(defect.defect_id)
        assert result.defect_datetime is not None
        assert isinstance(result.defect_datetime, datetime)

    def test_multiple_defects_allowed_per_user(self, app, valid_data):
        # A user can log multiple defect records — no unique constraint
        Defect(**valid_data).save()
        Defect(**{**valid_data}).save()
        Defect(**{**valid_data}).save()

        assert Defect.query.count() == 3


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that user_id must reference a real User row.
#    WHY:  Every defect must be traceable to the staff member who logged it.
#          An orphan defect with no user breaks audit trails, reports,
#          and any route that tries to display defect.user.full_name.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_user_id_raises(self, app, valid_data):
        # Nonexistent user_id should be blocked by FK constraint
        valid_data["user_id"] = 99999999
        with pytest.raises(Exception):
            Defect(**valid_data).save()

    def test_valid_user_id_saves(self, app, valid_data):
        # Confirm FK with a real user_id saves cleanly
        Defect(**valid_data).save()
        assert Defect.query.count() == 1

    def test_defect_blocked_after_user_deleted(self, app, valid_data, user):
        # After the referenced user is deleted, inserting a new defect
        # with that user_id should be blocked by FK constraint
        user.delete()
        with pytest.raises(Exception):
            Defect(**valid_data).save()


# ---------------------------------------------------------------------------
# 3. Numeric Precision — financial totals
#
#    WHAT: Verifies Decimal storage and retrieval for all three total fields.
#    WHY:  These totals are used in loss/damage reports. Float imprecision
#          or wrong types would silently produce incorrect financial summaries
#          that are hard to detect until reconciliation time.
# ---------------------------------------------------------------------------

class TestNumericPrecision:
    def test_totals_stored_as_decimal(self, app, defect):
        # All three total fields must be Decimal, not float
        result = Defect.get_by_id(defect.defect_id)

        assert isinstance(result.total_cost_price, Decimal)
        assert isinstance(result.total_revenue_price, Decimal)
        assert isinstance(result.total_amount, Decimal)

    def test_totals_stored_with_two_decimal_places(self, app, defect):
        # Values should round-trip correctly at 2dp precision
        result = Defect.get_by_id(defect.defect_id)

        assert result.total_cost_price == Decimal("20.00")
        assert result.total_revenue_price == Decimal("24.00")
        assert result.total_amount == Decimal("30.00")

    def test_zero_totals_accepted(self, app, valid_data):
        # Zero is a valid total — e.g. a defect with no monetary value
        valid_data["total_cost_price"] = Decimal("0.00")
        valid_data["total_revenue_price"] = Decimal("0.00")
        valid_data["total_amount"] = Decimal("0.00")
        Defect(**valid_data).save()

        result = Defect.query.first()
        assert result.total_amount == Decimal("0.00")

    def test_large_totals_within_numeric_bounds(self, app, valid_data):
        # Numeric(10, 2) supports values up to 99999999.99
        valid_data["total_cost_price"] = Decimal("99999999.99")
        valid_data["total_revenue_price"] = Decimal("99999999.99")
        valid_data["total_amount"] = Decimal("99999999.99")
        Defect(**valid_data).save()

        result = Defect.query.first()
        assert result.total_amount == Decimal("99999999.99")

    def test_non_round_total_retains_precision(self, app, valid_data):
        # Non-round values should survive the DB round-trip without drift
        valid_data["total_amount"] = Decimal("123.45")
        Defect(**valid_data).save()

        result = Defect.query.first()
        assert result.total_amount == Decimal("123.45")


# ---------------------------------------------------------------------------
# 4. Update Behavior
#
#    WHAT: Verifies that defect totals can be corrected and persisted.
#    WHY:  Although defects are typically immutable once logged, correction
#          workflows exist. Confirms the model supports it without silent
#          failures.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_total_amount(self, app, defect):
        # Simulates a corrected total being applied to a defect record
        defect.total_amount = Decimal("999.99")
        defect.save()

        result = Defect.get_by_id(defect.defect_id)
        assert result.total_amount == Decimal("999.99")

    def test_update_total_cost_price(self, app, defect):
        # total_cost_price can be corrected and saved
        defect.total_cost_price = Decimal("55.50")
        defect.save()

        result = Defect.get_by_id(defect.defect_id)
        assert result.total_cost_price == Decimal("55.50")

    def test_update_total_revenue_price(self, app, defect):
        # total_revenue_price can be corrected and saved
        defect.total_revenue_price = Decimal("66.60")
        defect.save()

        result = Defect.get_by_id(defect.defect_id)
        assert result.total_revenue_price == Decimal("66.60")

    def test_update_all_totals(self, app, defect):
        # All three totals can be updated in one save()
        defect.total_cost_price = Decimal("10.00")
        defect.total_revenue_price = Decimal("12.00")
        defect.total_amount = Decimal("15.00")
        defect.save()

        result = Defect.get_by_id(defect.defect_id)
        assert result.total_cost_price == Decimal("10.00")
        assert result.total_revenue_price == Decimal("12.00")
        assert result.total_amount == Decimal("15.00")


# ---------------------------------------------------------------------------
# 5. Relationship — User ↔ Defect
#
#    WHAT: Verifies both sides of the Defect ↔ User relationship.
#    WHY:  Routes that render defect logs display defect.user.full_name
#          to identify who logged the defect. user.defects is used to
#          pull all defect history for a staff member. A broken
#          relationship silently returns None, making these routes crash
#          or render incorrectly.
# ---------------------------------------------------------------------------

class TestUserRelationship:
    def test_defect_user_returns_linked_user(self, app, defect, user):
        # defect.user should return the User who logged the defect
        db.session.refresh(defect)
        assert defect.user is not None
        assert defect.user.user_id == user.user_id

    def test_user_defects_returns_list_of_defects(self, app, defect, user):
        # user.defects should return a list containing the user's defects
        db.session.refresh(user)
        assert len(user.defects) == 1
        assert user.defects[0].defect_id == defect.defect_id

    def test_user_multiple_defects(self, app, user, valid_data):
        # A user can accumulate multiple defect records
        Defect(**valid_data).save()
        Defect(**{**valid_data}).save()
        Defect(**{**valid_data}).save()

        db.session.refresh(user)
        assert len(user.defects) == 3

    def test_defect_user_full_name_accessible(self, app, defect, user):
        # Confirms traversal through the relationship to read user fields
        # This is the pattern used in defect log routes
        db.session.refresh(defect)
        assert defect.user.full_name == user.full_name


# ---------------------------------------------------------------------------
# 6. Relationship — Defect ↔ DefectDetail (cascade="all, delete-orphan")
#
#    WHAT: Verifies that:
#          a) defect.defect_details returns associated rows
#          b) deleting a Defect cascades and removes all child DefectDetail
#             rows — confirmed by cascade="all, delete-orphan" in the model
#    WHY:  DefectDetail rows are meaningless without a parent Defect.
#          If cascade delete is broken, deleting a Defect would leave
#          orphan DefectDetail rows with a dangling defect_id FK, which
#          would pollute financial reports and cause FK errors on future
#          queries.
# ---------------------------------------------------------------------------

class TestDefectDetailRelationship:
    def test_defect_details_returns_associated_rows(self, app, defect, defect_detail):
        # defect.defect_details should return the list of line items
        db.session.refresh(defect)
        assert len(defect.defect_details) == 1
        assert defect.defect_details[0].defect_detail_id == defect_detail.defect_detail_id

    def test_defect_with_no_details_returns_empty_list(self, app, defect):
        # A freshly created Defect with no details should have an empty list
        db.session.refresh(defect)
        assert defect.defect_details == []

    def test_defect_detail_back_reference(self, app, defect, defect_detail):
        # defect_detail.defect should return the parent Defect instance
        db.session.refresh(defect_detail)
        assert defect_detail.defect is not None
        assert defect_detail.defect.defect_id == defect.defect_id

    def test_deleting_defect_cascades_to_details(self, app, defect, defect_detail):
        # cascade="all, delete-orphan" — deleting a Defect must also
        # delete all its associated DefectDetail rows automatically
        assert DefectDetail.query.count() == 1

        db.session.delete(defect)
        db.session.commit()

        assert DefectDetail.query.count() == 0
        assert Defect.query.count() == 0

    def test_multiple_details_all_cascade_on_delete(self, app, defect, product, second_product):
        # All child rows should be removed — not just the first one
        from decimal import Decimal
        base = dict(
            defect_id=defect.defect_id,
            quantity=1,
            reason="defect",
            compensation="pending",
            cost_price_at_defect=Decimal("10.00"),
            revenue_price_at_defect=Decimal("12.00"),
            price_at_defect=Decimal("15.00"),
            subtotal_unit=Decimal("10.00"),
            subtotal_revenue=Decimal("12.00"),
            subtotal_amount=Decimal("15.00"),
        )
        DefectDetail(**{**base, "product_id": product.product_id}).save()
        DefectDetail(**{**base, "product_id": second_product.product_id}).save()

        assert DefectDetail.query.count() == 2

        db.session.delete(defect)
        db.session.commit()

        assert DefectDetail.query.count() == 0


# ---------------------------------------------------------------------------
# 7. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with Defect's specific schema.
#    WHY:  BaseModel is abstract and tested in isolation via DummyModel.
#          These checks confirm Defect's schema — particularly the
#          server_default datetime and Numeric columns — doesn't break
#          anything inherited from BaseModel.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_defect(self, app, valid_data):
        # save() should commit the Defect row to the DB
        Defect(**valid_data).save()
        assert Defect.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        d = Defect(**valid_data)
        returned = d.save()
        assert returned is d

    def test_delete_removes_defect(self, app, defect):
        # delete() should remove the Defect row from the DB
        defect.delete()
        assert Defect.query.count() == 0

    def test_get_by_id_returns_correct_defect(self, app, defect):
        # get_by_id() should return the Defect with the matching defect_id
        result = Defect.get_by_id(defect.defect_id)

        assert result is not None
        assert result.defect_id == defect.defect_id
        assert result.total_amount == defect.total_amount

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent defect_id should return None, not raise
        result = Defect.get_by_id(99999)
        assert result is None

    def test_get_all_returns_all_defects(self, app, valid_data):
        # get_all() returns every row in the Defects table
        Defect(**valid_data).save()
        Defect(**{**valid_data}).save()

        result = Defect.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = Defect.get_all()
        assert result == []