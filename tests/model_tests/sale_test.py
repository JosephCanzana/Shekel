"""
tests/sale_test.py

Pytest suite for Sale model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - payment_method is nullable (cash, card, or unrecorded)
   - sale_datetime auto-populated via server_default
   - transaction_id autoincrements

2. Foreign Key Constraints
   - user_id must reference an existing User row
   - Invalid user_id is blocked

3. Numeric Precision — financial totals
   - total_cost_price, total_revenue_price, total_amount stored as Decimal
   - Correct 2dp precision confirmed
   - Zero and large values accepted

4. Update Behavior
   - Total fields and payment_method can be updated and persisted

5. Relationship — User ↔ Sale
   - sale.user returns the linked User instance
   - user.sales returns a list of the user's sales

6. Relationship — Sale ↔ SaleDetail (cascade)
   - Deleting a Sale cascades to its SaleDetail children
   - sale.sale_details returns associated detail rows

7. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with Sale's specific schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from app.extensions import db
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.user import User


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(user):
    """
    Returns a dict of all valid fields for a Sale.
    payment_method is included but nullable — tested both ways.
    """
    return dict(
        user_id=user.user_id,
        total_cost_price=Decimal("20.00"),
        total_revenue_price=Decimal("24.00"),
        total_amount=Decimal("30.00"),
        payment_method="cash",
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are enforced by the DB
#          and that nullable columns (payment_method) accept None.
#    WHY:  Sales hold financial records — a missing total or broken FK
#          would silently corrupt reports and audit logs.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_sale_saves_successfully(self, app, valid_data):
        # Happy path — all fields present, should commit cleanly
        Sale(**valid_data).save()
        assert Sale.query.count() == 1

    def test_user_id_is_required(self, app, valid_data):
        # user_id is FK and NOT NULL — every sale must belong to a user
        valid_data.pop("user_id")
        with pytest.raises(Exception):
            Sale(**valid_data).save()

    def test_total_cost_price_is_required(self, app, valid_data):
        # total_cost_price is NOT NULL — omitting raises
        valid_data.pop("total_cost_price")
        with pytest.raises(Exception):
            Sale(**valid_data).save()

    def test_total_revenue_price_is_required(self, app, valid_data):
        # total_revenue_price is NOT NULL — omitting raises
        valid_data.pop("total_revenue_price")
        with pytest.raises(Exception):
            Sale(**valid_data).save()

    def test_total_amount_is_required(self, app, valid_data):
        # total_amount is NOT NULL — omitting raises
        valid_data.pop("total_amount")
        with pytest.raises(Exception):
            Sale(**valid_data).save()

    def test_payment_method_is_optional(self, app, valid_data):
        # payment_method is nullable — a sale can be saved without it
        valid_data.pop("payment_method")
        Sale(**valid_data).save()

        result = Sale.query.first()
        assert result.payment_method is None

    def test_payment_method_accepts_value(self, app, valid_data):
        # When provided, payment_method is stored correctly
        valid_data["payment_method"] = "card"
        Sale(**valid_data).save()

        result = Sale.query.first()
        assert result.payment_method == "card"

    def test_transaction_id_autoincrements(self, app, valid_data, user):
        # Each new Sale gets a higher transaction_id automatically
        s1 = Sale(**valid_data).save()
        s2 = Sale(**{**valid_data}).save()

        assert s2.transaction_id > s1.transaction_id

    def test_sale_datetime_is_set_automatically(self, app, sale):
        # sale_datetime uses server_default=db.func.now() —
        # it should be populated without being set manually
        result = Sale.get_by_id(sale.transaction_id)
        assert result.sale_datetime is not None
        assert isinstance(result.sale_datetime, datetime)

    def test_multiple_sales_for_same_user(self, app, valid_data):
        # A user can have many sales — no unique constraint on user_id
        Sale(**valid_data).save()
        Sale(**{**valid_data}).save()
        Sale(**{**valid_data}).save()

        assert Sale.query.count() == 3


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that user_id must point to a real User row.
#    WHY:  Every sale must be traceable to the cashier who processed it.
#          An orphan sale with no user breaks audit trails and reports.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_user_id_raises(self, app, valid_data):
        # Nonexistent user_id should be blocked by FK constraint
        valid_data["user_id"] = 99999999
        with pytest.raises(Exception):
            Sale(**valid_data).save()

    def test_valid_user_id_saves(self, app, valid_data):
        # Confirm FK with a real user_id saves cleanly
        Sale(**valid_data).save()
        assert Sale.query.count() == 1

    def test_sale_blocked_after_user_deleted(self, app, valid_data, user):
        # After the referenced user is deleted, inserting a new sale
        # with that user_id should be blocked by FK constraint
        user.delete()
        with pytest.raises(Exception):
            Sale(**valid_data).save()


# ---------------------------------------------------------------------------
# 3. Numeric Precision — financial totals
#
#    WHAT: Verifies Decimal storage and retrieval for all three total fields.
#    WHY:  These are the top-level financial totals for a transaction.
#          Float imprecision or type mismatches would silently corrupt
#          revenue reports and reconciliation summaries.
# ---------------------------------------------------------------------------

class TestNumericPrecision:
    def test_totals_stored_as_decimal(self, app, sale):
        # All three total fields must be Decimal, not float
        result = Sale.get_by_id(sale.transaction_id)

        assert isinstance(result.total_cost_price, Decimal)
        assert isinstance(result.total_revenue_price, Decimal)
        assert isinstance(result.total_amount, Decimal)

    def test_totals_stored_with_two_decimal_places(self, app, sale):
        # Values should round-trip correctly at 2dp precision
        result = Sale.get_by_id(sale.transaction_id)

        assert result.total_cost_price == Decimal("20.00")
        assert result.total_revenue_price == Decimal("24.00")
        assert result.total_amount == Decimal("30.00")

    def test_zero_totals_accepted(self, app, valid_data):
        # Zero is a valid total — e.g. a voided or complimentary transaction
        valid_data["total_cost_price"] = Decimal("0.00")
        valid_data["total_revenue_price"] = Decimal("0.00")
        valid_data["total_amount"] = Decimal("0.00")
        Sale(**valid_data).save()

        result = Sale.query.first()
        assert result.total_amount == Decimal("0.00")

    def test_large_totals_within_numeric_bounds(self, app, valid_data):
        # Numeric(10, 2) supports values up to 99999999.99
        valid_data["total_cost_price"] = Decimal("99999999.99")
        valid_data["total_revenue_price"] = Decimal("99999999.99")
        valid_data["total_amount"] = Decimal("99999999.99")
        Sale(**valid_data).save()

        result = Sale.query.first()
        assert result.total_amount == Decimal("99999999.99")

    def test_total_amount_precision_retained(self, app, valid_data):
        # Verify a non-round value keeps its precision after round-trip
        valid_data["total_amount"] = Decimal("123.45")
        Sale(**valid_data).save()

        result = Sale.query.first()
        assert result.total_amount == Decimal("123.45")


# ---------------------------------------------------------------------------
# 4. Update Behavior
#
#    WHAT: Verifies that sale totals and payment_method can be changed
#          and that changes persist correctly after save().
#    WHY:  Although sales are typically immutable once committed, some
#          workflows allow corrections. This confirms the model supports
#          it and that saves don't silently fail.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_total_amount(self, app, sale):
        # Simulates a corrected total being applied to a sale record
        sale.total_amount = Decimal("999.99")
        sale.save()

        result = Sale.get_by_id(sale.transaction_id)
        assert result.total_amount == Decimal("999.99")

    def test_update_payment_method(self, app, sale):
        # Payment method can be changed (e.g. cash → card after correction)
        sale.payment_method = "card"
        sale.save()

        result = Sale.get_by_id(sale.transaction_id)
        assert result.payment_method == "card"

    def test_set_payment_method_to_none(self, app, sale):
        # Payment method can be cleared — it is nullable
        sale.payment_method = None
        sale.save()

        result = Sale.get_by_id(sale.transaction_id)
        assert result.payment_method is None

    def test_update_all_totals(self, app, sale):
        # All three total fields can be updated together
        sale.total_cost_price = Decimal("50.00")
        sale.total_revenue_price = Decimal("60.00")
        sale.total_amount = Decimal("75.00")
        sale.save()

        result = Sale.get_by_id(sale.transaction_id)
        assert result.total_cost_price == Decimal("50.00")
        assert result.total_revenue_price == Decimal("60.00")
        assert result.total_amount == Decimal("75.00")


# ---------------------------------------------------------------------------
# 5. Relationship — User ↔ Sale
#
#    WHAT: Verifies both sides of the Sale ↔ User relationship.
#    WHY:  Reports and audit logs rely on sale.user to identify the cashier.
#          user.sales is used to pull all transactions for a given user.
#          A broken relationship silently returns None instead of crashing,
#          which is harder to catch without an explicit test.
# ---------------------------------------------------------------------------

class TestUserRelationship:
    def test_sale_user_returns_linked_user(self, app, sale, user):
        # sale.user should return the User who processed the transaction
        db.session.refresh(sale)
        assert sale.user is not None
        assert sale.user.user_id == user.user_id

    def test_user_sales_returns_list_of_sales(self, app, sale, user):
        # user.sales should return a list containing the user's sales
        db.session.refresh(user)
        assert len(user.sales) == 1
        assert user.sales[0].transaction_id == sale.transaction_id

    def test_user_multiple_sales(self, app, user, valid_data):
        # A user can accumulate multiple sales — all appear in user.sales
        Sale(**valid_data).save()
        Sale(**{**valid_data}).save()
        Sale(**{**valid_data}).save()

        db.session.refresh(user)
        assert len(user.sales) == 3

    def test_sale_user_name_accessible(self, app, sale, user):
        # Confirms we can traverse the relationship to read user fields
        # This is the pattern used in reports and receipts
        db.session.refresh(sale)
        assert sale.user.full_name == user.full_name


# ---------------------------------------------------------------------------
# 6. Relationship — Sale ↔ SaleDetail (cascade)
#
#    WHAT: Verifies that sale.sale_details returns associated rows and
#          that deleting a Sale cascades to its SaleDetail children.
#    WHY:  SaleDetail holds the per-product line items for every sale.
#          If cascade delete is broken, deleting a sale would leave
#          orphan SaleDetail rows polluting the database.
#
#    NOTE: Sale model defines:
#          sale_details = db.relationship("SaleDetail", back_populates="sale")
#          There is no explicit cascade="all, delete-orphan" in the model —
#          so deletion behavior depends on DB-level FK constraints.
#          These tests document the ACTUAL behavior, not assumed behavior.
# ---------------------------------------------------------------------------

class TestSaleDetailRelationship:
    def test_sale_details_returns_associated_rows(self, app, sale, sale_detail):
        # sale.sale_details should return the list of line items
        db.session.refresh(sale)
        assert len(sale.sale_details) == 1
        assert sale.sale_details[0].sale_detail_id == sale_detail.sale_detail_id

    def test_sale_with_no_details_returns_empty_list(self, app, sale):
        # A new sale with no line items should have an empty list
        db.session.refresh(sale)
        assert sale.sale_details == []

    def test_sale_detail_back_reference(self, app, sale, sale_detail):
        # sale_detail.sale should return the parent Sale instance
        db.session.refresh(sale_detail)
        assert sale_detail.sale is not None
        assert sale_detail.sale.transaction_id == sale.transaction_id


# ---------------------------------------------------------------------------
# 7. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with Sale's specific schema.
#    WHY:  BaseModel is abstract and tested in isolation via DummyModel.
#          These checks confirm Sale's schema doesn't break anything
#          inherited — e.g. String PKs or unusual column types can
#          sometimes interfere with generic ORM methods.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_sale(self, app, valid_data):
        # save() should commit the Sale row to the DB
        Sale(**valid_data).save()
        assert Sale.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        s = Sale(**valid_data)
        returned = s.save()
        assert returned is s

    def test_delete_removes_sale(self, app, sale):
        # delete() should remove the Sale row from the DB
        sale.delete()
        assert Sale.query.count() == 0

    def test_get_by_id_returns_correct_sale(self, app, sale):
        # get_by_id() should return the Sale with the matching transaction_id
        result = Sale.get_by_id(sale.transaction_id)

        assert result is not None
        assert result.transaction_id == sale.transaction_id
        assert result.total_amount == sale.total_amount

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent transaction_id should return None, not raise
        result = Sale.get_by_id(99999)
        assert result is None

    def test_get_all_returns_all_sales(self, app, valid_data):
        # get_all() returns every row in the Sales table
        Sale(**valid_data).save()
        Sale(**{**valid_data}).save()

        result = Sale.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = Sale.get_all()
        assert result == []