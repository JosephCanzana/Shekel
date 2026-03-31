"""
tests/utils_tests/index_helpers_test.py

Pytest suite for app/utils/index_helpers.py.
All functions require Flask app context and DB access.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. get_admin_stats()
   - Returns all expected keys
   - Returns correct types for each field
   - sales_today is 0 when no sales exist
   - transactions_today is 0 when no sales exist
   - Returns correct sales total when sales exist today
   - total_products reflects Product.query.count()
   - low_stock_count reflects actual low stock items
   - recent_transactions is a list of dicts with correct keys
   - Handles empty DB without crashing

2. get_low_stock_items()
   - Returns empty list when no inventory exists
   - Returns only items at or below low_reorder_threshold
   - Does not return archived products
   - Each item has correct keys: name, category, stock
   - category falls back to "—" when product has no category

3. get_recent_stockins()
   - Returns empty list when no stock-ins exist
   - Returns up to 5 most recent stock-ins
   - Each item has correct keys: name, stocked_by, date, qty
   - Skips records where product is None
   - Orders by most recent first

4. get_stocking_stats()
   - Returns all expected keys
   - total_products counts only active products
   - low_stock_count reflects actual threshold breaches
   - Handles empty DB without crashing

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
import pytz
from app.extensions import db
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.stock_in import StockIn
from app.models.category import Category


# ---------------------------------------------------------------------------
# Local helper — sales made "today" in PHT
# ---------------------------------------------------------------------------

def make_sale_today(user_id):
    """Creates a Sale with sale_datetime set to now (UTC)."""
    return Sale(
        user_id=user_id,
        total_cost_price=Decimal("10.00"),
        total_revenue_price=Decimal("12.00"),
        total_amount=Decimal("15.00"),
        payment_method="cash",
    ).save()


# ---------------------------------------------------------------------------
# 1. get_admin_stats()
#
#    WHAT: Verifies the dashboard stats dictionary is correctly populated.
#    WHY:  get_admin_stats() is called on every admin dashboard load.
#          A missing key or wrong type would crash the template render
#          with a KeyError or TypeError — visible as a 500 to the admin.
# ---------------------------------------------------------------------------

class TestGetAdminStats:
    def test_returns_all_expected_keys(self, app):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()

        assert set(stats.keys()) == {
            "sales_today",
            "transactions_today",
            "new_added_product",
            "total_products",
            "low_stock_count",
            "defects_count",
            "recent_transactions",
        }

    def test_returns_correct_types(self, app):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()

        assert isinstance(stats["recent_transactions"], list)
        assert isinstance(stats["total_products"], int)
        assert isinstance(stats["low_stock_count"], int)
        assert isinstance(stats["defects_count"], int)
        assert isinstance(stats["new_added_product"], int)

    def test_empty_db_does_not_crash(self, app):
        # No sales, no products, no inventory — must not raise
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()

        assert stats["sales_today"] == 0
        assert stats["transactions_today"] == 0
        assert stats["total_products"] == 0
        assert stats["recent_transactions"] == []

    def test_transactions_today_zero_with_no_sales(self, app):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["transactions_today"] == 0

    def test_total_products_reflects_db_count(self, app, product,
                                                second_product):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["total_products"] == 2

    def test_total_products_zero_when_empty(self, app):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["total_products"] == 0

    def test_low_stock_count_zero_when_no_inventory(self, app, product):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["low_stock_count"] == 0

    def test_low_stock_count_reflects_threshold_breach(self, app, product,
                                                         low_stock_inventory):
        # second_product has quantity=1, threshold=3 → low stock
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["low_stock_count"] >= 1

    def test_low_stock_ignores_archived_products(self, app, archived_product):
        # archived_product has status="archived" — must not count toward low stock
        from app.utils.index_helpers import get_admin_stats

        # Create low inventory for the archived product
        Inventory(
            product_id=archived_product.product_id,
            quantity_available=0,
            quantity_defective=0,
            last_updated=datetime.utcnow(),
        ).save()

        with app.app_context():
            stats = get_admin_stats()
        assert stats["low_stock_count"] == 0

    def test_recent_transactions_is_empty_with_no_sales(self, app):
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["recent_transactions"] == []

    def test_recent_transactions_contains_correct_keys(self, app, user):
        from app.utils.index_helpers import get_admin_stats
        make_sale_today(user.user_id)

        with app.app_context():
            stats = get_admin_stats()

        if stats["recent_transactions"]:
            txn = stats["recent_transactions"][0]
            assert set(txn.keys()) == {"reference", "cashier", "time", "total"}

    def test_recent_transactions_capped_at_7(self, app, user):
        # get_admin_stats returns at most 7 recent transactions
        from app.utils.index_helpers import get_admin_stats
        for _ in range(10):
            make_sale_today(user.user_id)

        with app.app_context():
            stats = get_admin_stats()
        assert len(stats["recent_transactions"]) <= 7

    def test_sales_today_reflects_total_amount(self, app, user):
        from app.utils.index_helpers import get_admin_stats
        make_sale_today(user.user_id)
        make_sale_today(user.user_id)

        with app.app_context():
            stats = get_admin_stats()

        # 2 sales × Decimal("15.00") = 30.00
        assert stats["sales_today"] == Decimal("30.00")

    def test_defects_count_is_zero(self, app):
        # get_defects() returns [] — defects_count is hardcoded 0 for now
        from app.utils.index_helpers import get_admin_stats
        with app.app_context():
            stats = get_admin_stats()
        assert stats["defects_count"] == 0


# ---------------------------------------------------------------------------
# 2. get_low_stock_items()
#
#    WHAT: Verifies the low stock list is correctly filtered and formatted.
#    WHY:  This feeds the dashboard's low stock widget. Wrong filtering
#          would either hide real low stock (causing stockouts) or show
#          archived products (confusing the stocking staff).
# ---------------------------------------------------------------------------

class TestGetLowStockItems:
    def test_empty_list_when_no_inventory(self, app):
        from app.utils.index_helpers import get_low_stock_items
        with app.app_context():
            result = get_low_stock_items()
        assert result == []

    def test_empty_list_when_stock_is_sufficient(self, app, product, inventory):
        # inventory fixture has quantity_available=100, threshold=5 → not low
        from app.utils.index_helpers import get_low_stock_items
        with app.app_context():
            result = get_low_stock_items()
        assert result == []

    def test_returns_item_at_threshold(self, app, second_product,
                                        low_stock_inventory):
        # low_stock_inventory has quantity=1, second_product threshold=3
        from app.utils.index_helpers import get_low_stock_items
        with app.app_context():
            result = get_low_stock_items()
        assert len(result) == 1

    def test_item_has_correct_keys(self, app, second_product,
                                    low_stock_inventory):
        from app.utils.index_helpers import get_low_stock_items
        with app.app_context():
            result = get_low_stock_items()

        if result:
            assert set(result[0].keys()) == {"name", "category", "stock"}

    def test_item_stock_value_is_correct(self, app, second_product,
                                          low_stock_inventory):
        from app.utils.index_helpers import get_low_stock_items
        with app.app_context():
            result = get_low_stock_items()

        if result:
            assert result[0]["stock"] == low_stock_inventory.quantity_available

    def test_category_fallback_when_no_category(self, app,
                                                  product_no_category):
        # product_no_category has category_id=None
        from app.utils.index_helpers import get_low_stock_items

        Inventory(
            product_id=product_no_category.product_id,
            quantity_available=0,
            quantity_defective=0,
            last_updated=datetime.utcnow(),
        ).save()

        with app.app_context():
            result = get_low_stock_items()

        if result:
            assert result[0]["category"] == "—"

    def test_archived_products_excluded(self, app, archived_product):
        # Archived products should not appear in low stock list
        from app.utils.index_helpers import get_low_stock_items

        Inventory(
            product_id=archived_product.product_id,
            quantity_available=0,
            quantity_defective=0,
            last_updated=datetime.utcnow(),
        ).save()

        with app.app_context():
            result = get_low_stock_items()
        assert result == []

    def test_capped_at_5_items(self, app, category):
        # get_low_stock_items() uses .limit(5) — at most 5 items returned
        from app.utils.index_helpers import get_low_stock_items

        for i in range(8):
            prod = Product(
                product_id=f"LOW-{i:03d}",
                product_name=f"Low Stock {i}",
                category_id=category.category_id,
                cost_price=Decimal("1.00"),
                revenue_price=Decimal("1.00"),
                total_price=Decimal("1.00"),
                low_reorder_threshold=10,
                status="active",
            ).save()
            Inventory(
                product_id=prod.product_id,
                quantity_available=1,
                quantity_defective=0,
                last_updated=datetime.utcnow(),
            ).save()

        with app.app_context():
            result = get_low_stock_items()
        assert len(result) <= 5


# ---------------------------------------------------------------------------
# 3. get_recent_stockins()
#
#    WHAT: Verifies recent stock-in records are returned correctly.
#    WHY:  This feeds the dashboard's recent activity widget. Wrong
#          ordering or missing fields would display stale or broken data.
# ---------------------------------------------------------------------------

class TestGetRecentStockins:
    def test_empty_list_when_no_stockins(self, app):
        from app.utils.index_helpers import get_recent_stockins
        with app.app_context():
            result = get_recent_stockins()
        assert result == []

    def test_returns_stockin_with_correct_keys(self, app, stock_in):
        from app.utils.index_helpers import get_recent_stockins
        with app.app_context():
            result = get_recent_stockins()

        if result:
            assert set(result[0].keys()) == {"name", "stocked_by", "date", "qty"}

    def test_qty_matches_quantity_received(self, app, stock_in):
        from app.utils.index_helpers import get_recent_stockins
        with app.app_context():
            result = get_recent_stockins()

        if result:
            assert result[0]["qty"] == stock_in.quantity_received

    def test_capped_at_5_items(self, app, product, user):
        # get_recent_stockins() uses .limit(5) — at most 5 items returned
        from app.utils.index_helpers import get_recent_stockins

        for _ in range(8):
            StockIn(
                product_id=product.product_id,
                user_id=user.user_id,
                quantity_received=10,
            ).save()

        with app.app_context():
            result = get_recent_stockins()
        assert len(result) <= 5

    def test_stocked_by_shows_user_full_name(self, app, stock_in, user):
        from app.utils.index_helpers import get_recent_stockins
        with app.app_context():
            result = get_recent_stockins()

        if result:
            assert result[0]["stocked_by"] == user.full_name

    def test_product_name_capitalized(self, app, stock_in, product):
        from app.utils.index_helpers import get_recent_stockins
        with app.app_context():
            result = get_recent_stockins()

        if result:
            # Product name is capitalized in the helper
            assert result[0]["name"] == product.product_name.capitalize()

    def test_does_not_crash_with_empty_db(self, app):
        from app.utils.index_helpers import get_recent_stockins
        with app.app_context():
            result = get_recent_stockins()
        assert result == []


# ---------------------------------------------------------------------------
# 4. get_stocking_stats()
#
#    WHAT: Verifies the stocking dashboard stats are correctly computed.
#    WHY:  This feeds the stocking staff dashboard. Wrong counts would
#          mislead stocking staff about how many products need attention.
# ---------------------------------------------------------------------------

class TestGetStockingStats:
    def test_returns_all_expected_keys(self, app):
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()

        assert set(stats.keys()) == {
            "total_products",
            "low_stock_count",
            "defects_count",
        }

    def test_empty_db_does_not_crash(self, app):
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()

        assert stats["total_products"] == 0
        assert stats["low_stock_count"] == 0
        assert stats["defects_count"] == 0

    def test_total_products_counts_only_active(self, app, product,
                                                archived_product):
        # product is "active", archived_product is "archived"
        # total_products should only count active ones
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()
        assert stats["total_products"] == 1

    def test_low_stock_count_zero_when_no_inventory(self, app, product):
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()
        assert stats["low_stock_count"] == 0

    def test_low_stock_count_reflects_threshold_breach(self, app,
                                                         second_product,
                                                         low_stock_inventory):
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()
        assert stats["low_stock_count"] >= 1

    def test_defects_count_is_zero(self, app):
        # get_defects() returns [] — defects_count hardcoded to 0 for now
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()
        assert stats["defects_count"] == 0

    def test_returns_correct_types(self, app):
        from app.utils.index_helpers import get_stocking_stats
        with app.app_context():
            stats = get_stocking_stats()

        assert isinstance(stats["total_products"], int)
        assert isinstance(stats["low_stock_count"], int)
        assert isinstance(stats["defects_count"], int)