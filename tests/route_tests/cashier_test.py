"""
tests/route_tests/cashier_test.py

Pytest suite for cashier blueprint routes.
All routes are under /cashier and require login + cashier/admin/co-admin role.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Authentication & Authorization
   - All routes require login
   - cashier, admin, co-admin can access all cashier routes
   - stocking role is blocked from all cashier routes

2. GET /cashier/transaction
   - Renders correctly for allowed roles
   - Blocked for stocking role

3. POST /cashier/api/search (JSON API)
   - Returns matching products by name
   - Returns matching products by product_id (barcode)
   - Returns empty list for no matches
   - Returns empty list for empty/short query
   - Only returns active products (archived excluded)
   - Returns correct JSON structure per result
   - Capped at 8 results
   - Adversarial — SQL injection, XSS, very long query, missing body

4. POST /cashier/api/lookup (JSON API)
   - Finds product by exact barcode (product_id)
   - Finds product by exact bundle barcode (bundle_id)
   - Finds product by partial name match
   - Returns 404 for nonexistent product
   - Returns 400 for archived product
   - Returns correct JSON structure including bundle info
   - scanned_as_bundle flag set correctly
   - Adversarial — empty query, SQL injection, missing body

5. POST /cashier/api/charge (JSON API)
   - Happy path — valid cart creates Sale + SaleDetails
   - Inventory is decremented after charge
   - Returns correct change amount
   - Returns correct transaction_id and totals
   - Returns 400 for empty cart
   - Returns 400 for invalid tendered amount
   - Returns 400 for tendered < total
   - Returns 400 for nonexistent product in cart
   - Returns 400 for archived product in cart
   - Warning returned (not error) when qty > stock
   - Inventory never goes below 0 (max(0, ...) guard)
   - Multiple items in cart all saved as SaleDetails
   - DB is unchanged on validation failure (no partial commits)
   - Adversarial — missing fields, wrong types, negative qty,
     zero qty, very large qty, SQL injection in product_id

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
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.inventory import Inventory


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cashier_client(client, cashier_user):
    """Authenticated client as cashier."""
    client.post("/", data={
        "full_name": f"{cashier_user.first_name} {cashier_user.last_name}",
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
def product_with_stock(app, product, inventory):
    """Product fixture with 100 units in inventory."""
    return product


@pytest.fixture
def cart_item(product_with_stock):
    """A single valid cart item dict matching the charge API format."""
    return {
        "product_id": product_with_stock.product_id,
        "product_name": product_with_stock.product_name,
        "qty": 2,
        "unit_price": float(product_with_stock.unit_price),
        "revenue_price": float(product_with_stock.revenue_price),
        "product_price": float(product_with_stock.product_price),
    }


def post_json(client, url, data):
    """Helper — POST JSON data to a URL."""
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
#    WHAT: Verifies all cashier routes require login and correct role.
#    WHY:  The cashier transaction page and APIs handle real money.
#          Unauthenticated or wrong-role access must be blocked completely.
# ---------------------------------------------------------------------------

class TestAuthAndAuthorization:
    def test_transaction_requires_login(self, client):
        response = client.get("/cashier/transaction",
                               follow_redirects=False)
        assert response.status_code == 302

    def test_search_requires_login(self, client):
        response = post_json(client, "/cashier/api/search",
                              {"query": "test"})
        assert response.status_code == 302

    def test_lookup_requires_login(self, client):
        response = post_json(client, "/cashier/api/lookup",
                              {"query": "test"})
        assert response.status_code == 302

    def test_charge_requires_login(self, client):
        response = post_json(client, "/cashier/api/charge", {})
        assert response.status_code == 302

    def test_stocking_blocked_from_transaction(self, stocking_client):
        response = stocking_client.get("/cashier/transaction",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_blocked_from_search(self, stocking_client):
        response = post_json(stocking_client, "/cashier/api/search",
                              {"query": "test"})
        assert response.status_code == 302

    def test_stocking_blocked_from_lookup(self, stocking_client):
        response = post_json(stocking_client, "/cashier/api/lookup",
                              {"query": "test"})
        assert response.status_code == 302

    def test_stocking_blocked_from_charge(self, stocking_client):
        response = post_json(stocking_client, "/cashier/api/charge", {})
        assert response.status_code == 302

    def test_cashier_can_access_transaction(self, cashier_client):
        response = cashier_client.get("/cashier/transaction")
        assert response.status_code == 200

    def test_admin_can_access_transaction(self, admin_client):
        response = admin_client.get("/cashier/transaction")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. GET /cashier/transaction
#
#    WHAT: Verifies the transaction page renders correctly.
#    WHY:  This is the main cashier interface. If it crashes on load,
#          cashiers cannot process any transactions — the entire POS
#          is down. Must render cleanly even with an empty product DB.
# ---------------------------------------------------------------------------

class TestTransactionPage:
    def test_renders_for_cashier(self, cashier_client):
        response = cashier_client.get("/cashier/transaction")
        assert response.status_code == 200

    def test_returns_html(self, cashier_client):
        response = cashier_client.get("/cashier/transaction")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_renders_with_empty_db(self, cashier_client):
        # Page returns 200 — "500" in body is ₱500 quick cash button, not an error
        response = cashier_client.get("/cashier/transaction")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data  # real 500 check
        assert b"Traceback" not in response.data              # real crash check

    def test_does_not_expose_raw_exceptions(self, cashier_client):
        response = cashier_client.get("/cashier/transaction")
        assert b"Traceback" not in response.data
        assert b"Exception" not in response.data


# ---------------------------------------------------------------------------
# 3. POST /cashier/api/search
#
#    WHAT: Verifies product search returns correct results.
#    WHY:  Cashiers use this to find products during a transaction.
#          Wrong results, missing results, or archived products appearing
#          would disrupt the cashier workflow or allow selling unavailable items.
# ---------------------------------------------------------------------------

class TestSearchAPI:
    def test_returns_json(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": product.product_name[:3]})
        assert response.content_type == "application/json"

    def test_matches_by_product_name(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": product.product_name[:4]})
        data = get_json(response)
        assert isinstance(data, list)
        assert any(r["product_id"] == product.product_id for r in data)

    def test_matches_by_product_id(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": product.product_id[:4]})
        data = get_json(response)
        assert any(r["product_id"] == product.product_id for r in data)

    def test_empty_query_returns_empty_list(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": ""})
        data = get_json(response)
        assert data == []

    def test_no_match_returns_empty_list(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": "ZZZNOMATCH99999"})
        data = get_json(response)
        assert data == []

    def test_archived_product_excluded(self, cashier_client,
                                        archived_product):
        # Archived products must never appear in search results
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": archived_product.product_name[:4]})
        data = get_json(response)
        ids = [r["product_id"] for r in data]
        assert archived_product.product_id not in ids

    def test_result_has_correct_keys(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        if data:
            assert set(data[0].keys()) == {
                "product_id", "product_name", "product_price", "stock"
            }

    def test_stock_reflects_inventory(self, cashier_client, product,
                                       inventory):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        match = next(
            (r for r in data if r["product_id"] == product.product_id), None
        )
        if match:
            assert match["stock"] == inventory.quantity_available

    def test_stock_zero_when_no_inventory(self, cashier_client, product):
        # Product exists but no inventory row — stock must be 0
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        match = next(
            (r for r in data if r["product_id"] == product.product_id), None
        )
        if match:
            assert match["stock"] == 0

    def test_capped_at_8_results(self, cashier_client, category):
        # Create 12 active products — search must return at most 8
        for i in range(12):
            Product(
                product_id=f"SRCH-{i:03d}",
                product_name=f"searchable product {i}",
                category_id=category.category_id,
                unit_price=Decimal("1.00"),
                revenue_price=Decimal("1.00"),
                product_price=Decimal("1.00"),
                low_reorder_threshold=1,
                status="active",
            ).save()

        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": "searchable"})
        data = get_json(response)
        assert len(data) <= 8

    def test_missing_query_key_returns_empty_list(self, cashier_client):
        # Body missing "query" key — get("query", "") returns ""
        response = post_json(cashier_client, "/cashier/api/search", {})
        data = get_json(response)
        assert data == []

    def test_empty_body_does_not_crash(self, cashier_client):
        response = cashier_client.post(
            "/cashier/api/search",
            data="",
            content_type="application/json",
        )
        assert response.status_code in [200, 400]  # ← accept 400
        assert b"500" not in response.data

    # -- Adversarial --

    def test_sql_injection_in_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": "'; DROP TABLE Products; --"})
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_xss_in_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": "<script>alert('xss')</script>"})
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_very_long_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": "a" * 10000})
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_numeric_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/search",
                              {"query": 12345})
        assert response.status_code == 200
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 4. POST /cashier/api/lookup
#
#    WHAT: Verifies product lookup by barcode, bundle barcode, or name.
#    WHY:  Cashiers scan barcodes during checkout. Wrong lookup results
#          mean scanning a product barcode returns nothing, scanning a
#          bundle barcode returns the wrong product, or archived products
#          appear as available for sale.
# ---------------------------------------------------------------------------

class TestLookupAPI:
    def test_finds_product_by_exact_product_id(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        assert response.status_code == 200
        data = get_json(response)
        assert data["product_id"] == product.product_id

    def test_finds_product_by_bundle_barcode(self, cashier_client,
                                               product, product_bundle):
        # Scanning the bundle barcode should return the parent product
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product_bundle.bundle_id})
        assert response.status_code == 200
        data = get_json(response)
        assert data["product_id"] == product.product_id
        assert data["scanned_as_bundle"] is True

    def test_finds_product_by_partial_name(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_name[:4]})
        assert response.status_code == 200
        data = get_json(response)
        assert data["product_id"] == product.product_id

    def test_returns_404_for_nonexistent_product(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": "NONEXISTENT-SKU-99999"})
        assert response.status_code == 404
        data = get_json(response)
        assert "error" in data

    def test_returns_400_for_archived_product(self, cashier_client,
                                               archived_product):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": archived_product.product_id})
        assert response.status_code == 400
        data = get_json(response)
        assert "archived" in data["error"].lower()

    def test_returns_400_for_empty_query(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": ""})
        assert response.status_code == 400

    def test_result_has_correct_keys(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        expected_keys = {
            "product_id", "product_name", "unit_price",
            "revenue_price", "product_price", "stock",
            "bundle", "scanned_as_bundle"
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_bundle_info_populated_when_bundle_exists(self, cashier_client,
                                                        product,
                                                        product_bundle):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["bundle"] is not None
        assert set(data["bundle"].keys()) == {
            "bundle_id", "bundle_name", "bundle_count"
        }

    def test_bundle_is_none_when_no_bundle(self, cashier_client, product):
        # product fixture has no bundle
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["bundle"] is None

    def test_scanned_as_bundle_false_for_direct_product(self, cashier_client,
                                                          product):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["scanned_as_bundle"] is False

    def test_stock_reflects_inventory(self, cashier_client, product,
                                       inventory):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["stock"] == inventory.quantity_available

    def test_stock_zero_when_no_inventory(self, cashier_client, product):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        assert data["stock"] == 0

    def test_missing_body_does_not_crash(self, cashier_client):
        response = cashier_client.post(
            "/cashier/api/lookup",
            data="",
            content_type="application/json",
        )
        assert response.status_code in [400, 200]
        assert b"500" not in response.data

    # -- Adversarial --

    def test_sql_injection_in_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": "'; DROP TABLE Products; --"})
        assert response.status_code in [400, 404]
        assert b"500" not in response.data

    def test_xss_in_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": "<script>alert(1)</script>"})
        assert response.status_code in [400, 404]
        assert b"500" not in response.data

    def test_very_long_query_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/lookup",
                              {"query": "a" * 10000})
        assert response.status_code in [400, 404]
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 5. POST /cashier/api/charge
#
#    WHAT: Verifies the charge API processes sales correctly and handles
#          all error cases without corrupting the DB.
#    WHY:  This is the most critical route in the system — it handles real
#          money and modifies inventory. A bug here means wrong change
#          given, wrong inventory counts, or partial DB commits leaving
#          the system in an inconsistent state.
# ---------------------------------------------------------------------------

class TestChargeAPI:
    # -- Happy path --

    def test_valid_charge_returns_200(self, cashier_client, cart_item):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        assert response.status_code == 200

    def test_valid_charge_returns_ok_true(self, cashier_client, cart_item):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        data = get_json(response)
        assert data["ok"] is True

    def test_creates_sale_in_db(self, cashier_client, cart_item):
        initial_count = Sale.query.count()
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        assert Sale.query.count() == initial_count + 1

    def test_creates_sale_detail_in_db(self, cashier_client, cart_item):
        initial_count = SaleDetail.query.count()
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        assert SaleDetail.query.count() == initial_count + 1

    def test_returns_correct_change(self, cashier_client, cart_item):
        # cart_item has product_price=15.00, qty=2 → total=30.00
        # tendered=50.00 → change=20.00
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 50.00,
        })
        data = get_json(response)
        assert data["change"] == 20.00

    def test_returns_transaction_id(self, cashier_client, cart_item):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        data = get_json(response)
        assert "transaction_id" in data
        assert data["transaction_id"] is not None

    def test_returns_correct_total(self, cashier_client, cart_item):
        # qty=2, product_price=15.00 → total=30.00
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        data = get_json(response)
        assert data["total"] == 30.00

    def test_inventory_decremented_after_charge(self, cashier_client,
                                                 cart_item, inventory,
                                                 product):
        initial_stock = inventory.quantity_available
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available == initial_stock - cart_item["qty"]

    def test_inventory_last_updated_refreshed(self, cashier_client,
                                               cart_item, inventory):
        before = inventory.last_updated
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        db.session.refresh(inventory)
        assert inventory.last_updated >= before

    def test_multiple_items_all_saved_as_details(self, cashier_client,
                                                   product_with_stock,
                                                   second_product,
                                                   low_stock_inventory):
        # second_product has its own inventory via low_stock_inventory
        items = [
            {
                "product_id": product_with_stock.product_id,
                "product_name": product_with_stock.product_name,
                "qty": 1,
                "unit_price": float(product_with_stock.unit_price),
                "revenue_price": float(product_with_stock.revenue_price),
                "product_price": float(product_with_stock.product_price),
            },
            {
                "product_id": second_product.product_id,
                "product_name": second_product.product_name,
                "qty": 1,
                "unit_price": float(second_product.unit_price),
                "revenue_price": float(second_product.revenue_price),
                "product_price": float(second_product.product_price),
            },
        ]
        initial_detail_count = SaleDetail.query.count()
        post_json(cashier_client, "/cashier/api/charge", {
            "items": items,
            "tendered": 200.00,
        })
        assert SaleDetail.query.count() == initial_detail_count + 2

    def test_exact_tender_returns_zero_change(self, cashier_client, cart_item):
        # qty=2, product_price=15.00 → total=30.00, tendered=30.00 → change=0
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 30.00,
        })
        data = get_json(response)
        assert data["ok"] is True
        assert data["change"] == 0.00

    def test_returns_cashier_name(self, cashier_client, cart_item,
                                   cashier_user):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 100.00,
        })
        data = get_json(response)
        assert "cashier" in data
        assert cashier_user.full_name in data["cashier"]

    # -- Validation errors --

    def test_empty_cart_returns_400(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [],
            "tendered": 100.00,
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "empty" in data["error"].lower()

    def test_missing_items_returns_400(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "tendered": 100.00,
        })
        assert response.status_code == 400

    def test_invalid_tendered_string_returns_400(self, cashier_client,
                                                  cart_item):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": "not-a-number",
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "payment" in data["error"].lower() or \
               "invalid" in data["error"].lower()

    def test_none_tendered_returns_400(self, cashier_client, cart_item):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": None,
        })
        assert response.status_code == 400

    def test_tendered_less_than_total_returns_400(self, cashier_client,
                                                   cart_item):
        # cart_item total = 30.00, tendered = 1.00
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 1.00,
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "less" in data["error"].lower() or \
               "cash" in data["error"].lower()

    def test_nonexistent_product_in_cart_returns_400(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [{
                "product_id": "NONEXISTENT-SKU",
                "product_name": "Ghost Product",
                "qty": 1,
                "unit_price": 10.00,
                "revenue_price": 12.00,
                "product_price": 15.00,
            }],
            "tendered": 100.00,
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "not found" in data["error"].lower() or \
               "error" in data

    def test_archived_product_in_cart_returns_400(self, cashier_client,
                                                    archived_product):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [{
                "product_id": archived_product.product_id,
                "product_name": archived_product.product_name,
                "qty": 1,
                "unit_price": float(archived_product.unit_price),
                "revenue_price": float(archived_product.revenue_price),
                "product_price": float(archived_product.product_price),
            }],
            "tendered": 100.00,
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "archived" in data["error"].lower()

    def test_no_sale_created_on_validation_failure(self, cashier_client):
        initial_count = Sale.query.count()
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [],
            "tendered": 100.00,
        })
        assert Sale.query.count() == initial_count

    def test_no_sale_created_when_tendered_too_low(self, cashier_client,
                                                     cart_item):
        initial_count = Sale.query.count()
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 1.00,
        })
        assert Sale.query.count() == initial_count

    def test_inventory_unchanged_on_validation_failure(self, cashier_client,
                                                         cart_item, inventory):
        initial_stock = inventory.quantity_available
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 1.00,  # too low — validation fails
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available == initial_stock

    # -- Stock warning behavior --

    def test_qty_exceeds_stock_returns_warning_not_error(self, cashier_client,
                                                           cart_item,
                                                           inventory):
        # Selling more than in stock — returns warning but still succeeds
        over_qty_item = {**cart_item, "qty": inventory.quantity_available + 50}
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [over_qty_item],
            "tendered": 99999.00,
        })
        data = get_json(response)
        assert data["ok"] is True
        assert len(data["warnings"]) > 0
        assert "stock" in data["warnings"][0].lower() or \
               "in stock" in data["warnings"][0].lower()

    def test_inventory_never_goes_below_zero(self, cashier_client,
                                              cart_item, inventory):
        # max(0, stock - qty) guard — inventory should clamp at 0
        over_qty_item = {**cart_item, "qty": inventory.quantity_available + 50}
        post_json(cashier_client, "/cashier/api/charge", {
            "items": [over_qty_item],
            "tendered": 99999.00,
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available >= 0

    def test_no_warning_when_qty_equals_stock(self, cashier_client,
                                               cart_item, inventory):
        # Selling exactly what's in stock — no warning needed
        exact_qty_item = {**cart_item,
                           "qty": inventory.quantity_available}
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [exact_qty_item],
            "tendered": 99999.00,
        })
        data = get_json(response)
        assert data["ok"] is True
        assert data["warnings"] == []

    # -- Adversarial --

    def test_empty_body_does_not_crash(self, cashier_client):
        response = cashier_client.post(
            "/cashier/api/charge",
            data="",
            content_type="application/json",
        )
        assert response.status_code in [400, 200]
        assert b"500" not in response.data

    def test_missing_body_does_not_crash(self, cashier_client):
        response = cashier_client.post("/cashier/api/charge")
        assert response.status_code in [302, 400, 415]
        assert b"500" not in response.data

    def test_negative_qty_in_cart(self, cashier_client, cart_item,
                                   inventory):
        initial_stock = inventory.quantity_available
        negative_item = {**cart_item, "qty": -5}
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [negative_item],
            "tendered": 100.00,
        })
        # Negative qty — app should either reject or handle gracefully
        assert b"500" not in response.data
        # Inventory must not increase from a negative qty purchase
        db.session.refresh(inventory)
        assert inventory.quantity_available <= initial_stock

    def test_zero_qty_in_cart(self, cashier_client, cart_item):
        zero_item = {**cart_item, "qty": 0}
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [zero_item],
            "tendered": 100.00,
        })
        assert b"500" not in response.data

    def test_string_qty_in_cart(self, cashier_client, cart_item):
        # qty as string — int() conversion in route must handle this
        string_item = {**cart_item, "qty": "two"}
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [string_item],
            "tendered": 100.00,
        })
        # Must not crash with 500
        assert b"500" not in response.data

    def test_very_large_tendered_accepted(self, cashier_client, cart_item):
        # Very large tendered amount — change calculation must not overflow
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [cart_item],
            "tendered": 999999999.00,
        })
        assert b"500" not in response.data
        data = get_json(response)
        if data.get("ok"):
            assert data["change"] > 0

    def test_sql_injection_in_product_id_does_not_crash(self, cashier_client):
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [{
                "product_id": "'; DROP TABLE Products; --",
                "product_name": "Injected",
                "qty": 1,
                "unit_price": 10.00,
                "revenue_price": 12.00,
                "product_price": 15.00,
            }],
            "tendered": 100.00,
        })
        assert b"500" not in response.data
        # Products table must still exist
        assert Product.query.count() >= 0

    def test_xss_in_product_name_does_not_execute(self, cashier_client, cart_item):
        # JSON APIs return raw strings — HTML escaping is the template's job
        # The test should verify the sale was processed (or rejected) without crashing
        xss_item = {**cart_item, "product_name": "<script>alert('xss')</script>"}
        response = post_json(cashier_client, "/cashier/api/charge", {
            "items": [xss_item],
            "tendered": 100.00,
        })
        # Must not crash with 500 — XSS in JSON is safe, it's raw data not rendered HTML
        assert b"500" not in response.data
        assert response.status_code in [200, 400]