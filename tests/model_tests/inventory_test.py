"""
tests/inventory_test.py

Pytest suite for Inventory model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - product_id unique constraint (one inventory row per product)
   - Default values for quantity_available and quantity_defective
   - last_updated is required (no server_default — must be set manually)

2. Foreign Key Constraints
   - product_id must reference an existing Product row
   - Invalid product_id is blocked

3. Unique Constraint on product_id
   - One product can only have one Inventory row

4. Default Values
   - quantity_available defaults to 0
   - quantity_defective defaults to 0

5. Update Behavior
   - quantity_available, quantity_defective, last_updated can be updated
   - Updates persist correctly after save()

6. Relationship — Product ↔ Inventory
   - product.inventory returns the linked Inventory (uselist=False)
   - inventory.product returns the linked Product

7. Cascade / Delete Behavior
   - Deleting an Inventory row does NOT delete the Product
   - Product can be deleted if Inventory is deleted first

8. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with Inventory's specific schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models.inventory import Inventory
from app.models.product import Product


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(product):
    """
    Returns a dict of all valid fields for an Inventory row.
    Depends on the shared `product` fixture from conftest.py.
    """
    return dict(
        product_id=product.product_id,
        quantity_available=100,
        quantity_defective=5,
        last_updated=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are actually enforced by
#          the DB — not just declared in the model.
#    WHY:  If a column constraint is accidentally removed during a schema
#          change, these tests will immediately catch it.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_inventory_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should save cleanly
        Inventory(**valid_data).save()
        assert Inventory.query.count() == 1

    def test_product_id_is_required(self, app, valid_data):
        # product_id is the FK and NOT NULL — cannot be omitted
        valid_data.pop("product_id")
        with pytest.raises(Exception):
            Inventory(**valid_data).save()

    def test_last_updated_is_required(self, app, valid_data):
        # last_updated has no server_default — it must be set explicitly
        # unlike defect_datetime or sale_datetime which use server_default
        valid_data.pop("last_updated")
        with pytest.raises(Exception):
            Inventory(**valid_data).save()

    def test_quantity_available_defaults_to_zero(self, app, product):
        # quantity_available has default=0 — omitting it should succeed
        # and the DB should store 0, not NULL
        inv = Inventory(
            product_id=product.product_id,
            last_updated=datetime.utcnow(),
        )
        inv.save()

        result = Inventory.get_by_id(inv.inventory_id)
        assert result.quantity_available == 0

    def test_quantity_defective_defaults_to_zero(self, app, product):
        # quantity_defective has default=0 — same as above
        inv = Inventory(
            product_id=product.product_id,
            last_updated=datetime.utcnow(),
        )
        inv.save()

        result = Inventory.get_by_id(inv.inventory_id)
        assert result.quantity_defective == 0

    def test_inventory_id_autoincrements(self, app, product, second_product):
        # inventory_id is autoincrement — each new row gets a higher ID
        inv1 = Inventory(product_id=product.product_id,
                         last_updated=datetime.utcnow()).save()
        inv2 = Inventory(product_id=second_product.product_id,
                         last_updated=datetime.utcnow()).save()

        assert inv2.inventory_id > inv1.inventory_id

    def test_last_updated_stores_datetime(self, app, valid_data):
        # last_updated should be stored and retrieved as a datetime object
        now = datetime.utcnow()
        valid_data["last_updated"] = now
        Inventory(**valid_data).save()

        result = Inventory.query.first()
        assert isinstance(result.last_updated, datetime)


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that product_id must point to a real Product row.
#    WHY:  Orphan inventory rows (pointing to deleted/nonexistent products)
#          would cause silent data corruption and broken to_dict() calls
#          in Product that read inventory.quantity_available.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_product_id_raises(self, app, valid_data):
        # Nonexistent product_id should be rejected by FK constraint
        valid_data["product_id"] = "NONEXISTENT-SKU"
        with pytest.raises(Exception):
            Inventory(**valid_data).save()

    def test_valid_product_id_saves(self, app, valid_data):
        # Confirm the happy path works with a real product_id
        Inventory(**valid_data).save()
        assert Inventory.query.count() == 1


# ---------------------------------------------------------------------------
# 3. Unique Constraint on product_id
#
#    WHAT: One product can only have ONE inventory row (unique=True on FK).
#    WHY:  Product.inventory is uselist=False — it expects exactly one row.
#          A second inventory row for the same product would break
#          product.to_dict() which reads self.inventory.quantity_available.
# ---------------------------------------------------------------------------

class TestUniqueConstraint:
    def test_duplicate_product_id_raises(self, app, valid_data):
        # First inventory row saves fine
        Inventory(**valid_data).save()

        # Second row with the same product_id violates unique constraint
        with pytest.raises(Exception):
            Inventory(**valid_data).save()

    def test_different_products_can_each_have_inventory(self, app, product, second_product):
        # Each product can have its own inventory row — uniqueness is per product
        Inventory(product_id=product.product_id,
                  last_updated=datetime.utcnow()).save()
        Inventory(product_id=second_product.product_id,
                  last_updated=datetime.utcnow()).save()

        assert Inventory.query.count() == 2


# ---------------------------------------------------------------------------
# 4. Update Behavior
#
#    WHAT: Verifies that inventory quantities and last_updated can be
#          changed and persisted correctly.
#    WHY:  Inventory is one of the most frequently updated tables —
#          every sale, stock_in, and defect affects it. Silent update
#          failures would corrupt stock levels.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_quantity_available(self, app, inventory):
        # Simulates stock being added or sold
        inventory.quantity_available = 250
        inventory.save()

        result = Inventory.get_by_id(inventory.inventory_id)
        assert result.quantity_available == 250

    def test_update_quantity_defective(self, app, inventory):
        # Simulates defects being logged against inventory
        inventory.quantity_defective = 20
        inventory.save()

        result = Inventory.get_by_id(inventory.inventory_id)
        assert result.quantity_defective == 20

    def test_update_last_updated_timestamp(self, app, inventory):
        # last_updated should be refreshed whenever inventory changes
        new_time = datetime.utcnow() + timedelta(hours=1)
        inventory.last_updated = new_time
        inventory.save()

        result = Inventory.get_by_id(inventory.inventory_id)
        # Compare without microseconds to avoid floating point drift
        assert result.last_updated.replace(microsecond=0) == new_time.replace(microsecond=0)

    def test_quantity_available_can_be_zero(self, app, inventory):
        # Zero stock is a valid state — product exists but is out of stock
        inventory.quantity_available = 0
        inventory.save()

        result = Inventory.get_by_id(inventory.inventory_id)
        assert result.quantity_available == 0

    def test_quantity_available_can_be_large(self, app, inventory):
        # Large stock quantities should be stored without overflow
        inventory.quantity_available = 999999
        inventory.save()

        result = Inventory.get_by_id(inventory.inventory_id)
        assert result.quantity_available == 999999


# ---------------------------------------------------------------------------
# 5. Relationship — Product ↔ Inventory
#
#    WHAT: Verifies both sides of the bidirectional relationship work.
#    WHY:  Product.to_dict() reads self.inventory.quantity_available —
#          if the relationship is broken, to_dict() silently returns 0
#          for every product regardless of actual stock.
# ---------------------------------------------------------------------------

class TestRelationship:
    def test_product_inventory_relationship(self, app, product, inventory):
        # product.inventory should return the linked Inventory instance
        # uselist=False means it's a single object, not a list
        db.session.refresh(product)
        assert product.inventory is not None
        assert product.inventory.inventory_id == inventory.inventory_id

    def test_inventory_product_relationship(self, app, product, inventory):
        # inventory.product should return the linked Product instance
        db.session.refresh(inventory)
        assert inventory.product is not None
        assert inventory.product.product_id == product.product_id

    def test_product_inventory_is_not_a_list(self, app, product, inventory):
        # uselist=False — must be a single Inventory object, not a list
        db.session.refresh(product)
        assert not isinstance(product.inventory, list)

    def test_product_with_no_inventory_returns_none(self, app, product):
        # When no Inventory row exists for a product, the relationship is None
        db.session.refresh(product)
        assert product.inventory is None

    def test_product_to_dict_stock_matches_inventory(self, app, product, inventory):
        # End-to-end check: product.to_dict()["stock"] reads from inventory
        db.session.refresh(product)
        result = product.to_dict()
        assert result["stock"] == inventory.quantity_available


# ---------------------------------------------------------------------------
# 6. Cascade / Delete Behavior
#
#    WHAT: Verifies what happens when either side of the relationship
#          is deleted.
#    WHY:  There is no cascade defined from Product to Inventory in the
#          model — you'd need to delete inventory before deleting the
#          product (or add cascade). This makes that behavior explicit
#          so it doesn't surprise you later.
# ---------------------------------------------------------------------------

class TestDeleteBehavior:
    def test_deleting_inventory_does_not_delete_product(self, app, product, inventory):
        # Inventory has no cascade back to Product
        # Deleting inventory should leave the product intact
        inventory.delete()

        assert Product.query.count() == 1
        assert Inventory.query.count() == 0

    def test_deleting_inventory_allows_product_deletion(self, app, product, inventory):
        # After removing inventory, the product itself can be deleted cleanly
        inventory.delete()
        product.delete()

        assert Product.query.count() == 0
        assert Inventory.query.count() == 0


# ---------------------------------------------------------------------------
# 7. Inherited BaseModel methods
#
#    WHAT: Confirms save(), delete(), get_by_id(), get_all() work with
#          Inventory's specific schema.
#    WHY:  BaseModel is abstract — its methods are tested via DummyModel
#          in base_model_test.py, but we also spot-check here to confirm
#          nothing in Inventory's schema breaks the inherited behavior.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_inventory(self, app, valid_data):
        # save() should commit the row to the DB
        Inventory(**valid_data).save()
        assert Inventory.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance itself — allows method chaining
        inv = Inventory(**valid_data)
        returned = inv.save()
        assert returned is inv

    def test_delete_removes_inventory(self, app, inventory):
        # delete() should remove the row from the DB
        inventory.delete()
        assert Inventory.query.count() == 0

    def test_get_by_id_returns_correct_record(self, app, inventory):
        # get_by_id() should return the Inventory with the matching PK
        result = Inventory.get_by_id(inventory.inventory_id)

        assert result is not None
        assert result.inventory_id == inventory.inventory_id
        assert result.product_id == inventory.product_id

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent inventory_id should return None, not raise
        result = Inventory.get_by_id(99999)
        assert result is None

    def test_get_all_returns_all_inventory_rows(self, app, product, second_product):
        # get_all() returns every row in the Inventory table
        Inventory(product_id=product.product_id,
                  last_updated=datetime.utcnow()).save()
        Inventory(product_id=second_product.product_id,
                  last_updated=datetime.utcnow()).save()

        result = Inventory.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = Inventory.get_all()
        assert result == []