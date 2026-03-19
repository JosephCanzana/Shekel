"""
tests/product_test.py

Pytest suite for Product model.
Covers: column constraints, enum validation, Numeric precision,
        to_dict() with all relationship branches, and inherited
        BaseModel methods.

All base fixtures come from tests/conftest.py.
"""

"""
What's covered
Column Constraints — all 7 nullable=False fields individually tested; product_id confirmed as string PK (not autoincrement); duplicate product_id blocked; category_id confirmed nullable; created_at auto-populated by server_default; product_name accepts 150 chars
Enum — status — both valid values (active, archived) via parametrize; 6 invalid values rejected including wrong case and empty string
Numeric Precision — all 3 price fields confirmed as Decimal type; correct 2dp values; max value 99999999.99 accepted; zero prices accepted
to_dict() — no relationships — all 13 keys present; prices converted to float; missing inventory → stock=0; missing bundle → bundle_id=None, bundle_name="—", bundle_count=None; missing category → category_name="—"; created_at formatted as "Mon DD, YYYY"
to_dict() — with relationships — correct stock from inventory; correct category_name from category; all 3 bundle fields populated; zero-quantity inventory returns stock=0
FK Constraints — invalid category_id blocked; valid FK saves cleanly
Update behavior — name, status, prices, threshold, category reassignment, and category removal (set to None) all persist correctly
Inherited BaseModel — save, delete, get_by_id, get_all; confirms active/archived filtering works on the result set
"""

import pytest
from decimal import Decimal
from datetime import datetime
from app.extensions import db
from app.models.product import Product
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.product_bundle import ProductBundle


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(category):
    """Returns a dict of all valid fields for a Product."""
    return dict(
        product_id="TEST-SKU-001",
        product_name="Test Product",
        category_id=category.category_id,
        unit_price=Decimal("10.00"),
        revenue_price=Decimal("12.00"),
        product_price=Decimal("15.00"),
        low_reorder_threshold=5,
        status="active",
    )


# ---------------------------------------------------------------------------
# Column Constraints
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_product_saves_successfully(self, app, valid_data):
        """A fully populated Product saves without error."""
        Product(**valid_data).save()
        assert Product.query.count() == 1

    def test_product_id_is_required(self, app, valid_data):
        """product_id is the primary key — omitting raises an error."""
        valid_data.pop("product_id")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_product_name_is_required(self, app, valid_data):
        """product_name is NOT NULL — omitting raises an error."""
        valid_data.pop("product_name")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_unit_price_is_required(self, app, valid_data):
        """unit_price is NOT NULL — omitting raises an error."""
        valid_data.pop("unit_price")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_revenue_price_is_required(self, app, valid_data):
        """revenue_price is NOT NULL — omitting raises an error."""
        valid_data.pop("revenue_price")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_product_price_is_required(self, app, valid_data):
        """product_price is NOT NULL — omitting raises an error."""
        valid_data.pop("product_price")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_low_reorder_threshold_is_required(self, app, valid_data):
        """low_reorder_threshold is NOT NULL — omitting raises an error."""
        valid_data.pop("low_reorder_threshold")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_status_is_required(self, app, valid_data):
        """status is NOT NULL — omitting raises an error."""
        valid_data.pop("status")
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_category_id_is_optional(self, app, product_no_category):
        """category_id is nullable — a product without a category saves cleanly."""
        assert product_no_category.category_id is None
        assert Product.query.count() == 1

    def test_duplicate_product_id_raises(self, app, product, valid_data):
        """Two products with the same product_id violate the PK constraint."""
        valid_data["product_id"] = product.product_id
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_product_id_is_string_type(self, app, product):
        """product_id is stored and retrieved as a string (barcode/SKU)."""
        result = Product.get_by_id(product.product_id)
        assert isinstance(result.product_id, str)

    def test_product_name_max_length(self, app, valid_data):
        """product_name accepts strings up to 150 characters."""
        valid_data["product_name"] = "A" * 150
        Product(**valid_data).save()

        result = Product.get_by_id(valid_data["product_id"])
        assert len(result.product_name) == 150

    def test_created_at_is_set_automatically(self, app, product):
        """created_at is auto-populated by server_default on insert."""
        result = Product.get_by_id(product.product_id)
        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)


# ---------------------------------------------------------------------------
# Enum Constraints — status
# ---------------------------------------------------------------------------

class TestStatusEnum:
    @pytest.mark.parametrize("valid_status", ["active", "archived"])
    def test_valid_status_values_accepted(self, app, valid_data, valid_status):
        """Each valid status enum value saves without error."""
        valid_data["status"] = valid_status
        Product(**valid_data).save()
        assert Product.query.filter_by(status=valid_status).count() == 1

    @pytest.mark.parametrize("invalid_status", [
        "inactive", "disabled", "pending", "", "Active", "ARCHIVED"
    ])
    def test_invalid_status_values_rejected(self, app, valid_data, invalid_status):
        """Invalid status values outside the enum should raise an error."""
        valid_data["status"] = invalid_status
        with pytest.raises(Exception):
            Product(**valid_data).save()


