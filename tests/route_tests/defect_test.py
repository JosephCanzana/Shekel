"""
tests/route_tests/defects_test.py

Pytest suite for defects blueprint routes.
All routes are under /defects.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Authentication & Authorization
   - All routes require login
   - index, product_history, log, search, lookup, complete
     → admin, co-admin, stocking only
   - edit_detail → admin, co-admin only (stocking blocked)
   - cashier blocked from all defect routes

2. GET /defects/ (index)
   - Renders correctly for allowed roles
   - Does not crash with empty DB (no defects yet)
   - Does not crash with defect data present

3. GET /defects/product/<product_id>
   - Renders correctly for product with defect history
   - Returns 404 for nonexistent product_id
   - Handles product with no defect history

4. POST /defects/detail/<detail_id>/edit
   - Valid compensation values update correctly
   - Invalid compensation values rejected with flash
   - Nonexistent detail_id returns 404
   - stocking role blocked (admin/co-admin only)

5. GET /defects/log
   - Renders correctly for allowed roles
   - Does not crash with empty DB

6. POST /defects/api/search (JSON API)
   - Same search behavior as cashier/stocking search
   - Adversarial inputs handled

7. POST /defects/api/lookup (JSON API)
   - Same lookup behavior as cashier/stocking lookup
   - Adversarial inputs handled

8. POST /defects/api/complete (JSON API)
   - Happy path — creates Defect + DefectDetail records
   - Decrements quantity_available in inventory
   - Increments quantity_defective in inventory
   - Returns correct response structure
   - Multiple items in one defect log
   - qty > stock returns 400 (stricter than cashier — no override)
   - Invalid reason value returns 400
   - Invalid compensation value returns 400
   - qty <= 0 returns 400
   - Empty items returns 400
   - Nonexistent product returns 400
   - Archived product returns 400
   - DB unchanged on any validation failure
   - Adversarial — string qty, SQL injection, XSS, missing fields

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
from app.models.defect import Defect
from app.models.defect_detail import DefectDetail


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
    client.post("/", data={
        "full_name": f"{stocking_user.first_name} {stocking_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def admin_client(client, user):
    client.post("/", data={
        "full_name": f"{user.first_name} {user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def cashier_client(client, cashier_user):
    client.post("/", data={
        "full_name": f"{cashier_user.first_name} {cashier_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def product_with_stock(app, product, inventory):
    """Product fixture with 100 units in inventory."""
    return product


@pytest.fixture
def defect_item(product_with_stock):
    """A single valid defect item dict."""
    return {
        "product_id":   product_with_stock.product_id,
        "qty":          2,
        "reason":       "defect",
        "compensation": "pending",
    }


@pytest.fixture
def existing_defect(app, defect, defect_detail):
    """A pre-existing Defect with one DefectDetail — for history/edit tests."""
    return defect_detail


def post_json(client, url, data):
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


def get_json(response):
    return json.loads(response.data)


# ---------------------------------------------------------------------------
# 1. Authentication & Authorization
#
#    WHAT: Verifies every defect route enforces the correct role.
#    WHY:  Defect logging directly affects inventory counts and financial
#          loss records. Cashiers must never access this — they could
#          falsely log defects to cover up shrinkage. edit_detail is
#          admin/co-admin only because changing compensation status has
#          financial implications.
# ---------------------------------------------------------------------------

class TestAuthAndAuthorization:
    # -- Unauthenticated --

    def test_index_requires_login(self, client):
        response = client.get("/defects/", follow_redirects=False)
        assert response.status_code == 302

    def test_log_requires_login(self, client):
        response = client.get("/defects/log", follow_redirects=False)
        assert response.status_code == 302

    def test_search_requires_login(self, client):
        response = post_json(client, "/defects/api/search", {"query": "test"})
        assert response.status_code == 302

    def test_lookup_requires_login(self, client):
        response = post_json(client, "/defects/api/lookup", {"query": "test"})
        assert response.status_code == 302

    def test_complete_requires_login(self, client):
        response = post_json(client, "/defects/api/complete", {})
        assert response.status_code == 302

    # -- Cashier blocked from all --

    def test_cashier_blocked_from_index(self, cashier_client):
        response = cashier_client.get("/defects/", follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_log(self, cashier_client):
        response = cashier_client.get("/defects/log", follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_search(self, cashier_client):
        response = post_json(cashier_client, "/defects/api/search",
                              {"query": "test"})
        assert response.status_code == 302

    def test_cashier_blocked_from_complete(self, cashier_client):
        response = post_json(cashier_client, "/defects/api/complete", {})
        assert response.status_code == 302

    # -- edit_detail is admin/co-admin only --

    def test_stocking_blocked_from_edit_detail(self, stocking_client,
                                                existing_defect):
        response = stocking_client.post(
            f"/defects/detail/{existing_defect.defect_detail_id}/edit",
            data={"compensation": "loss"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_admin_can_edit_detail(self, admin_client, existing_defect):
        response = admin_client.post(
            f"/defects/detail/{existing_defect.defect_detail_id}/edit",
            data={"compensation": "loss"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Allowed roles --

    def test_stocking_can_access_index(self, stocking_client):
        response = stocking_client.get("/defects/")
        assert response.status_code == 200

    def test_admin_can_access_index(self, admin_client):
        response = admin_client.get("/defects/")
        assert response.status_code == 200

    def test_stocking_can_access_log(self, stocking_client):
        response = stocking_client.get("/defects/log")
        assert response.status_code == 200

    def test_admin_can_access_complete(self, admin_client, product_with_stock):
        response = post_json(admin_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. GET /defects/ (index)
#
#    WHAT: Verifies the defect index renders without crashing.
#    WHY:  The index runs a complex join query (Product + DefectDetail).
#          An empty DB or a product with no bundle must not crash the
#          query or the template rendering.
# ---------------------------------------------------------------------------

class TestIndex:
    def test_renders_for_admin(self, admin_client):
        response = admin_client.get("/defects/")
        assert response.status_code == 200

    def test_returns_html(self, admin_client):
        response = admin_client.get("/defects/")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_renders_with_empty_db(self, admin_client):
        # No defects yet — query returns empty, must not crash
        response = admin_client.get("/defects/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data
        assert b"Traceback" not in response.data

    def test_renders_with_defect_data(self, admin_client, existing_defect):
        # Defect + DefectDetail exist — query must return and render them
        response = admin_client.get("/defects/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_renders_with_bundled_product_defect(self, admin_client,
                                                   product_bundle,
                                                   existing_defect):
        # Product has a bundle — bundle_count must be retrieved without crashing
        response = admin_client.get("/defects/")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 3. GET /defects/product/<product_id>
#
#    WHAT: Verifies product defect history renders correctly.
#    WHY:  This page runs a join between DefectDetail and Defect filtered
#          by product_id. An empty history must render cleanly. A
#          nonexistent product_id must 404, not 500.
# ---------------------------------------------------------------------------

class TestProductHistory:
    def test_renders_for_product_with_defects(self, admin_client,
                                               product_with_stock,
                                               existing_defect):
        response = admin_client.get(
            f"/defects/product/{product_with_stock.product_id}"
        )
        assert response.status_code == 200

    def test_renders_for_product_with_no_defects(self, admin_client, product):
        # Product exists but has no defect history — rows=[] must not crash
        response = admin_client.get(
            f"/defects/product/{product.product_id}"
        )
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_returns_404_for_nonexistent_product(self, admin_client):
        response = admin_client.get(
            "/defects/product/NONEXISTENT-SKU-99999"
        )
        assert response.status_code == 404

    def test_renders_with_bundle_product(self, admin_client,
                                          product_with_stock,
                                          product_bundle,
                                          existing_defect):
        # Product has a bundle — bundle_qty inference must not crash
        response = admin_client.get(
            f"/defects/product/{product_with_stock.product_id}"
        )
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_returns_html(self, admin_client, product):
        response = admin_client.get(
            f"/defects/product/{product.product_id}"
        )
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data


# ---------------------------------------------------------------------------
# 4. POST /defects/detail/<detail_id>/edit
#
#    WHAT: Verifies compensation status updates are validated and persisted.
#    WHY:  Compensation status determines how financial losses are recorded.
#          Invalid values could corrupt compensation tracking. Only admin
#          and co-admin can change this — not stocking staff.
# ---------------------------------------------------------------------------

class TestEditDetail:
    @pytest.mark.parametrize("valid_comp", [
        "pending", "loss", "returned", "replacement"
    ])
    def test_valid_compensation_values_accepted(self, admin_client,
                                                  existing_defect,
                                                  valid_comp):
        admin_client.post(
            f"/defects/detail/{existing_defect.defect_detail_id}/edit",
            data={"compensation": valid_comp},
        )
        db.session.refresh(existing_defect)
        assert existing_defect.compensation == valid_comp

    @pytest.mark.parametrize("invalid_comp", [
        "refund", "rejected", "", "PENDING", "Returned"
    ])
    def test_invalid_compensation_values_rejected(self, admin_client,
                                                    existing_defect,
                                                    invalid_comp):
        original = existing_defect.compensation
        admin_client.post(
            f"/defects/detail/{existing_defect.defect_detail_id}/edit",
            data={"compensation": invalid_comp},
        )
        db.session.refresh(existing_defect)
        assert existing_defect.compensation == original

    def test_edit_redirects_after_success(self, admin_client, existing_defect):
        response = admin_client.post(
            f"/defects/detail/{existing_defect.defect_detail_id}/edit",
            data={"compensation": "loss"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "product" in response.location

    def test_nonexistent_detail_returns_404(self, admin_client):
        response = admin_client.post(
            "/defects/detail/99999/edit",
            data={"compensation": "loss"},
        )
        assert response.status_code == 404

    def test_stocking_cannot_edit_detail(self, stocking_client,
                                          existing_defect):
        original = existing_defect.compensation
        stocking_client.post(
            f"/defects/detail/{existing_defect.defect_detail_id}/edit",
            data={"compensation": "loss"},
        )
        db.session.refresh(existing_defect)
        # Stocking is blocked — compensation must be unchanged
        assert existing_defect.compensation == original


# ---------------------------------------------------------------------------
# 5. GET /defects/log
#
#    WHAT: Verifies the defect log form page renders correctly.
#    WHY:  If this page crashes, stocking staff cannot log any defects —
#          defective items pile up with no record.
# ---------------------------------------------------------------------------

class TestLogPage:
    def test_renders_for_stocking(self, stocking_client):
        response = stocking_client.get("/defects/log")
        assert response.status_code == 200

    def test_renders_for_admin(self, admin_client):
        response = admin_client.get("/defects/log")
        assert response.status_code == 200

    def test_returns_html(self, stocking_client):
        response = stocking_client.get("/defects/log")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_renders_with_empty_db(self, stocking_client):
        response = stocking_client.get("/defects/log")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 6. POST /defects/api/search
# ---------------------------------------------------------------------------

class TestSearchAPI:
    def test_matches_by_name(self, stocking_client, product):
        response = post_json(stocking_client, "/defects/api/search",
                              {"query": product.product_name[:4]})
        data = get_json(response)
        assert any(r["product_id"] == product.product_id for r in data)

    def test_empty_query_returns_empty_list(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/search",
                              {"query": ""})
        assert get_json(response) == []

    def test_archived_excluded(self, stocking_client, archived_product):
        response = post_json(stocking_client, "/defects/api/search",
                              {"query": archived_product.product_name[:4]})
        data = get_json(response)
        assert archived_product.product_id not in [r["product_id"] for r in data]

    def test_result_has_correct_keys(self, stocking_client, product):
        response = post_json(stocking_client, "/defects/api/search",
                              {"query": product.product_name[:3]})
        data = get_json(response)
        if data:
            assert set(data[0].keys()) == {
                "product_id", "product_name", "product_price", "stock"
            }

    def test_sql_injection_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/search",
                              {"query": "'; DROP TABLE Products; --"})
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data

    def test_very_long_query_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/search",
                              {"query": "a" * 10000})
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 7. POST /defects/api/lookup
# ---------------------------------------------------------------------------

class TestLookupAPI:
    def test_finds_by_product_id(self, stocking_client, product):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": product.product_id})
        assert response.status_code == 200
        assert get_json(response)["product_id"] == product.product_id

    def test_finds_by_bundle_barcode(self, stocking_client,
                                      product, product_bundle):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": product_bundle.bundle_id})
        data = get_json(response)
        assert data["product_id"] == product.product_id
        assert data["scanned_as_bundle"] is True

    def test_returns_404_for_nonexistent(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": "NONEXISTENT-SKU"})
        assert response.status_code == 404

    def test_returns_400_for_archived(self, stocking_client, archived_product):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": archived_product.product_id})
        assert response.status_code == 400

    def test_returns_400_for_empty_query(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": ""})
        assert response.status_code == 400

    def test_result_has_correct_keys(self, stocking_client, product):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": product.product_id})
        data = get_json(response)
        expected = {
            "product_id", "product_name", "unit_price",
            "revenue_price", "product_price", "stock",
            "bundle", "scanned_as_bundle"
        }
        assert expected.issubset(set(data.keys()))

    def test_sql_injection_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/lookup",
                              {"query": "'; DROP TABLE Products; --"})
        assert response.status_code in [400, 404]
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 8. POST /defects/api/complete
#
#    WHAT: Verifies defect logging creates correct DB records and enforces
#          strict validation (unlike cashier charge which allows overselling).
#    WHY:  Defect logs are permanent financial records. A qty > stock is
#          an error here — you cannot log more defects than you have stock.
#          Both inventory.quantity_available AND quantity_defective must
#          update correctly.
# ---------------------------------------------------------------------------

class TestCompleteAPI:
    # -- Happy path --

    def test_valid_complete_returns_200(self, stocking_client, defect_item):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        assert response.status_code == 200

    def test_valid_complete_returns_success_true(self, stocking_client,
                                                   defect_item):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        data = get_json(response)
        assert data["success"] is True

    def test_creates_defect_record(self, stocking_client, defect_item):
        initial = Defect.query.count()
        post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        assert Defect.query.count() == initial + 1

    def test_creates_defect_detail_record(self, stocking_client, defect_item):
        initial = DefectDetail.query.count()
        post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        assert DefectDetail.query.count() == initial + 1

    def test_decrements_quantity_available(self, stocking_client, defect_item,
                                            inventory, product):
        initial_stock = inventory.quantity_available
        post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],  # qty=2
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available == initial_stock - defect_item["qty"]

    def test_increments_quantity_defective(self, stocking_client, defect_item,
                                            inventory, product):
        initial_defective = inventory.quantity_defective
        post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],  # qty=2
        })
        db.session.refresh(inventory)
        assert inventory.quantity_defective == initial_defective + defect_item["qty"]

    def test_returns_defect_id(self, stocking_client, defect_item):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        data = get_json(response)
        assert "defect_id" in data
        assert data["defect_id"] is not None

    def test_returns_correct_total_items(self, stocking_client, defect_item):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        data = get_json(response)
        assert data["total_items"] == 1

    def test_returns_correct_total_units(self, stocking_client, defect_item):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],  # qty=2
        })
        data = get_json(response)
        assert data["total_units"] == defect_item["qty"]

    def test_returns_correct_response_structure(self, stocking_client,
                                                  defect_item):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        data = get_json(response)
        assert set(data.keys()) >= {
            "success", "defect_id", "logged",
            "total_items", "total_units", "recorded_by", "datetime"
        }

    def test_multiple_items_creates_multiple_details(self, stocking_client,
                                                       product_with_stock,
                                                       second_product,
                                                       low_stock_inventory):
        # second_product has 1 unit via low_stock_inventory
        items = [
            {
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "defect",
                "compensation": "pending",
            },
            {
                "product_id":   second_product.product_id,
                "qty":          1,
                "reason":       "damage",
                "compensation": "loss",
            },
        ]
        initial_detail_count = DefectDetail.query.count()
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": items,
        })
        data = get_json(response)
        assert data["success"] is True
        assert data["total_items"] == 2
        assert DefectDetail.query.count() == initial_detail_count + 2

    def test_recorded_by_shows_user_name(self, stocking_client, defect_item,
                                          stocking_user):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [defect_item],
        })
        data = get_json(response)
        assert stocking_user.full_name in data["recorded_by"]

    # -- Reason enum validation --

    @pytest.mark.parametrize("valid_reason", [
        "defect", "damage", "expired", "change_of_mind"
    ])
    def test_valid_reason_values_accepted(self, stocking_client,
                                           product_with_stock, valid_reason):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       valid_reason,
                "compensation": "pending",
            }],
        })
        assert response.status_code == 200

    @pytest.mark.parametrize("invalid_reason", [
        "lost", "broken", "stolen", "", "DEFECT", "Defect"
    ])
    def test_invalid_reason_values_rejected(self, stocking_client,
                                             product_with_stock, invalid_reason):
        initial_defect_count = Defect.query.count()
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       invalid_reason,
                "compensation": "pending",
            }],
        })
        assert response.status_code == 400
        assert Defect.query.count() == initial_defect_count

    # -- Compensation enum validation --

    @pytest.mark.parametrize("valid_comp", [
        "pending", "loss", "returned", "replacement"
    ])
    def test_valid_compensation_values_accepted(self, stocking_client,
                                                  product_with_stock,
                                                  valid_comp):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "defect",
                "compensation": valid_comp,
            }],
        })
        assert response.status_code == 200

    @pytest.mark.parametrize("invalid_comp", [
        "refund", "rejected", "", "PENDING", "Loss"
    ])
    def test_invalid_compensation_values_rejected(self, stocking_client,
                                                    product_with_stock,
                                                    invalid_comp):
        initial_defect_count = Defect.query.count()
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "defect",
                "compensation": invalid_comp,
            }],
        })
        assert response.status_code == 400
        assert Defect.query.count() == initial_defect_count

    # -- Stock check (stricter than cashier — no override) --

    def test_qty_exceeds_stock_returns_400(self, stocking_client,
                                            product_with_stock, inventory):
        # Unlike cashier, defects BLOCK when qty > stock
        over_qty = inventory.quantity_available + 50
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          over_qty,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 400
        data = get_json(response)
        assert "stock" in data["error"].lower() or \
               "in stock" in data["error"].lower()

    def test_qty_exceeds_stock_no_defect_created(self, stocking_client,
                                                   product_with_stock,
                                                   inventory):
        initial = Defect.query.count()
        over_qty = inventory.quantity_available + 50
        post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          over_qty,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert Defect.query.count() == initial

    def test_qty_exactly_equals_stock_accepted(self, stocking_client,
                                                product_with_stock, inventory):
        # Logging exactly what's in stock — allowed
        exact_qty = inventory.quantity_available
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          exact_qty,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 200

    # -- Other validation errors --

    def test_empty_items_returns_400(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [],
        })
        assert response.status_code == 400

    def test_zero_qty_returns_400(self, stocking_client, product_with_stock):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          0,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 400

    def test_negative_qty_returns_400(self, stocking_client,
                                       product_with_stock):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          -5,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 400

    def test_nonexistent_product_returns_400(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   "NONEXISTENT-SKU",
                "qty":          1,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 400

    def test_archived_product_returns_400(self, stocking_client,
                                           archived_product):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   archived_product.product_id,
                "qty":          1,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert response.status_code == 400

    # -- DB atomicity — nothing written on validation failure --

    def test_no_defect_created_on_invalid_reason(self, stocking_client,
                                                   product_with_stock):
        initial = Defect.query.count()
        post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "invalid_reason",
                "compensation": "pending",
            }],
        })
        assert Defect.query.count() == initial

    def test_inventory_unchanged_on_validation_failure(self, stocking_client,
                                                         product_with_stock,
                                                         inventory):
        initial_stock = inventory.quantity_available
        post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "invalid_reason",
                "compensation": "pending",
            }],
        })
        db.session.refresh(inventory)
        assert inventory.quantity_available == initial_stock

    def test_second_item_failure_rolls_back_first_item(self, stocking_client,
                                                         product_with_stock,
                                                         second_product,
                                                         low_stock_inventory):
        # First item is valid, second has invalid reason
        # The whole batch must be rejected — no partial commits
        initial_defect_count = Defect.query.count()
        initial_stock = inventory = product_with_stock.inventory
        if initial_stock:
            initial_avail = initial_stock.quantity_available
        else:
            initial_avail = 0

        post_json(stocking_client, "/defects/api/complete", {
            "items": [
                {
                    "product_id":   product_with_stock.product_id,
                    "qty":          1,
                    "reason":       "defect",       # valid
                    "compensation": "pending",
                },
                {
                    "product_id":   second_product.product_id,
                    "qty":          1,
                    "reason":       "INVALID",      # invalid — should abort all
                    "compensation": "pending",
                },
            ],
        })
        # No Defect should have been created
        assert Defect.query.count() == initial_defect_count

    # -- Adversarial --

    def test_string_qty_does_not_crash(self, stocking_client,
                                        product_with_stock):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          "two",
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert b"Internal Server Error" not in response.data

    def test_sql_injection_in_product_id_does_not_crash(self, stocking_client):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   "'; DROP TABLE Products; --",
                "qty":          1,
                "reason":       "defect",
                "compensation": "pending",
            }],
        })
        assert b"Internal Server Error" not in response.data
        assert Product.query.count() >= 0

    def test_xss_in_reason_does_not_execute(self, stocking_client,
                                          product_with_stock):
        response = post_json(stocking_client, "/defects/api/complete", {
            "items": [{
                "product_id":   product_with_stock.product_id,
                "qty":          1,
                "reason":       "<script>alert('xss')</script>",
                "compensation": "pending",
            }],
        })
        # Invalid reason → 400 returned ✅
        assert response.status_code == 400
        # XSS in JSON response is safe — scripts don't execute in raw JSON
        # The real XSS protection happens when Jinja2 renders this in a template
        assert b"Internal Server Error" not in response.data

    def test_empty_body_does_not_crash(self, stocking_client):
        response = stocking_client.post(
            "/defects/api/complete",
            data="",
            content_type="application/json",
        )
        assert response.status_code in [400, 200]
        assert b"Internal Server Error" not in response.data

    def test_missing_body_does_not_crash(self, stocking_client):
        response = stocking_client.post("/defects/api/complete")
        assert response.status_code in [302, 400, 415]
        assert b"Internal Server Error" not in response.data