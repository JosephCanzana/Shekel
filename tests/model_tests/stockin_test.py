"""
tests/stock_in_test.py

Pytest suite for StockIn model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - notes is nullable — optional field for remarks
   - stockin_datetime auto-populated via server_default
   - stockin_id autoincrements
   - Multiple stock-in records allowed per product and per user

2. Foreign Key Constraints
   - product_id must reference an existing Product row
   - user_id must reference an existing User row
   - Both invalid FKs are blocked independently

3. Update Behavior
   - quantity_received and notes can be updated and persisted
   - notes can be set to None (cleared) after being set

4. Relationship — Product ↔ StockIn
   - stock_in.product returns the linked Product instance
   - product.stock_ins returns a list of all stock-in records for the product

5. Relationship — User ↔ StockIn
   - stock_in.user returns the linked User instance
   - user.stock_ins returns a list of all stock-in records by the user

6. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with StockIn's specific schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from datetime import datetime
from app.extensions import db
from app.models.stock_in import StockIn
from app.models.product import Product
from app.models.user import User


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(product, user):
    """
    Returns a dict of all valid fields for a StockIn record.
    notes is included but optional — tested both ways below.
    """
    return dict(
        product_id=product.product_id,
        user_id=user.user_id,
        quantity_received=50,
        notes="Initial stock delivery",
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are enforced by the DB
#          and that nullable columns (notes) accept None cleanly.
#    WHY:  StockIn records are the source of truth for inventory replenishment.
#          A missing quantity or broken FK would corrupt stock level history
#          and make it impossible to audit where inventory came from.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_stock_in_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should commit cleanly
        StockIn(**valid_data).save()
        assert StockIn.query.count() == 1

    def test_product_id_is_required(self, app, valid_data):
        # product_id is FK and NOT NULL — every stock-in must reference a product
        valid_data.pop("product_id")
        with pytest.raises(Exception):
            StockIn(**valid_data).save()

    def test_user_id_is_required(self, app, valid_data):
        # user_id is FK and NOT NULL — every stock-in must be traceable to a user
        valid_data.pop("user_id")
        with pytest.raises(Exception):
            StockIn(**valid_data).save()

    def test_quantity_received_is_required(self, app, valid_data):
        # quantity_received is NOT NULL — a stock-in with no quantity is meaningless
        valid_data.pop("quantity_received")
        with pytest.raises(Exception):
            StockIn(**valid_data).save()

    def test_notes_is_optional(self, app, valid_data):
        # notes is nullable — a stock-in can be saved without a remark
        valid_data.pop("notes")
        StockIn(**valid_data).save()

        result = StockIn.query.first()
        assert result.notes is None

    def test_notes_accepts_value(self, app, valid_data):
        # When provided, notes is stored and retrieved correctly
        valid_data["notes"] = "Restocked from supplier A"
        StockIn(**valid_data).save()

        result = StockIn.query.first()
        assert result.notes == "Restocked from supplier A"

    def test_notes_accepts_long_text(self, app, valid_data):
        # notes is db.Text — should accept long strings without truncation
        long_note = "Detail note. " * 100
        valid_data["notes"] = long_note
        StockIn(**valid_data).save()

        result = StockIn.query.first()
        assert result.notes == long_note

    def test_stockin_id_autoincrements(self, app, valid_data, second_product, user):
        # Each new StockIn gets a higher stockin_id automatically
        s1 = StockIn(**valid_data).save()
        s2 = StockIn(**{**valid_data,
                        "product_id": second_product.product_id}).save()

        assert s2.stockin_id > s1.stockin_id

    def test_stockin_datetime_is_set_automatically(self, app, stock_in):
        # stockin_datetime uses server_default=db.func.now() —
        # it should be populated without being set manually
        result = StockIn.get_by_id(stock_in.stockin_id)
        assert result.stockin_datetime is not None
        assert isinstance(result.stockin_datetime, datetime)

    def test_multiple_stock_ins_allowed_per_product(self, app, valid_data):
        # A product can receive multiple stock-in records over time
        # No unique constraint on product_id in StockIn
        StockIn(**valid_data).save()
        StockIn(**{**valid_data}).save()
        StockIn(**{**valid_data}).save()

        assert StockIn.query.count() == 3

    def test_multiple_stock_ins_allowed_per_user(self, app, valid_data, second_product):
        # A user can log multiple stock-ins for different products
        StockIn(**valid_data).save()
        StockIn(**{**valid_data,
                   "product_id": second_product.product_id}).save()

        assert StockIn.query.count() == 2

    def test_quantity_received_stores_integer(self, app, valid_data):
        # quantity_received is db.Integer — should be stored and returned as int
        StockIn(**valid_data).save()

        result = StockIn.query.first()
        assert isinstance(result.quantity_received, int)
        assert result.quantity_received == 50

    def test_large_quantity_is_accepted(self, app, valid_data):
        # Large batch deliveries should not overflow the Integer column
        valid_data["quantity_received"] = 1000000
        StockIn(**valid_data).save()

        result = StockIn.query.first()
        assert result.quantity_received == 1000000


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that product_id and user_id must reference real rows.
#    WHY:  StockIn has two FKs — both must be valid for the record to be
#          meaningful. An orphan stock-in with a nonexistent product would
#          break inventory history queries. One with a nonexistent user
#          would make the delivery untraceable.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_product_id_raises(self, app, valid_data):
        # Nonexistent product_id should be blocked by FK constraint
        valid_data["product_id"] = "NONEXISTENT-SKU"
        with pytest.raises(Exception):
            StockIn(**valid_data).save()

    def test_invalid_user_id_raises(self, app, valid_data):
        # Nonexistent user_id should be blocked by FK constraint
        valid_data["user_id"] = 99999999
        with pytest.raises(Exception):
            StockIn(**valid_data).save()

    def test_valid_fks_save_successfully(self, app, valid_data):
        # Confirm both valid FKs together result in a clean save
        StockIn(**valid_data).save()
        assert StockIn.query.count() == 1

    def test_stock_in_blocked_after_user_deleted(self, app, valid_data, user):
        # After the referenced user is deleted, a new stock-in with
        # that user_id should be blocked by FK constraint
        user.delete()
        with pytest.raises(Exception):
            StockIn(**valid_data).save()

    def test_stock_in_blocked_after_product_deleted(self, app, valid_data, product):
        # After the referenced product is deleted, a new stock-in with
        # that product_id should be blocked by FK constraint
        product.delete()
        with pytest.raises(Exception):
            StockIn(**valid_data).save()


# ---------------------------------------------------------------------------
# 3. Update Behavior
#
#    WHAT: Verifies that quantity_received and notes can be corrected
#          and that changes persist correctly after save().
#    WHY:  Data entry corrections do happen — a wrong quantity or
#          a missing note may need to be updated after the fact.
#          Confirms the model supports it without silent failures.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_quantity_received(self, app, stock_in):
        # Simulates a quantity correction after a data entry mistake
        stock_in.quantity_received = 200
        stock_in.save()

        result = StockIn.get_by_id(stock_in.stockin_id)
        assert result.quantity_received == 200

    def test_update_notes(self, app, stock_in):
        # Notes can be updated to add more detail after the fact
        stock_in.notes = "Updated: verified by warehouse manager"
        stock_in.save()

        result = StockIn.get_by_id(stock_in.stockin_id)
        assert result.notes == "Updated: verified by warehouse manager"

    def test_clear_notes_to_none(self, app, stock_in):
        # Notes can be cleared back to None — it is nullable
        stock_in.notes = None
        stock_in.save()

        result = StockIn.get_by_id(stock_in.stockin_id)
        assert result.notes is None

    def test_update_quantity_to_one(self, app, stock_in):
        # Minimum meaningful quantity is 1 — should be accepted
        stock_in.quantity_received = 1
        stock_in.save()

        result = StockIn.get_by_id(stock_in.stockin_id)
        assert result.quantity_received == 1


# ---------------------------------------------------------------------------
# 4. Relationship — Product ↔ StockIn
#
#    WHAT: Verifies both sides of the StockIn ↔ Product relationship.
#    WHY:  stock_in.product is used in stocking routes and reports to
#          display what product was received. product.stock_ins gives
#          the full delivery history for a product — used in inventory
#          audit views. A broken relationship returns None silently,
#          causing routes to crash or display blank product names.
# ---------------------------------------------------------------------------

class TestProductRelationship:
    def test_stock_in_product_returns_linked_product(self, app, stock_in, product):
        # stock_in.product should return the Product that was received
        db.session.refresh(stock_in)
        assert stock_in.product is not None
        assert stock_in.product.product_id == product.product_id

    def test_product_stock_ins_returns_list(self, app, stock_in, product):
        # product.stock_ins should return a list containing the stock-in
        db.session.refresh(product)
        assert len(product.stock_ins) == 1
        assert product.stock_ins[0].stockin_id == stock_in.stockin_id

    def test_product_multiple_stock_ins(self, app, product, user, valid_data):
        # A product can have multiple delivery records over time
        StockIn(**valid_data).save()
        StockIn(**{**valid_data}).save()

        db.session.refresh(product)
        assert len(product.stock_ins) == 2

    def test_stock_in_product_name_accessible(self, app, stock_in, product):
        # Confirms traversal through the relationship to read product fields
        # This is the pattern used in stocking dashboard routes
        db.session.refresh(stock_in)
        assert stock_in.product.product_name == product.product_name

    def test_product_with_no_stock_ins_returns_empty_list(self, app, product):
        # A product with no delivery history should return an empty list
        db.session.refresh(product)
        assert product.stock_ins == []


# ---------------------------------------------------------------------------
# 5. Relationship — User ↔ StockIn
#
#    WHAT: Verifies both sides of the StockIn ↔ User relationship.
#    WHY:  stock_in.user is used to identify who received the delivery —
#          critical for accountability in stocking workflows. user.stock_ins
#          is used in staff activity reports. A broken relationship silently
#          returns None instead of crashing, which is hard to catch without
#          explicit tests.
# ---------------------------------------------------------------------------

class TestUserRelationship:
    def test_stock_in_user_returns_linked_user(self, app, stock_in, user):
        # stock_in.user should return the User who logged the delivery
        db.session.refresh(stock_in)
        assert stock_in.user is not None
        assert stock_in.user.user_id == user.user_id

    def test_user_stock_ins_returns_list(self, app, stock_in, user):
        # user.stock_ins should return a list of all deliveries logged by the user
        db.session.refresh(user)
        assert len(user.stock_ins) == 1
        assert user.stock_ins[0].stockin_id == stock_in.stockin_id

    def test_user_multiple_stock_ins(self, app, user, valid_data, second_product):
        # A user can log multiple deliveries across different products
        StockIn(**valid_data).save()
        StockIn(**{**valid_data,
                   "product_id": second_product.product_id}).save()

        db.session.refresh(user)
        assert len(user.stock_ins) == 2

    def test_stock_in_user_full_name_accessible(self, app, stock_in, user):
        # Confirms traversal through the relationship to read user fields
        # This is the pattern used in stocking history routes
        db.session.refresh(stock_in)
        assert stock_in.user.full_name == user.full_name

    def test_user_with_no_stock_ins_returns_empty_list(self, app, user):
        # A user who has not logged any deliveries returns an empty list
        db.session.refresh(user)
        assert user.stock_ins == []


# ---------------------------------------------------------------------------
# 6. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with StockIn's specific schema.
#    WHY:  BaseModel is abstract and tested in isolation via DummyModel.
#          These checks confirm StockIn's dual-FK schema and server_default
#          datetime don't break anything inherited from BaseModel.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_stock_in(self, app, valid_data):
        # save() should commit the StockIn row to the DB
        StockIn(**valid_data).save()
        assert StockIn.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        s = StockIn(**valid_data)
        returned = s.save()
        assert returned is s

    def test_delete_removes_stock_in(self, app, stock_in):
        # delete() should remove the StockIn row from the DB
        stock_in.delete()
        assert StockIn.query.count() == 0

    def test_delete_does_not_remove_product(self, app, stock_in, product):
        # Deleting a StockIn should NOT cascade to the referenced Product
        stock_in.delete()
        assert Product.query.count() == 1

    def test_delete_does_not_remove_user(self, app, stock_in, user):
        # Deleting a StockIn should NOT cascade to the referenced User
        stock_in.delete()
        assert User.query.count() == 1

    def test_get_by_id_returns_correct_record(self, app, stock_in):
        # get_by_id() should return the StockIn with the matching PK
        result = StockIn.get_by_id(stock_in.stockin_id)

        assert result is not None
        assert result.stockin_id == stock_in.stockin_id
        assert result.product_id == stock_in.product_id
        assert result.user_id == stock_in.user_id

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent stockin_id should return None, not raise
        result = StockIn.get_by_id(99999)
        assert result is None

    def test_get_all_returns_all_stock_ins(self, app, valid_data, second_product):
        # get_all() returns every row in the Stock_In table
        StockIn(**valid_data).save()
        StockIn(**{**valid_data,
                   "product_id": second_product.product_id}).save()

        result = StockIn.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = StockIn.get_all()
        assert result == []