# ---------------------------------------------------------------------------
# Numeric Precision — price fields
# ---------------------------------------------------------------------------

class TestNumericPrecision:
    def test_prices_stored_as_decimal(self, app, product):
        """All price fields are retrieved as Decimal instances."""
        result = Product.get_by_id(product.product_id)

        assert isinstance(result.unit_price, Decimal)
        assert isinstance(result.revenue_price, Decimal)
        assert isinstance(result.product_price, Decimal)

    def test_prices_stored_with_two_decimal_places(self, app, product):
        """Price values are stored and retrieved correctly at 2dp."""
        result = Product.get_by_id(product.product_id)

        assert result.unit_price == Decimal("10.00")
        assert result.revenue_price == Decimal("12.00")
        assert result.product_price == Decimal("15.00")

    def test_large_price_within_numeric_bounds(self, app, valid_data):
        """Numeric(10, 2) allows values up to 99999999.99."""
        valid_data["unit_price"] = Decimal("99999999.99")
        valid_data["revenue_price"] = Decimal("99999999.99")
        valid_data["product_price"] = Decimal("99999999.99")
        Product(**valid_data).save()

        result = Product.get_by_id(valid_data["product_id"])
        assert result.unit_price == Decimal("99999999.99")

    def test_zero_price_is_accepted(self, app, valid_data):
        """Zero is a valid Numeric value for prices."""
        valid_data["unit_price"] = Decimal("0.00")
        valid_data["revenue_price"] = Decimal("0.00")
        valid_data["product_price"] = Decimal("0.00")
        Product(**valid_data).save()

        result = Product.get_by_id(valid_data["product_id"])
        assert result.unit_price == Decimal("0.00")


# ---------------------------------------------------------------------------
# Product.to_dict() — no relationships loaded
# ---------------------------------------------------------------------------

class TestToDictNoRelationships:
    def test_all_keys_present(self, app, product):
        """to_dict() returns all expected keys."""
        result = product.to_dict()

        assert set(result.keys()) == {
            "product_id", "product_name", "category_id", "category_name",
            "bundle_id", "bundle_name", "bundle_count",
            "unit_price", "revenue_price", "product_price",
            "low_reorder_threshold", "status", "stock", "created_at",
        }

    def test_prices_are_floats_in_dict(self, app, product):
        """to_dict() converts Decimal prices to float via float()."""
        result = product.to_dict()

        assert isinstance(result["unit_price"], float)
        assert isinstance(result["revenue_price"], float)
        assert isinstance(result["product_price"], float)

    def test_price_values_correct_in_dict(self, app, product):
        """to_dict() price values match the stored Decimal values."""
        result = product.to_dict()

        assert result["unit_price"] == 10.00
        assert result["revenue_price"] == 12.00
        assert result["product_price"] == 15.00

    def test_no_inventory_returns_zero_stock(self, app, product):
        """When no Inventory row exists, stock defaults to 0."""
        result = product.to_dict()
        assert result["stock"] == 0

    def test_no_bundle_returns_none_bundle_id(self, app, product):
        """When no ProductBundle exists, bundle_id is None."""
        result = product.to_dict()
        assert result["bundle_id"] is None

    def test_no_bundle_returns_dash_bundle_name(self, app, product):
        """When no ProductBundle exists, bundle_name is '—'."""
        result = product.to_dict()
        assert result["bundle_name"] == "—"

    def test_no_bundle_returns_none_bundle_count(self, app, product):
        """When no ProductBundle exists, bundle_count is None."""
        result = product.to_dict()
        assert result["bundle_count"] is None

    def test_no_category_returns_dash_category_name(self, app, product_no_category):
        """When category_id is None, category_name falls back to '—'."""
        result = product_no_category.to_dict()
        assert result["category_name"] == "—"

    def test_created_at_is_formatted_string(self, app, product):
        """created_at in dict is formatted as 'Mon DD, YYYY' string."""
        result = product.to_dict()

        assert result["created_at"] != ""
        # Validate the format — should parse back to a date
        parsed = datetime.strptime(result["created_at"], "%b %d, %Y")
        assert isinstance(parsed, datetime)

    def test_product_id_and_name_correct_in_dict(self, app, product):
        """product_id and product_name values match the model fields."""
        result = product.to_dict()

        assert result["product_id"] == product.product_id
        assert result["product_name"] == product.product_name

    def test_low_reorder_threshold_correct_in_dict(self, app, product):
        """low_reorder_threshold is returned as an integer."""
        result = product.to_dict()

        assert result["low_reorder_threshold"] == product.low_reorder_threshold
        assert isinstance(result["low_reorder_threshold"], int)


# ---------------------------------------------------------------------------
# Product.to_dict() — with relationships loaded
# ---------------------------------------------------------------------------

