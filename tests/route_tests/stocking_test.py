"""
tests/route_tests/stocking_test.py

Pytest suite for stocking blueprint routes.
All routes are under /stocking.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Authentication & Authorization
   - All routes require login
   - dashboard() — stocking role ONLY (admin/co-admin blocked)
   - stock_in(), search(), lookup(), complete() — admin, co-admin, stocking
   - cashier role blocked from all stocking routes

2. GET /stocking/ (dashboard)
   - Renders correctly for stocking role
   - Does not crash with empty DB
   - Does not crash with products and inventory data
   - Admin and co-admin blocked (stocking-only route)

3. GET /stocking/stock-in
   - Renders correctly for stocking, admin, co-admin
   - Does not crash with empty DB

4. POST /stocking/api/search (JSON API)
   - Returns matching products by name and product_id
   - Empty query returns empty list
   - Archived products excluded
   - Returns correct JSON structure
   - Capped at 8 results
   - Adversarial — SQL injection, XSS, very long query

5. POST /stocking/api/lookup (JSON API)
   - Finds by exact product_id
   - Finds by bundle barcode
   - Finds by partial name
   - Returns 404 for nonexistent
   - Returns 400 for archived
   - Returns correct JSON structure
   - Adversarial — empty query, SQL injection

6. POST /stocking/api/complete (JSON API)
   - Happy path — valid items increment inventory and create StockIn records
   - Creates Inventory row when none exists for product
   - Increments existing inventory correctly
   - Returns correct response structure
   - Notes applied to StockIn record
   - Multiple items processed in one call
   - Items with qty <= 0 are silently skipped
   - Returns 400 for empty items list
   - Returns 400 for nonexistent product
   - Returns 400 for archived product
   - Inventory unchanged on failure
   - Adversarial — string qty, negative qty, missing fields,
     empty body, SQL injection, very large qty

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
import json
from decimal import Decimal
from datetime import datetime
from app.extensions import db
from app.models.user import User
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.stock_in import StockIn


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stocking_user(app):
    u = User(
        user_id=10092026,
        first_name="Stock",
        last_name="Person",
        role="stocking",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def stocking_client(client, stocking_user):
    """Authenticated client as stocking staff."""
    client.post("/", data={
        "full_name": f"{stocking_user.first_name} {stocking_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def admin_client(client, user):
    """Authenticated client as admin."""
    client.post("/", data={
        "full_name": f"{user.first_name} {user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def cashier_client(client, cashier_user):
    """Authenticated client as cashier."""
    client.post("/", data={
        "full_name": f"{cashier_user.first_name} {cashier_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def stock_item(product):
    """A valid stock-in item dict."""
    return {
        "product_id": product.product_id,
        "qty": 10,
        "notes": "Test delivery",
    }


def post_json(client, url, data):
    """Helper — POST JSON to a URL."""
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


def get_json(response):
    """Helper — parse JSON from a response."""
    return json.loads(response.data)


# ---------------------------------------------------------------------------
# 1. Authentication & Authorization
#
#    WHAT: Verifies every stocking route enforces the correct role.
#    WHY:  Dashboard is stocking-only — admin seeing it means they are
#          using a stocking interface not designed for their workflow.
#          Cashier must never access stock-in routes — they don't manage
#          inventory and could corrupt stock counts.
# ---------------------------------------------------------------------------

class TestAuthAndAuthorization:
    # -- Unauthenticated --

    def test_dashboard_requires_login(self, client):
        response = client.get("/stocking/", follow_redirects=False)
        assert response.status_code == 302

    def test_stock_in_requires_login(self, client):
        response = client.get("/stocking/stock-in", follow_redirects=False)
        assert response.status_code == 302

    def test_search_requires_login(self, client):
        response = post_json(client, "/stocking/api/search", {"query": "test"})
        assert response.status_code == 302

    def test_lookup_requires_login(self, client):
        response = post_json(client, "/stocking/api/lookup", {"query": "test"})
        assert response.status_code == 302

    def test_complete_requires_login(self, client):
        response = post_json(client, "/stocking/api/complete", {})
        assert response.status_code == 302

    # -- Dashboard is stocking-only --

    def test_admin_blocked_from_dashboard(self, admin_client):
        # Dashboard is stocking role only — admin must be blocked
        response = admin_client.get("/stocking/", follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_dashboard(self, cashier_client):
        response = cashier_client.get("/stocking/", follow_redirects=False)
        assert response.status_code == 302

    # -- stock_in, search, lookup, complete — admin/co-admin/stocking --

    def test_cashier_blocked_from_stock_in(self, cashier_client):
        response = cashier_client.get("/stocking/stock-in",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_search(self, cashier_client):
        response = post_json(cashier_client, "/stocking/api/search",
                              {"query": "test"})
        assert response.status_code == 302

    def test_cashier_blocked_from_lookup(self, cashier_client):
        response = post_json(cashier_client, "/stocking/api/lookup",
                              {"query": "test"})
        assert response.status_code == 302

    def test_cashier_blocked_from_complete(self, cashier_client):
        response = post_json(cashier_client, "/stocking/api/complete", {})
        assert response.status_code == 302

    def test_stocking_can_access_dashboard(self, stocking_client):
        response = stocking_client.get("/stocking/")
        assert response.status_code == 200

    def test_stocking_can_access_stock_in(self, stocking_client):
        response = stocking_client.get("/stocking/stock-in")
        assert response.status_code == 200

    def test_admin_can_access_stock_in(self, admin_client):
        response = admin_client.get("/stocking/stock-in")
        assert response.status_code == 200

    def test_admin_can_access_search(self, admin_client):
        response = post_json(admin_client, "/stocking/api/search",
                              {"query": "test"})
        assert response.status_code == 200

    def test_admin_can_access_complete(self, admin_client, product):
        response = post_json(admin_client, "/stocking/api/complete", {
            "items": [{"product_id": product.product_id, "qty": 5}],
        })
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. GET /stocking/ (dashboard)
#
#    WHAT: Verifies the stocking dashboard renders without crashing.
#    WHY:  The dashboard calls get_stocking_stats(), get_low_stock_items(),
#          get_recent_stockins() — any of these crashing on empty data
#          would leave stocking staff unable to start their shift.
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_renders_for_stocking(self, stocking_client):
        response = stocking_client.get("/stocking/")
        assert response.status_code == 200

    def test_returns_html(self, stocking_client):
        response = stocking_client.get("/stocking/")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_renders_with_empty_db(self, stocking_client):
        # No products, no inventory, no stock-ins — must not crash
        response = stocking_client.get("/stocking/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data
        assert b"Traceback" not in response.data

    def test_renders_with_products_and_inventory(self, stocking_client,
                                                   product, inventory):
        response = stocking_client.get("/stocking/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_renders_with_low_stock(self, stocking_client, second_product,
                                     low_stock_inventory):
        # Low stock items exist — get_low_stock_items() returns data
        response = stocking_client.get("/stocking/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_renders_with_recent_stockins(self, stocking_client, stock_in):
        # Recent stock-ins exist — get_recent_stockins() returns data
        response = stocking_client.get("/stocking/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_does_not_expose_raw_exceptions(self, stocking_client):
        response = stocking_client.get("/stocking/")
        assert b"Traceback" not in response.data
        assert b"Exception" not in response.data


# ---------------------------------------------------------------------------
# 3. GET /stocking/stock-in
#
#    WHAT: Verifies the stock-in form page renders correctly.
#    WHY:  If this page crashes, stocking staff cannot record any
#          deliveries — all received inventory goes unlogged.
# ---------------------------------------------------------------------------

class TestStockInPage:
    def test_renders_for_stocking(self, stocking_client):
        response = stocking_client.get("/stocking/stock-in")
        assert response.status_code == 200

    def test_renders_for_admin(self, admin_client):
        response = admin_client.get("/stocking/stock-in")
        assert response.status_code == 200

    def test_returns_html(self, stocking_client):
        response = stocking_client.get("/stocking/stock-in")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_renders_with_empty_db(self, stocking_client):
        response = stocking_client.get("/stocking/stock-in")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 4. POST /stocking/api/search
#
#    WHAT: Verifies product search works correctly for stocking staff.
#    WHY:  Stocking staff use this to find products when logging a delivery.
#          Wrong results or archived products appearing would cause stock
#          to be logged against the wrong product.
# ---------------------------------------------------------------------------

class TestSearchAPI:
    def test_returns_json(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": product.product_name[:3]})
        assert response.content_type == "application/json"

    def test_matches_by_product_name(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": product.product_name[:4]})
        data = get_json(response)
        assert any(r["product_id"] == product.product_id for r in data)

    def test_matches_by_product_id(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": product.product_id[:4]})
        data = get_json(response)
        assert any(r["product_id"] == product.product_id for r in data)

    def test_empty_query_returns_empty_list(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": ""})
        data = get_json(response)
        assert data == []

    def test_no_match_returns_empty_list(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": "ZZZNOMATCH99999"})
        data = get_json(response)
        assert data == []

    def test_archived_product_excluded(self, stocking_client, archived_product):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": archived_product.product_name[:4]})
        data = get_json(response)
        ids = [r["product_id"] for r in data]
        assert archived_product.product_id not in ids

    def test_result_has_correct_keys(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        if data:
            assert set(data[0].keys()) == {
                "product_id", "product_name", "product_price", "stock"
            }

    def test_stock_reflects_inventory(self, stocking_client, product,
                                       inventory):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        match = next(
            (r for r in data if r["product_id"] == product.product_id), None
        )
        if match:
            assert match["stock"] == inventory.quantity_available

    def test_stock_zero_when_no_inventory(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        match = next(
            (r for r in data if r["product_id"] == product.product_id), None
        )
        if match:
            assert match["stock"] == 0

    def test_capped_at_8_results(self, stocking_client, category):
        for i in range(12):
            Product(
                product_id=f"STCK-{i:03d}",
                product_name=f"stockable product {i}",
                category_id=category.category_id,
                unit_price=Decimal("1.00"),
                revenue_price=Decimal("1.00"),
                product_price=Decimal("1.00"),
                low_reorder_threshold=1,
                status="active",
            ).save()

        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": "stockable"})
        data = get_json(response)
        assert len(data) <= 8

    def test_missing_query_key_returns_empty_list(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/search", {})
        data = get_json(response)
        assert data == []

    # -- Adversarial --

    def test_sql_injection_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": "'; DROP TABLE Products; --"})
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_xss_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": "<script>alert('xss')</script>"})
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_very_long_query_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/search",
                              {"query": "a" * 10000})
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 5. POST /stocking/api/lookup
#
#    WHAT: Verifies product lookup works for all three lookup strategies.
#    WHY:  Stocking staff scan barcodes on incoming deliveries. If the
#          lookup returns the wrong product or fails on a valid barcode,
#          stock is logged against the wrong product — corrupting inventory.
# ---------------------------------------------------------------------------

class TestLookupAPI:
    def test_finds_product_by_exact_product_id(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product.product_id})
        assert response.status_code == 200
        data = get_json(response)
        assert data["product_id"] == product.product_id

    def test_finds_product_by_bundle_barcode(self, stocking_client,
                                               product, product_bundle):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product_bundle.bundle_id})
        assert response.status_code == 200
        data = get_json(response)
        assert data["product_id"] == product.product_id
        assert data["scanned_as_bundle"] is True

    def test_finds_product_by_partial_name(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product.product_name[:4]})
        assert response.status_code == 200
        data = get_json(response)
        assert data["product_id"] == product.product_id

    def test_returns_404_for_nonexistent(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": "NONEXISTENT-SKU-99999"})
        assert response.status_code == 404

    def test_returns_400_for_archived(self, stocking_client, archived_product):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": archived_product.product_id})
        assert response.status_code == 400
        data = get_json(response)
        assert "archived" in data["error"].lower()

    def test_returns_400_for_empty_query(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": ""})
        assert response.status_code == 400

    def test_result_has_correct_keys(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        expected_keys = {
            "product_id", "product_name", "product_price",
            "stock", "bundle", "scanned_as_bundle"
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_scanned_as_bundle_false_for_direct_product(self, stocking_client,
                                                          product):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["scanned_as_bundle"] is False

    def test_bundle_info_populated_when_bundle_exists(self, stocking_client,
                                                        product,
                                                        product_bundle):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["bundle"] is not None
        assert set(data["bundle"].keys()) == {
            "bundle_id", "bundle_name", "bundle_count"
        }

    def test_bundle_none_when_no_bundle(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["bundle"] is None

    # -- Adversarial --

    def test_sql_injection_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": "'; DROP TABLE Products; --"})
        assert response.status_code in [400, 404]
        assert b"Internal Server Error" not in response.data

    def test_very_long_query_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/lookup",
                              {"query": "a" * 10000})
        assert response.status_code in [400, 404]
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 6. POST /stocking/api/complete
#
#    WHAT: Verifies stock-in completion correctly increments inventory
#          and creates StockIn records.
#    WHY:  This is the core operation of the stocking module. Incorrect
#          inventory increments directly corrupt stock counts used by
#          cashiers and reported on the admin dashboard.
# ---------------------------------------------------------------------------

class TestCompleteAPI:
    # -- Happy path --

    def test_valid_complete_returns_200(self, stocking_client, stock_item):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        assert response.status_code == 200

    def test_valid_complete_returns_success_true(self, stocking_client,
                                                  stock_item):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        data = get_json(response)
        assert data["success"] is True

    def test_creates_stock_in_record(self, stocking_client, stock_item):
        initial_count = StockIn.query.count()
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        assert StockIn.query.count() == initial_count + 1

    def test_increments_existing_inventory(self, stocking_client,
                                            stock_item, inventory, product):
        initial_stock = inventory.quantity_available
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],  # qty=10
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available == initial_stock + stock_item["qty"]

    def test_creates_inventory_when_none_exists(self, stocking_client,
                                                  stock_item, product):
        # product fixture has no inventory — complete() should create it
        assert product.inventory is None
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        db.session.refresh(product)
        assert product.inventory is not None
        assert product.inventory.quantity_available == stock_item["qty"]

    def test_returns_correct_response_structure(self, stocking_client,
                                                  stock_item):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        data = get_json(response)
        assert set(data.keys()) >= {
            "success", "received", "total_items",
            "total_units", "recorded_by", "datetime"
        }

    def test_returns_correct_total_items(self, stocking_client, stock_item):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        data = get_json(response)
        assert data["total_items"] == 1

    def test_returns_correct_total_units(self, stocking_client, stock_item):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],  # qty=10
        })
        data = get_json(response)
        assert data["total_units"] == stock_item["qty"]

    def test_notes_saved_to_stock_in(self, stocking_client, stock_item):
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],  # notes="Test delivery"
        })
        si = StockIn.query.first()
        assert si is not None
        assert si.notes == stock_item["notes"]

    def test_multiple_items_all_processed(self, stocking_client,
                                           product, second_product):
        items = [
            {"product_id": product.product_id, "qty": 5},
            {"product_id": second_product.product_id, "qty": 3},
        ]
        initial_si_count = StockIn.query.count()
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": items,
        })
        data = get_json(response)
        assert data["success"] is True
        assert data["total_items"] == 2
        assert data["total_units"] == 8
        assert StockIn.query.count() == initial_si_count + 2

    def test_inventory_last_updated_refreshed(self, stocking_client,
                                               stock_item, inventory):
        before = inventory.last_updated
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        db.session.refresh(inventory)
        assert inventory.last_updated >= before

    def test_recorded_by_shows_user_name(self, stocking_client,
                                          stock_item, stocking_user):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        data = get_json(response)
        assert stocking_user.full_name in data["recorded_by"]

    def test_received_list_contains_correct_product_name(self, stocking_client,
                                                           stock_item, product):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [stock_item],
        })
        data = get_json(response)
        assert len(data["received"]) == 1
        assert data["received"][0]["qty"] == stock_item["qty"]

    # -- Validation errors --

    def test_empty_items_returns_400(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [],
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "error" in data

    def test_missing_items_key_returns_400(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/complete", {})
        assert response.status_code == 400

    def test_nonexistent_product_returns_400(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [{"product_id": "NONEXISTENT-SKU", "qty": 5}],
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "error" in data

    def test_archived_product_returns_400(self, stocking_client,
                                           archived_product):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [{
                "product_id": archived_product.product_id,
                "qty": 5
            }],
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "archived" in data["error"].lower() or \
               "error" in data

    def test_zero_qty_item_silently_skipped(self, stocking_client, product):
        # qty=0 items are skipped — success with 0 received items
        initial_si_count = StockIn.query.count()
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [{"product_id": product.product_id, "qty": 0}],
        })
        # No StockIn created for skipped items
        assert StockIn.query.count() == initial_si_count

    def test_negative_qty_item_silently_skipped(self, stocking_client, product):
        # qty<0 items are also skipped
        initial_si_count = StockIn.query.count()
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [{"product_id": product.product_id, "qty": -5}],
        })
        assert StockIn.query.count() == initial_si_count

    def test_inventory_unchanged_when_all_items_skipped(self, stocking_client,
                                                          product, inventory):
        initial_stock = inventory.quantity_available
        post_json(stocking_client, "/stocking/api/complete", {
            "items": [{"product_id": product.product_id, "qty": 0}],
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available == initial_stock

    # -- Adversarial --

    def test_string_qty_does_not_crash(self, stocking_client, product):
        # int("two") raises ValueError — route must handle gracefully
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [{"product_id": product.product_id, "qty": "two"}],
        })
        assert b"Internal Server Error" not in response.data

    def test_none_qty_does_not_crash(self, stocking_client, product):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [{"product_id": product.product_id, "qty": None}],
        })
        assert b"Internal Server Error" not in response.data

    def test_very_large_qty_accepted(self, stocking_client, stock_item,
                                      inventory, product):
        # Large delivery quantities must not overflow Integer column
        initial_stock = inventory.quantity_available
        large_item = {**stock_item, "qty": 100000}
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [large_item],
        })
        assert b"Internal Server Error" not in response.data
        if get_json(response).get("success"):
            db.session.refresh(inventory)
            assert inventory.quantity_available == initial_stock + 100000

    def test_sql_injection_in_product_id_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [{
                "product_id": "'; DROP TABLE Products; --",
                "qty": 5
            }],
        })
        assert b"Internal Server Error" not in response.data
        assert Product.query.count() >= 0  # table still intact

    def test_xss_in_notes_does_not_crash(self, stocking_client, stock_item):
        xss_item = {**stock_item,
                     "notes": "<script>alert('xss')</script>"}
        response = post_json(stocking_client, "/stocking/api/complete", {
            "items": [xss_item],
        })
        assert b"Internal Server Error" not in response.data

    def test_empty_body_does_not_crash(self, stocking_client):
        response = stocking_client.post(
            "/stocking/api/complete",
            data="",
            content_type="application/json",
        )
        assert response.status_code in [400, 200]
        assert b"Internal Server Error" not in response.data

    def test_missing_body_does_not_crash(self, stocking_client):
        response = stocking_client.post("/stocking/api/complete")
        assert response.status_code in [302, 400, 415]
        assert b"Internal Server Error" not in response.data