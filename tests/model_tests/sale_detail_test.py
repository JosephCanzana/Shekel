"""
tests/sale_detail_test.py

Pytest suite for SaleDetail model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - product_id is nullable (sale detail can exist without a product reference)
   - sale_detail_id autoincrements
   - Multiple SaleDetail rows allowed per Sale (line items)

2. Foreign Key Constraints
   - transaction_id must reference an existing Sale row
   - product_id must reference an existing Product row when provided
   - ondelete=RESTRICT on product_id — deleting a Product with SaleDetails
     is blocked

3. Numeric Precision — financial fields
   - All 6 price/subtotal fields stored as Decimal
   - Correct 2dp precision confirmed
   - Zero and large values accepted

4. ondelete=RESTRICT on product_id
   - Deleting a Product that has SaleDetail rows is blocked
   - SaleDetail rows survive a failed product delete (rollback works)
   - product_id can be NULL — allows product deletion after nulling the FK

5. Relationship — Sale ↔ SaleDetail
   - sale_detail.sale returns the linked Sale instance
   - sale.sale_details returns list of all line items for the sale

6. Relationship — Product ↔ SaleDetail
   - sale_detail.product returns the linked Product instance
   - passive_deletes=True — SQLAlchemy defers to DB-level FK behavior

7. Update Behavior
   - Quantity and price fields can be updated and persisted

8. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with SaleDetail's specific schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from decimal import Decimal
from app.extensions import db
from app.models.sale_detail import SaleDetail
from app.models.sale import Sale
from app.models.product import Product


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(sale, product):
    """
    Returns a dict of all valid fields for a SaleDetail.
    product_id is included but nullable — tested both ways below.
    """
    return dict(
        transaction_id=sale.transaction_id,
        product_id=product.product_id,
        quantity=2,
        cost_price_at_sale=Decimal("10.00"),
        revenue_price_at_sale=Decimal("12.00"),
        price_at_sale=Decimal("15.00"),
        subtotal_unit=Decimal("20.00"),
        subtotal_revenue=Decimal("24.00"),
        subtotal_amount=Decimal("30.00"),
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies nullable=False columns are enforced by the DB and that
#          the nullable column (product_id) accepts None cleanly.
#    WHY:  SaleDetail rows are the financial line items of every transaction.
#          A missing quantity or subtotal would corrupt per-transaction
#          revenue breakdowns and make receipts inaccurate.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_sale_detail_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should commit cleanly
        SaleDetail(**valid_data).save()
        assert SaleDetail.query.count() == 1

    def test_transaction_id_is_required(self, app, valid_data):
        # transaction_id is FK and NOT NULL — every detail must belong to a sale
        valid_data.pop("transaction_id")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_quantity_is_required(self, app, valid_data):
        # quantity is NOT NULL — a line item with no quantity is meaningless
        valid_data.pop("quantity")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_cost_price_at_sale_is_required(self, app, valid_data):
        # cost_price_at_sale is NOT NULL — omitting raises
        valid_data.pop("cost_price_at_sale")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_revenue_price_at_sale_is_required(self, app, valid_data):
        # revenue_price_at_sale is NOT NULL — omitting raises
        valid_data.pop("revenue_price_at_sale")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_price_at_sale_is_required(self, app, valid_data):
        # price_at_sale is NOT NULL — omitting raises
        valid_data.pop("price_at_sale")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_subtotal_unit_is_required(self, app, valid_data):
        # subtotal_unit is NOT NULL — omitting raises
        valid_data.pop("subtotal_unit")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_subtotal_revenue_is_required(self, app, valid_data):
        # subtotal_revenue is NOT NULL — omitting raises
        valid_data.pop("subtotal_revenue")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_subtotal_amount_is_required(self, app, valid_data):
        # subtotal_amount is NOT NULL — omitting raises
        valid_data.pop("subtotal_amount")
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_product_id_is_optional(self, app, valid_data):
        # product_id is nullable — a line item can exist without a product ref
        # This allows historical sale records to survive product deletion
        valid_data.pop("product_id")
        SaleDetail(**valid_data).save()

        result = SaleDetail.query.first()
        assert result.product_id is None

    def test_product_id_can_be_explicitly_null(self, app, valid_data):
        # Explicitly setting product_id=None should also be accepted
        valid_data["product_id"] = None
        SaleDetail(**valid_data).save()

        result = SaleDetail.query.first()
        assert result.product_id is None

    def test_sale_detail_id_autoincrements(self, app, valid_data):
        # Each new SaleDetail gets a higher sale_detail_id automatically
        sd1 = SaleDetail(**valid_data).save()
        sd2 = SaleDetail(**{**valid_data}).save()

        assert sd2.sale_detail_id > sd1.sale_detail_id

    def test_multiple_details_allowed_per_sale(self, app, valid_data):
        # A sale can have multiple line items — no unique constraint on
        # transaction_id in SaleDetail (one sale, many products)
        SaleDetail(**valid_data).save()
        SaleDetail(**{**valid_data}).save()
        SaleDetail(**{**valid_data}).save()

        assert SaleDetail.query.count() == 3

    def test_quantity_stored_as_integer(self, app, valid_data):
        # quantity is db.Integer — should be stored and returned as int
        SaleDetail(**valid_data).save()

        result = SaleDetail.query.first()
        assert isinstance(result.quantity, int)
        assert result.quantity == 2


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that transaction_id must reference a real Sale row
#          and product_id must reference a real Product row when provided.
#    WHY:  SaleDetail rows orphaned from their parent Sale would corrupt
#          transaction totals and make receipts irretrievable. An invalid
#          product_id would break product history lookups.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_transaction_id_raises(self, app, valid_data):
        # Nonexistent transaction_id should be blocked by FK constraint
        valid_data["transaction_id"] = 99999
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_invalid_product_id_raises(self, app, valid_data):
        # Nonexistent product_id should be blocked by FK constraint
        valid_data["product_id"] = "NONEXISTENT-SKU"
        with pytest.raises(Exception):
            SaleDetail(**valid_data).save()

    def test_valid_fks_save_successfully(self, app, valid_data):
        # Confirm both valid FKs result in a clean save
        SaleDetail(**valid_data).save()
        assert SaleDetail.query.count() == 1

    def test_null_product_id_bypasses_fk_check(self, app, valid_data):
        # NULL product_id is allowed and bypasses the FK constraint —
        # this is intentional to preserve sale history after product deletion
        valid_data["product_id"] = None
        SaleDetail(**valid_data).save()
        assert SaleDetail.query.count() == 1


# ---------------------------------------------------------------------------
# 3. Numeric Precision — financial fields
#
#    WHAT: Verifies Decimal storage and retrieval for all 6 price fields.
#    WHY:  SaleDetail holds the snapshot prices at the time of sale —
#          unit cost, revenue price, and customer price. Float imprecision
#          would silently corrupt per-item profit margin calculations and
#          end-of-day revenue reports. These values must never drift.
# ---------------------------------------------------------------------------

class TestNumericPrecision:
    def test_all_price_fields_stored_as_decimal(self, app, sale_detail):
        # All 6 price/subtotal fields must be Decimal, not float
        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)

        assert isinstance(result.cost_price_at_sale, Decimal)
        assert isinstance(result.revenue_price_at_sale, Decimal)
        assert isinstance(result.price_at_sale, Decimal)
        assert isinstance(result.subtotal_unit, Decimal)
        assert isinstance(result.subtotal_revenue, Decimal)
        assert isinstance(result.subtotal_amount, Decimal)

    def test_prices_stored_with_two_decimal_places(self, app, sale_detail):
        # Values should round-trip correctly at 2dp precision
        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)

        assert result.cost_price_at_sale == Decimal("10.00")
        assert result.revenue_price_at_sale == Decimal("12.00")
        assert result.price_at_sale == Decimal("15.00")
        assert result.subtotal_unit == Decimal("20.00")
        assert result.subtotal_revenue == Decimal("24.00")
        assert result.subtotal_amount == Decimal("30.00")

    def test_zero_prices_accepted(self, app, valid_data):
        # Zero is a valid price — e.g. a complimentary item
        for field in ["cost_price_at_sale", "revenue_price_at_sale",
                      "price_at_sale", "subtotal_unit",
                      "subtotal_revenue", "subtotal_amount"]:
            valid_data[field] = Decimal("0.00")

        SaleDetail(**valid_data).save()

        result = SaleDetail.query.first()
        assert result.subtotal_amount == Decimal("0.00")

    def test_large_prices_within_numeric_bounds(self, app, valid_data):
        # Numeric(10, 2) supports values up to 99999999.99
        for field in ["cost_price_at_sale", "revenue_price_at_sale",
                      "price_at_sale", "subtotal_unit",
                      "subtotal_revenue", "subtotal_amount"]:
            valid_data[field] = Decimal("99999999.99")

        SaleDetail(**valid_data).save()

        result = SaleDetail.query.first()
        assert result.subtotal_amount == Decimal("99999999.99")

    def test_non_round_price_retains_precision(self, app, valid_data):
        # Non-round values survive the DB round-trip without drift
        valid_data["subtotal_amount"] = Decimal("123.45")
        SaleDetail(**valid_data).save()

        result = SaleDetail.query.first()
        assert result.subtotal_amount == Decimal("123.45")


# ---------------------------------------------------------------------------
# 4. ondelete=RESTRICT on product_id
#
#    WHAT: Verifies that deleting a Product with associated SaleDetail rows
#          is blocked by the DB, and that SaleDetails survive the rollback.
#    WHY:  Sales are historical records — they must not be silently broken
#          when a product is archived or deleted. RESTRICT forces the
#          developer to explicitly null out product_id on historical records
#          before allowing the product to be deleted, preserving audit integrity.
#
#    NOTE: passive_deletes=True on the relationship means SQLAlchemy does NOT
#          load or manage the children during a delete — it defers entirely to
#          the DB-level FK constraint (RESTRICT). This is why we test at the
#          DB level here rather than through the ORM relationship.
# ---------------------------------------------------------------------------

class TestOnDeleteRestrict:
    def test_deleting_product_with_sale_details_raises(self, app, sale_detail, product):
        # A Product referenced by SaleDetail rows cannot be deleted —
        # the DB blocks it with ondelete=RESTRICT
        with pytest.raises(Exception):
            db.session.delete(product)
            db.session.commit()

    def test_sale_detail_survives_failed_product_delete(self, app, sale_detail, product):
        # After a failed product delete, the SaleDetail row must still exist —
        # the transaction was rolled back cleanly
        try:
            db.session.delete(product)
            db.session.commit()
        except Exception:
            db.session.rollback()

        assert SaleDetail.query.count() == 1

    def test_product_can_be_deleted_after_nulling_product_id(self, app, sale_detail, product):
        # The correct workflow: null out product_id on historical records
        # first, then the product can be deleted freely
        sale_detail.product_id = None
        sale_detail.save()

        # Now the product has no RESTRICT references — deletion succeeds
        product.delete()

        assert Product.query.count() == 0
        assert SaleDetail.query.count() == 1  # sale detail still exists


# ---------------------------------------------------------------------------
# 5. Relationship — Sale ↔ SaleDetail
#
#    WHAT: Verifies both sides of the SaleDetail ↔ Sale relationship.
#    WHY:  sale_detail.sale is used to look up the parent transaction when
#          rendering receipts or reversing a sale. sale.sale_details is used
#          to enumerate line items for a transaction. A broken relationship
#          silently returns None instead of crashing — hard to catch
#          without explicit tests.
# ---------------------------------------------------------------------------

class TestSaleRelationship:
    def test_sale_detail_sale_returns_linked_sale(self, app, sale_detail, sale):
        # sale_detail.sale should return the parent Sale instance
        db.session.refresh(sale_detail)
        assert sale_detail.sale is not None
        assert sale_detail.sale.transaction_id == sale.transaction_id

    def test_sale_sale_details_returns_list(self, app, sale_detail, sale):
        # sale.sale_details should return a list containing the line item
        db.session.refresh(sale)
        assert len(sale.sale_details) == 1
        assert sale.sale_details[0].sale_detail_id == sale_detail.sale_detail_id

    def test_sale_multiple_details(self, app, sale, valid_data):
        # A sale with multiple line items returns all of them
        SaleDetail(**valid_data).save()
        SaleDetail(**{**valid_data}).save()
        SaleDetail(**{**valid_data}).save()

        db.session.refresh(sale)
        assert len(sale.sale_details) == 3

    def test_sale_with_no_details_returns_empty_list(self, app, sale):
        # A sale with no line items should have an empty list
        db.session.refresh(sale)
        assert sale.sale_details == []

    def test_sale_total_accessible_via_back_reference(self, app, sale_detail, sale):
        # Confirms traversal through the relationship to read sale fields
        # This is the pattern used in receipt and report routes
        db.session.refresh(sale_detail)
        assert sale_detail.sale.total_amount == sale.total_amount


# ---------------------------------------------------------------------------
# 6. Relationship — Product ↔ SaleDetail
#
#    WHAT: Verifies both sides of the SaleDetail ↔ Product relationship.
#    WHY:  sale_detail.product is used to display product names on receipts.
#          product.sale_details is used to pull sales history for a product.
#          passive_deletes=True means SQLAlchemy won't auto-load children
#          on product delete — the DB handles it via RESTRICT.
# ---------------------------------------------------------------------------

class TestProductRelationship:
    def test_sale_detail_product_returns_linked_product(self, app, sale_detail, product):
        # sale_detail.product should return the Product that was sold
        db.session.refresh(sale_detail)
        assert sale_detail.product is not None
        assert sale_detail.product.product_id == product.product_id

    def test_product_sale_details_returns_list(self, app, sale_detail, product):
        # product.sale_details should return a list containing the line item
        db.session.refresh(product)
        assert len(product.sale_details) == 1
        assert product.sale_details[0].sale_detail_id == sale_detail.sale_detail_id

    def test_sale_detail_product_name_accessible(self, app, sale_detail, product):
        # Confirms traversal to read product fields — used in receipts
        db.session.refresh(sale_detail)
        assert sale_detail.product.product_name == product.product_name

    def test_null_product_id_returns_none_for_product(self, app, valid_data):
        # When product_id is NULL, sale_detail.product should return None
        valid_data["product_id"] = None
        sd = SaleDetail(**valid_data).save()

        db.session.refresh(sd)
        assert sd.product is None


# ---------------------------------------------------------------------------
# 7. Update Behavior
#
#    WHAT: Verifies that quantity and price fields can be corrected after
#          the fact and that changes persist correctly.
#    WHY:  Cashier corrections or post-processing adjustments may require
#          updating individual line items. Confirms the model supports it
#          without silent failures.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_quantity(self, app, sale_detail):
        # Simulates a quantity correction on a line item
        sale_detail.quantity = 10
        sale_detail.save()

        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)
        assert result.quantity == 10

    def test_update_subtotal_amount(self, app, sale_detail):
        # Subtotal can be corrected after a price adjustment
        sale_detail.subtotal_amount = Decimal("150.00")
        sale_detail.save()

        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)
        assert result.subtotal_amount == Decimal("150.00")

    def test_update_price_at_sale(self, app, sale_detail):
        # price_at_sale snapshot can be corrected
        sale_detail.price_at_sale = Decimal("99.99")
        sale_detail.save()

        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)
        assert result.price_at_sale == Decimal("99.99")

    def test_null_product_id_after_save(self, app, sale_detail):
        # product_id can be set to None on an existing record —
        # the correct workflow before deleting a product
        sale_detail.product_id = None
        sale_detail.save()

        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)
        assert result.product_id is None


# ---------------------------------------------------------------------------
# 8. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with SaleDetail's specific schema.
#    WHY:  BaseModel is abstract and tested in isolation via DummyModel.
#          These checks confirm that SaleDetail's nullable FK and Numeric
#          columns don't break anything inherited from BaseModel.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_sale_detail(self, app, valid_data):
        # save() should commit the SaleDetail row to the DB
        SaleDetail(**valid_data).save()
        assert SaleDetail.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        sd = SaleDetail(**valid_data)
        returned = sd.save()
        assert returned is sd

    def test_delete_removes_sale_detail(self, app, sale_detail):
        # delete() should remove the SaleDetail row from the DB
        sale_detail.delete()
        assert SaleDetail.query.count() == 0

    def test_delete_does_not_remove_sale(self, app, sale_detail, sale):
        # Deleting a SaleDetail should NOT affect the parent Sale
        sale_detail.delete()
        assert Sale.query.count() == 1

    def test_delete_does_not_remove_product(self, app, sale_detail, product):
        # Deleting a SaleDetail should NOT cascade to the Product
        sale_detail.delete()
        assert Product.query.count() == 1

    def test_get_by_id_returns_correct_record(self, app, sale_detail):
        # get_by_id() should return the SaleDetail with the matching PK
        result = SaleDetail.get_by_id(sale_detail.sale_detail_id)

        assert result is not None
        assert result.sale_detail_id == sale_detail.sale_detail_id
        assert result.transaction_id == sale_detail.transaction_id

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent sale_detail_id should return None, not raise
        result = SaleDetail.get_by_id(99999)
        assert result is None

    def test_get_all_returns_all_sale_details(self, app, valid_data):
        # get_all() returns every row in the Sales_Details table
        SaleDetail(**valid_data).save()
        SaleDetail(**{**valid_data}).save()

        result = SaleDetail.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = SaleDetail.get_all()
        assert result == []