class TestToDictWithRelationships:
    def test_with_inventory_returns_correct_stock(self, app, product, inventory):
        """When Inventory exists, stock reflects quantity_available."""
        result = product.to_dict()
        assert result["stock"] == inventory.quantity_available

    def test_with_category_returns_category_name(self, app, product, category):
        """When category is linked, category_name is the category's name."""
        result = product.to_dict()
        assert result["category_name"] == category.category_name

    def test_with_bundle_returns_bundle_fields(self, app, product, product_bundle):
        """When ProductBundle exists, bundle fields are populated correctly."""
        result = product.to_dict()

        assert result["bundle_id"] == product_bundle.bundle_id
        assert result["bundle_name"] == product_bundle.bundle_name
        assert result["bundle_count"] == product_bundle.bundle_count

    def test_with_zero_inventory_stock_is_zero(self, app, product):
        """When Inventory exists but quantity_available is 0, stock is 0."""
        inv = Inventory(
            product_id=product.product_id,
            quantity_available=0,
            quantity_defective=0,
            last_updated=datetime.utcnow(),
        )
        inv.save()

        result = product.to_dict()
        assert result["stock"] == 0


# ---------------------------------------------------------------------------
# FK Constraint — category_id
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_category_id_raises(self, app, valid_data):
        """category_id must reference an existing Category row."""
        valid_data["category_id"] = 99999
        with pytest.raises(Exception):
            Product(**valid_data).save()

    def test_valid_category_id_saves(self, app, valid_data, category):
        """A valid category_id FK reference saves cleanly."""
        valid_data["category_id"] = category.category_id
        Product(**valid_data).save()
        assert Product.query.count() == 1


# ---------------------------------------------------------------------------
# Product update behavior
# ---------------------------------------------------------------------------

class TestProductUpdates:
    def test_update_product_name(self, app, product):
        """Updating product_name and saving persists the change."""
        product.product_name = "Updated Name"
        product.save()

        result = Product.get_by_id(product.product_id)
        assert result.product_name == "Updated Name"

    def test_update_status_to_archived(self, app, product):
        """Status can be changed from active to archived."""
        product.status = "archived"
        product.save()

        result = Product.get_by_id(product.product_id)
        assert result.status == "archived"

    def test_update_prices(self, app, product):
        """Price fields can be updated and persisted."""
        product.unit_price = Decimal("99.99")
        product.revenue_price = Decimal("110.00")
        product.product_price = Decimal("125.00")
        product.save()

        result = Product.get_by_id(product.product_id)
        assert result.unit_price == Decimal("99.99")
        assert result.revenue_price == Decimal("110.00")
        assert result.product_price == Decimal("125.00")

    def test_update_low_reorder_threshold(self, app, product):
        """low_reorder_threshold can be updated."""
        product.low_reorder_threshold = 20
        product.save()

        result = Product.get_by_id(product.product_id)
        assert result.low_reorder_threshold == 20

    def test_reassign_category(self, app, product, second_category):
        """A product can be moved to a different category."""
        product.category_id = second_category.category_id
        product.save()

        result = Product.get_by_id(product.product_id)
        assert result.category_id == second_category.category_id

    def test_remove_category(self, app, product):
        """category_id can be set to None (product becomes uncategorized)."""
        product.category_id = None
        product.save()

        result = Product.get_by_id(product.product_id)
        assert result.category_id is None


# ---------------------------------------------------------------------------
# Inherited BaseModel methods
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_product(self, app, valid_data):
        """save() commits a Product to the database."""
        Product(**valid_data).save()
        assert Product.query.count() == 1

    def test_delete_removes_product(self, app, product):
        """delete() removes the Product from the database."""
        product.delete()
        assert Product.query.count() == 0

    def test_get_by_id_returns_correct_product(self, app, product):
        """get_by_id() retrieves the correct Product by primary key."""
        result = Product.get_by_id(product.product_id)

        assert result is not None
        assert result.product_id == product.product_id
        assert result.product_name == product.product_name

    def test_get_by_id_returns_none_for_missing(self, app):
        """get_by_id() returns None for a non-existent product_id."""
        result = Product.get_by_id("NONEXISTENT-SKU")
        assert result is None

    def test_get_all_returns_all_products(self, app, product, second_product, archived_product):
        """get_all() returns every saved Product."""
        result = Product.get_all()
        assert len(result) == 3

    def test_get_all_empty_returns_empty_list(self, app):
        """get_all() returns an empty list when no products exist."""
        result = Product.get_all()
        assert result == []

    def test_get_all_filters_by_status(self, app, product, archived_product):
        """Active and archived products can be filtered from get_all()."""
        all_products = Product.get_all()
        active = [p for p in all_products if p.status == "active"]
        archived = [p for p in all_products if p.status == "archived"]

        assert len(active) == 1
        assert len(archived) == 1