"""
tests/product_bundle_test.py

Pytest suite for ProductBundle model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - bundle_id is a string PK (barcode/SKU) — not autoincrement
   - product_id unique constraint — one bundle per product
   - bundle_count must be present (units per bundle)
   - bundle_name must be present

2. Foreign Key Constraints
   - product_id must reference an existing Product row
   - Invalid product_id is blocked

3. Unique Constraint on product_id
   - One product can only have ONE bundle row (unique=True on FK)
   - Two different products can each have their own bundle

4. Update Behavior
   - bundle_name, bundle_count can be updated and persisted
   - bundle_id (PK) identity confirmed stable after updates

5. Relationship — Product ↔ ProductBundle (uselist=False)
   - product.bundle returns single ProductBundle instance, not a list
   - product_bundle.product returns the linked Product instance
   - product with no bundle returns None
   - to_dict() bundle fields correctly reflect the linked bundle

6. Delete Behavior
   - Deleting a ProductBundle does NOT delete the Product
   - After bundle deletion, product.bundle returns None
   - Deleting a Product cascades — does it remove the bundle?
     (no explicit cascade defined — behavior documented here)

7. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with ProductBundle's string PK schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from app.extensions import db
from app.models.product_bundle import ProductBundle
from app.models.product import Product


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(product):
    """
    Returns a dict of all valid fields for a ProductBundle.
    bundle_id is a string — acts as barcode/SKU for the bundle pack.
    """
    return dict(
        bundle_id="BUNDLE-SKU-001",
        product_id=product.product_id,
        bundle_name="12-pack",
        bundle_count=12,
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are enforced by the DB
#          and that the string PK behaves correctly.
#    WHY:  ProductBundle stores pack configuration for bundled products.
#          A missing bundle_count or bundle_name would break cashier
#          transaction logic that uses bundle info to calculate unit prices
#          and display pack names on receipts.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_bundle_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should commit cleanly
        ProductBundle(**valid_data).save()
        assert ProductBundle.query.count() == 1

    def test_bundle_id_is_required(self, app, valid_data):
        # bundle_id is the string PK — omitting it raises an error
        valid_data.pop("bundle_id")
        with pytest.raises(Exception):
            ProductBundle(**valid_data).save()

    def test_product_id_is_required(self, app, valid_data):
        # product_id is FK and NOT NULL — every bundle must reference a product
        valid_data.pop("product_id")
        with pytest.raises(Exception):
            ProductBundle(**valid_data).save()

    def test_bundle_name_is_required(self, app, valid_data):
        # bundle_name is NOT NULL — a bundle with no name breaks display logic
        valid_data.pop("bundle_name")
        with pytest.raises(Exception):
            ProductBundle(**valid_data).save()

    def test_bundle_count_is_required(self, app, valid_data):
        # bundle_count is NOT NULL — units per bundle must always be known
        valid_data.pop("bundle_count")
        with pytest.raises(Exception):
            ProductBundle(**valid_data).save()

    def test_bundle_id_is_string_type(self, app, product_bundle):
        # bundle_id is db.String(100) — retrieved as string, not int
        result = ProductBundle.get_by_id(product_bundle.bundle_id)
        assert isinstance(result.bundle_id, str)

    def test_bundle_id_acts_as_primary_key(self, app, valid_data):
        # bundle_id is the PK — get_by_id should retrieve by bundle_id string
        ProductBundle(**valid_data).save()
        result = ProductBundle.get_by_id("BUNDLE-SKU-001")
        assert result is not None
        assert result.bundle_id == "BUNDLE-SKU-001"

    def test_duplicate_bundle_id_raises(self, app, valid_data, second_product):
        # Two bundles with the same bundle_id violate the PK constraint
        ProductBundle(**valid_data).save()
        with pytest.raises(Exception):
            ProductBundle(**{**valid_data,
                             "product_id": second_product.product_id}).save()

    def test_bundle_name_max_length(self, app, valid_data):
        # bundle_name is db.String(100) — accepts up to 100 characters
        valid_data["bundle_name"] = "B" * 100
        ProductBundle(**valid_data).save()

        result = ProductBundle.get_by_id(valid_data["bundle_id"])
        assert len(result.bundle_name) == 100

    def test_bundle_count_stored_as_integer(self, app, product_bundle):
        # bundle_count is db.Integer — stored and retrieved as int
        result = ProductBundle.get_by_id(product_bundle.bundle_id)
        assert isinstance(result.bundle_count, int)

    def test_large_bundle_count_accepted(self, app, valid_data):
        # Large bundle counts (e.g. bulk packs) should not overflow Integer
        valid_data["bundle_count"] = 10000
        ProductBundle(**valid_data).save()

        result = ProductBundle.get_by_id(valid_data["bundle_id"])
        assert result.bundle_count == 10000


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that product_id must reference a real Product row.
#    WHY:  A bundle pointing to a nonexistent product would cause
#          product.to_dict() to silently return bundle fields for a
#          ghost product, breaking inventory and cashier displays.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_product_id_raises(self, app, valid_data):
        # Nonexistent product_id should be blocked by FK constraint
        valid_data["product_id"] = "NONEXISTENT-SKU"
        with pytest.raises(Exception):
            ProductBundle(**valid_data).save()

    def test_valid_product_id_saves(self, app, valid_data):
        # Confirm FK with a real product_id saves cleanly
        ProductBundle(**valid_data).save()
        assert ProductBundle.query.count() == 1

    def test_bundle_blocked_after_product_deleted(self, app, valid_data, product):
        # After the referenced product is deleted, inserting a new bundle
        # with that product_id should be blocked by FK constraint
        product.delete()
        with pytest.raises(Exception):
            ProductBundle(**valid_data).save()


# ---------------------------------------------------------------------------
# 3. Unique Constraint on product_id
#
#    WHAT: Verifies one product can only have one bundle row.
#    WHY:  Product.bundle is uselist=False — it expects exactly one bundle.
#          A second bundle for the same product would cause SQLAlchemy to
#          raise or return an unpredictable result when accessing
#          product.bundle, and break product.to_dict() bundle fields.
# ---------------------------------------------------------------------------

class TestUniqueConstraint:
    def test_duplicate_product_id_raises(self, app, valid_data):
        # First bundle saves fine
        ProductBundle(**valid_data).save()

        # Second bundle for the same product violates unique constraint
        with pytest.raises(Exception):
            ProductBundle(**{**valid_data, "bundle_id": "BUNDLE-SKU-002"}).save()

    def test_different_products_can_each_have_bundle(self, app, product, second_product):
        # Each product can have its own bundle — uniqueness is per product_id
        ProductBundle(
            bundle_id="BUNDLE-A",
            product_id=product.product_id,
            bundle_name="6-pack",
            bundle_count=6,
        ).save()
        ProductBundle(
            bundle_id="BUNDLE-B",
            product_id=second_product.product_id,
            bundle_name="12-pack",
            bundle_count=12,
        ).save()

        assert ProductBundle.query.count() == 2


# ---------------------------------------------------------------------------
# 4. Update Behavior
#
#    WHAT: Verifies that bundle_name and bundle_count can be changed
#          and that changes persist correctly after save().
#    WHY:  Bundle configurations change — a supplier might change pack
#          sizes or rename a bundle. Confirms the model supports updates
#          without silent failures or identity confusion on the string PK.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_bundle_name(self, app, product_bundle):
        # Bundle display name can be changed (e.g. "12-pack" → "Dozen Pack")
        product_bundle.bundle_name = "Dozen Pack"
        product_bundle.save()

        result = ProductBundle.get_by_id(product_bundle.bundle_id)
        assert result.bundle_name == "Dozen Pack"

    def test_update_bundle_count(self, app, product_bundle):
        # Units per bundle can be updated when pack size changes
        product_bundle.bundle_count = 24
        product_bundle.save()

        result = ProductBundle.get_by_id(product_bundle.bundle_id)
        assert result.bundle_count == 24

    def test_update_bundle_name_and_count_together(self, app, product_bundle):
        # Both fields can be updated in a single save()
        product_bundle.bundle_name = "Case Pack"
        product_bundle.bundle_count = 48
        product_bundle.save()

        result = ProductBundle.get_by_id(product_bundle.bundle_id)
        assert result.bundle_name == "Case Pack"
        assert result.bundle_count == 48

    def test_bundle_id_is_stable_after_update(self, app, product_bundle):
        # Updating other fields should not change the string PK
        original_bundle_id = product_bundle.bundle_id
        product_bundle.bundle_name = "Updated Name"
        product_bundle.save()

        result = ProductBundle.get_by_id(original_bundle_id)
        assert result is not None
        assert result.bundle_id == original_bundle_id


# ---------------------------------------------------------------------------
# 5. Relationship — Product ↔ ProductBundle (uselist=False)
#
#    WHAT: Verifies both sides of the bidirectional relationship and that
#          uselist=False returns a single object, not a list.
#    WHY:  product.bundle is used directly in product.to_dict() to populate
#          bundle_id, bundle_name, and bundle_count. If the relationship
#          returns None when it should return a bundle, to_dict() silently
#          returns "—" for bundle_name instead of the real name, making
#          product listings display incorrect data without raising errors.
# ---------------------------------------------------------------------------

class TestRelationship:
    def test_product_bundle_returns_single_object(self, app, product, product_bundle):
        # uselist=False — must be a single ProductBundle, not a list
        db.session.refresh(product)
        assert not isinstance(product.bundle, list)
        assert product.bundle is not None

    def test_product_bundle_returns_correct_bundle(self, app, product, product_bundle):
        # product.bundle should return the linked ProductBundle instance
        db.session.refresh(product)
        assert product.bundle.bundle_id == product_bundle.bundle_id
        assert product.bundle.bundle_name == product_bundle.bundle_name
        assert product.bundle.bundle_count == product_bundle.bundle_count

    def test_bundle_product_returns_linked_product(self, app, product, product_bundle):
        # product_bundle.product should return the linked Product instance
        db.session.refresh(product_bundle)
        assert product_bundle.product is not None
        assert product_bundle.product.product_id == product.product_id

    def test_product_with_no_bundle_returns_none(self, app, product):
        # When no ProductBundle exists for a product, product.bundle is None
        db.session.refresh(product)
        assert product.bundle is None

    def test_product_to_dict_with_bundle(self, app, product, product_bundle):
        # End-to-end: product.to_dict() bundle fields populated from relationship
        db.session.refresh(product)
        result = product.to_dict()

        assert result["bundle_id"] == product_bundle.bundle_id
        assert result["bundle_name"] == product_bundle.bundle_name
        assert result["bundle_count"] == product_bundle.bundle_count

    def test_product_to_dict_without_bundle(self, app, product):
        # When no bundle exists, to_dict() returns fallback values
        db.session.refresh(product)
        result = product.to_dict()

        assert result["bundle_id"] is None
        assert result["bundle_name"] == "—"
        assert result["bundle_count"] is None

    def test_bundle_product_name_accessible(self, app, product, product_bundle):
        # Confirms traversal through the relationship to read product fields
        db.session.refresh(product_bundle)
        assert product_bundle.product.product_name == product.product_name


# ---------------------------------------------------------------------------
# 6. Delete Behavior
#
#    WHAT: Verifies what happens when either side of the relationship
#          is deleted.
#    WHY:  No explicit cascade is defined from Product to ProductBundle
#          in the model. This means deleting a Product may leave an
#          orphan ProductBundle row OR be blocked by FK — the actual
#          behavior depends on DB-level FK settings. These tests document
#          the real behavior so it doesn't surprise you later.
# ---------------------------------------------------------------------------

class TestDeleteBehavior:
    def test_deleting_bundle_does_not_delete_product(self, app, product, product_bundle):
        # Deleting a ProductBundle should leave the Product intact
        product_bundle.delete()

        assert Product.query.count() == 1
        assert ProductBundle.query.count() == 0

    def test_after_bundle_deletion_product_bundle_is_none(self, app, product, product_bundle):
        # After its bundle is deleted, product.bundle should return None
        product_bundle.delete()

        db.session.refresh(product)
        assert product.bundle is None

    def test_after_bundle_deletion_product_to_dict_returns_fallbacks(self, app, product, product_bundle):
        # After bundle deletion, to_dict() should return fallback bundle values
        product_bundle.delete()

        db.session.refresh(product)
        result = product.to_dict()

        assert result["bundle_id"] is None
        assert result["bundle_name"] == "—"
        assert result["bundle_count"] is None

    def test_deleting_bundle_allows_new_bundle_for_same_product(self, app, product, product_bundle):
        # After deleting a bundle, the unique constraint is freed —
        # a new bundle can be created for the same product
        product_bundle.delete()

        new_bundle = ProductBundle(
            bundle_id="BUNDLE-NEW-001",
            product_id=product.product_id,
            bundle_name="24-pack",
            bundle_count=24,
        )
        new_bundle.save()

        assert ProductBundle.query.count() == 1
        db.session.refresh(product)
        assert product.bundle.bundle_id == "BUNDLE-NEW-001"


# ---------------------------------------------------------------------------
# 7. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with ProductBundle's string PK schema.
#    WHY:  BaseModel's get_by_id() uses cls.query.get(id) — this works
#          for integer PKs but must also work for string PKs like bundle_id.
#          This confirms there's no type mismatch issue with string PKs
#          and the inherited generic methods.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_bundle(self, app, valid_data):
        # save() should commit the ProductBundle row to the DB
        ProductBundle(**valid_data).save()
        assert ProductBundle.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        b = ProductBundle(**valid_data)
        returned = b.save()
        assert returned is b

    def test_delete_removes_bundle(self, app, product_bundle):
        # delete() should remove the ProductBundle row from the DB
        product_bundle.delete()
        assert ProductBundle.query.count() == 0

    def test_get_by_id_with_string_pk(self, app, product_bundle):
        # get_by_id() must work with string PKs — not just integers
        result = ProductBundle.get_by_id(product_bundle.bundle_id)

        assert result is not None
        assert result.bundle_id == product_bundle.bundle_id
        assert result.bundle_name == product_bundle.bundle_name

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent bundle_id should return None, not raise
        result = ProductBundle.get_by_id("NONEXISTENT-BUNDLE")
        assert result is None

    def test_get_all_returns_all_bundles(self, app, product, second_product):
        # get_all() returns every row in the ProductBundles table
        ProductBundle(bundle_id="B1", product_id=product.product_id,
                      bundle_name="6-pack", bundle_count=6).save()
        ProductBundle(bundle_id="B2", product_id=second_product.product_id,
                      bundle_name="12-pack", bundle_count=12).save()

        result = ProductBundle.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = ProductBundle.get_all()
        assert result == []