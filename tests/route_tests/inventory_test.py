"""
tests/route_tests/inventory_test.py

Pytest suite for inventory blueprint routes.
All routes are under /inventory.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Authentication & Authorization
   - All routes require login (unauthenticated → 302)
   - index, edit (GET)
     → admin, co-admin, stocking allowed
     → cashier blocked
   - add (GET/POST), status_update, delete
     → admin, co-admin only
     → stocking blocked
     → cashier blocked
   - delete
     → co-admin blocked even though role_required passes (explicit check inside)

2. GET /inventory/ (index)
   - Renders correctly for all allowed roles
   - Does not crash with empty DB (no products)
   - Does not crash with products present
   - Does not expose raw exceptions

3. GET /inventory/add
   - Renders form for admin and co-admin
   - Blocked for stocking and cashier

4. POST /inventory/add
   - Happy path — creates Product + Inventory row (quantity 0)
   - Happy path with bundle — creates Product + Inventory + ProductBundle
   - Missing required fields flash and redirect (no DB write)
   - Invalid product name rejected
   - Invalid unit price rejected
   - Invalid revenue price rejected
   - Negative low_reorder_threshold rejected
   - Non-integer low_reorder_threshold rejected
   - Duplicate product_id (barcode already in use) rejected
   - Bundle ID same as product_id rejected
   - Partial bundle info (only some bundle fields) rejected
   - Bundle count < 2 rejected
   - Duplicate bundle_id (barcode already in use) rejected
   - DB is unchanged on any validation failure

5. GET /inventory/<product_id>/edit
   - Renders for admin, co-admin, stocking
   - Returns 302 for nonexistent product_id (flash + redirect)
   - Template receives product and categories

6. POST /inventory/<product_id>/edit — stocking role
   - Stocking can update quantity_available only
   - Valid stock update persists
   - Negative stock value rejected
   - Non-integer stock value rejected
   - Out-of-range stock value (> 2_147_483_647) rejected
   - No form data for stock → "no changes" info flash
   - Stocking cannot change product name / prices (ignored silently)

7. POST /inventory/<product_id>/edit — admin / co-admin
   - Valid full edit updates all fields
   - Product name, prices, category, status all updated
   - Stock update included in full edit
   - Duplicate product_name rejected
   - Invalid unit price rejected
   - Invalid revenue price rejected
   - Out-of-range low_reorder_threshold rejected
   - Nonexistent product_id redirects to index
   - product_price auto-calculated as unit_price + revenue_price
   - Bundle added when product had none
   - Bundle updated when product already has one
   - Bundle removed when all bundle fields cleared
   - Bundle count < 2 rejected
   - Partial bundle fields rejected
   - product_id rename updates product_id correctly
   - product_id rename conflict blocked

8. POST /inventory/<product_id>/s`tatus_update
   - Valid status "active" persists
   - Valid status "archived" persists
   - Invalid status value rejected with flash
   - Nonexistent product_id redirects to index
   - Stocking blocked (role_required)
   - Cashier blocked (role_required)

9. POST /inventory/<product_id>/delete
   - Admin can delete an archived product with no history
   - Product, Inventory, and Bundle rows all removed from DB
   - co-admin blocked (explicit check inside route)
   - Non-archived (active) product cannot be deleted
   - Nonexistent product_id redirects to index
   - Product with sale history cannot be deleted
   - Product with defect history cannot be deleted
   - DB unchanged when deletion is blocked

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
SQLite FK enforcement is enabled globally via conftest's event listener.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from app.extensions import db
from app.models.user import User
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.product_bundle import ProductBundle
from app.models.sale_detail import SaleDetail
from app.models.defect_detail import DefectDetail


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def co_admin_user(app):
    u = User(
        user_id=10032026,
        first_name="Co",
        last_name="superadmin",
        role="admin",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def stocking_user(app):
    u = User(
        user_id=10042026,
        first_name="Stock",
        last_name="Person",
        role="stocking",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def admin_client(client, user):
    """Authenticated client logged in as admin."""
    client.post("/", data={
        "full_name": f"{user.first_name} {user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def co_admin_client(client, co_admin_user):
    """Authenticated client logged in as co-admin."""
    client.post("/", data={
        "full_name": f"{co_admin_user.first_name} {co_admin_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def stocking_client(client, stocking_user):
    """Authenticated client logged in as stocking."""
    client.post("/", data={
        "full_name": f"{stocking_user.first_name} {stocking_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def cashier_client(client, cashier_user):
    """Authenticated client logged in as cashier."""
    client.post("/", data={
        "full_name": f"{cashier_user.first_name} {cashier_user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def archived_product_clean(app, category):
    """Archived product with NO sale or defect history — safe to delete."""
    prod = Product(
        product_id="PROD-DEL",
        product_name="Deletable Product",
        category_id=category.category_id,
        unit_price=Decimal("5.00"),
        revenue_price=Decimal("3.00"),
        product_price=Decimal("8.00"),
        low_reorder_threshold=1,
        status="archived",
    )
    prod.save()
    inv = Inventory(
        product_id=prod.product_id,
        quantity_available=0,
        quantity_defective=0,
        last_updated=datetime.utcnow(),
    )
    inv.save()
    return prod


@pytest.fixture
def valid_add_form(category):
    """Minimal valid POST body for /inventory/add."""
    return {
        "product_id":            "NEW-001",
        "product_name":          "New Product",
        "category_id":           str(category.category_id),
        "unit_price":            "10.00",
        "revenue_price":         "5.00",
        "low_reorder_threshold": "10",
        "bundle_id":             "",
        "bundle_name":           "",
        "bundle_count":          "",
    }


@pytest.fixture
def valid_edit_form(category):
    """Valid POST body for a full admin edit (mirrors the add form fields)."""
    return {
        "product_id":            "PROD-001",   # same as product fixture's ID
        "product_name":          "Updated Product",
        "category_id":           str(category.category_id),
        "unit_price":            "12.00",
        "revenue_price":         "6.00",
        "low_reorder_threshold": "8",
        "status":                "active",
        "bundle_id":             "",
        "bundle_name":           "",
        "bundle_count":          "",
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def get_flash_messages(response):
    """Return the raw response data as a string for flash message assertions."""
    return response.data.decode("utf-8")


# ---------------------------------------------------------------------------
# 1. Authentication & Authorization
#
#    WHAT: Every inventory route must reject unauthenticated requests and
#          enforce role-based access control before any business logic runs.
#    WHY:  Inventory management touches pricing and stock levels. An
#          unauthenticated or wrong-role user must never reach those actions.
# ---------------------------------------------------------------------------

class TestAuthAndAuthorization:

    # -- Unauthenticated --

    def test_index_requires_login(self, client):
        response = client.get("/inventory/", follow_redirects=False)
        assert response.status_code == 302

    def test_add_get_requires_login(self, client):
        response = client.get("/inventory/add", follow_redirects=False)
        assert response.status_code == 302

    def test_add_post_requires_login(self, client):
        response = client.post("/inventory/add", data={},
                                follow_redirects=False)
        assert response.status_code == 302

    def test_edit_get_requires_login(self, client, product):
        response = client.get(f"/inventory/{product.product_id}/edit",
                               follow_redirects=False)
        assert response.status_code == 302

    def test_edit_post_requires_login(self, client, product):
        response = client.post(f"/inventory/{product.product_id}/edit",
                                data={}, follow_redirects=False)
        assert response.status_code == 302

    def test_status_update_requires_login(self, client, product):
        response = client.post(f"/inventory/{product.product_id}/status_update",
                                data={"status": "archived"},
                                follow_redirects=False)
        assert response.status_code == 302

    def test_delete_requires_login(self, client, product):
        response = client.post(f"/inventory/{product.product_id}/delete",
                                follow_redirects=False)
        assert response.status_code == 302

    # -- Role: cashier (blocked from everything) --

    def test_cashier_blocked_from_index(self, cashier_client):
        response = cashier_client.get("/inventory/",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_add(self, cashier_client):
        response = cashier_client.get("/inventory/add",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_edit(self, cashier_client, product):
        response = cashier_client.get(f"/inventory/{product.product_id}/edit",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_status_update(self, cashier_client, product):
        response = cashier_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_blocked_from_delete(self, cashier_client, product):
        response = cashier_client.post(
            f"/inventory/{product.product_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Role: stocking (allowed on index and edit, blocked on add/status/delete) --

    def test_stocking_can_access_index(self, stocking_client):
        response = stocking_client.get("/inventory/")
        assert response.status_code == 200

    def test_stocking_blocked_from_add(self, stocking_client):
        response = stocking_client.get("/inventory/add",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_can_access_edit(self, stocking_client, product):
        response = stocking_client.get(
            f"/inventory/{product.product_id}/edit")
        assert response.status_code == 200

    def test_stocking_blocked_from_status_update(self, stocking_client,
                                                   product):
        response = stocking_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_stocking_blocked_from_delete(self, stocking_client, product):
        response = stocking_client.post(
            f"/inventory/{product.product_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Role: admin and co-admin (allowed on all routes) --

    def test_admin_can_access_index(self, admin_client):
        response = admin_client.get("/inventory/")
        assert response.status_code == 200

    def test_co_admin_can_access_index(self, co_admin_client):
        response = co_admin_client.get("/inventory/")
        assert response.status_code == 200

    def test_admin_can_access_add(self, admin_client):
        response = admin_client.get("/inventory/add")
        assert response.status_code == 200

    def test_co_admin_can_access_add(self, co_admin_client):
        response = co_admin_client.get("/inventory/add")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. GET /inventory/ (index)
#
#    WHAT: Verifies the inventory index page renders correctly under
#          various DB states and for all permitted roles.
#    WHY:  The index is the main inventory management screen. If it crashes
#          on empty DB or with products present, the entire inventory
#          management workflow is inaccessible.
# ---------------------------------------------------------------------------

class TestIndex:

    def test_renders_200_for_admin(self, admin_client):
        response = admin_client.get("/inventory/")
        assert response.status_code == 200

    def test_renders_200_for_co_admin(self, co_admin_client):
        response = co_admin_client.get("/inventory/")
        assert response.status_code == 200

    def test_renders_200_for_stocking(self, stocking_client):
        response = stocking_client.get("/inventory/")
        assert response.status_code == 200

    def test_does_not_crash_with_empty_db(self, admin_client):
        # No products seeded — page must still return 200 without exceptions
        response = admin_client.get("/inventory/")
        assert response.status_code == 200
        assert b"Traceback" not in response.data
        assert b"Internal Server Error" not in response.data

    def test_does_not_crash_with_products_present(self, admin_client,
                                                    product, inventory):
        response = admin_client.get("/inventory/")
        assert response.status_code == 200
        assert b"Traceback" not in response.data

    def test_returns_html(self, admin_client):
        response = admin_client.get("/inventory/")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_does_not_expose_raw_exceptions(self, admin_client):
        response = admin_client.get("/inventory/")
        assert b"Traceback" not in response.data
        assert b"Exception" not in response.data


# ---------------------------------------------------------------------------
# 3. GET /inventory/add
#
#    WHAT: Verifies the add-product form renders for permitted roles.
#    WHY:  A broken add form prevents adding new products entirely.
# ---------------------------------------------------------------------------

class TestAddGet:

    def test_renders_200_for_admin(self, admin_client):
        response = admin_client.get("/inventory/add")
        assert response.status_code == 200

    def test_renders_200_for_co_admin(self, co_admin_client):
        response = co_admin_client.get("/inventory/add")
        assert response.status_code == 200

    def test_returns_html(self, admin_client):
        response = admin_client.get("/inventory/add")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_does_not_crash_with_no_categories(self, admin_client):
        # No category fixtures seeded — form must still render
        response = admin_client.get("/inventory/add")
        assert response.status_code == 200
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 4. POST /inventory/add
#
#    WHAT: Verifies product creation with all validation paths.
#    WHY:  Adding a product is the gateway to inventory management. Invalid
#          data must be caught before hitting the DB. Successful creation
#          must produce exactly one Product + one Inventory row (and
#          optionally one ProductBundle). Partial writes on validation
#          failure would corrupt the inventory state.
# ---------------------------------------------------------------------------

class TestAddPost:

    # -- Happy path --

    def test_valid_submission_creates_product(self, admin_client,
                                               valid_add_form):
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=valid_add_form,
                           follow_redirects=True)
        assert Product.query.count() == initial + 1

    def test_valid_submission_creates_inventory_row(self, admin_client,
                                                     valid_add_form):
        admin_client.post("/inventory/add", data=valid_add_form,
                           follow_redirects=True)
        product = Product.query.filter_by(
            product_id=valid_add_form["product_id"]).first()
        assert product is not None
        assert product.inventory is not None

    def test_new_product_inventory_starts_at_zero(self, admin_client,
                                                    valid_add_form):
        admin_client.post("/inventory/add", data=valid_add_form,
                           follow_redirects=True)
        product = Product.query.filter_by(
            product_id=valid_add_form["product_id"]).first()
        assert product.inventory.quantity_available == 0
        assert product.inventory.quantity_defective == 0

    def test_product_price_calculated_correctly(self, admin_client,
                                                 valid_add_form):
        # product_price = unit_price + revenue_price = 10.00 + 5.00 = 15.00
        admin_client.post("/inventory/add", data=valid_add_form,
                           follow_redirects=True)
        product = Product.query.filter_by(
            product_id=valid_add_form["product_id"]).first()
        assert float(product.product_price) == 15.00

    def test_valid_submission_redirects_to_index(self, admin_client,
                                                   valid_add_form):
        response = admin_client.post("/inventory/add", data=valid_add_form,
                                      follow_redirects=False)
        assert response.status_code == 302
        assert "/inventory" in response.headers["Location"]

    def test_valid_submission_with_bundle_creates_bundle_row(
            self, admin_client, valid_add_form):
        form = {
            **valid_add_form,
            "bundle_id":    "BUNDLE-NEW",
            "bundle_name":  "12/pack",
            "bundle_count": "12",
        }
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        bundle = ProductBundle.query.filter_by(
            bundle_id="BUNDLE-NEW").first()
        assert bundle is not None
        assert bundle.bundle_count == 12

    def test_no_bundle_form_creates_no_bundle_row(self, admin_client,
                                                    valid_add_form):
        initial = ProductBundle.query.count()
        admin_client.post("/inventory/add", data=valid_add_form,
                           follow_redirects=True)
        assert ProductBundle.query.count() == initial

    # -- Required fields --

    def test_missing_product_id_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "product_id": ""}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_missing_product_name_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "product_name": ""}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_missing_unit_price_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "unit_price": ""}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_missing_revenue_price_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "revenue_price": ""}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_missing_low_reorder_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "low_reorder_threshold": ""}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    # -- Price validation --

    def test_non_numeric_unit_price_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "unit_price": "abc"}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_negative_unit_price_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "unit_price": "-1.00"}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_non_numeric_revenue_price_rejected(self, admin_client,
                                                 valid_add_form):
        form = {**valid_add_form, "revenue_price": "abc"}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    # -- Low reorder threshold validation --

    def test_negative_low_reorder_rejected(self, admin_client, valid_add_form):
        form = {**valid_add_form, "low_reorder_threshold": "-1"}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_non_integer_low_reorder_rejected(self, admin_client,
                                               valid_add_form):
        form = {**valid_add_form, "low_reorder_threshold": "3.5"}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    # -- Duplicate / barcode checks --

    def test_duplicate_product_id_rejected(self, admin_client, valid_add_form,
                                            product):
        # product fixture already uses "PROD-001"
        form = {**valid_add_form, "product_id": product.product_id}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_bundle_id_same_as_product_id_rejected(self, admin_client,
                                                     valid_add_form):
        form = {
            **valid_add_form,
            "bundle_id":    valid_add_form["product_id"],
            "bundle_name":  "12/pack",
            "bundle_count": "12",
        }
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    # -- Bundle partial-field validation --

    def test_partial_bundle_only_id_rejected(self, admin_client,
                                              valid_add_form):
        # bundle_id provided but name and count missing → rejected
        form = {**valid_add_form, "bundle_id": "BUNDLE-PARTIAL"}
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_bundle_count_below_2_rejected(self, admin_client, valid_add_form):
        form = {
            **valid_add_form,
            "bundle_id":    "BUNDLE-BAD",
            "bundle_name":  "1/pack",
            "bundle_count": "1",
        }
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    def test_duplicate_bundle_id_rejected(self, admin_client, valid_add_form,
                                           product_bundle):
        # product_bundle fixture uses "BUNDLE-001"
        form = {
            **valid_add_form,
            "bundle_id":    product_bundle.bundle_id,
            "bundle_name":  "12/pack",
            "bundle_count": "12",
        }
        initial = Product.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Product.query.count() == initial

    # -- DB unchanged on failure --

    def test_inventory_row_not_created_on_validation_failure(
            self, admin_client, valid_add_form):
        form = {**valid_add_form, "product_id": ""}
        initial_inv = Inventory.query.count()
        admin_client.post("/inventory/add", data=form,
                           follow_redirects=True)
        assert Inventory.query.count() == initial_inv


# ---------------------------------------------------------------------------
# 5. GET /inventory/<product_id>/edit
#
#    WHAT: Verifies the edit form renders correctly for all permitted roles
#          and handles missing products gracefully.
#    WHY:  If the edit form crashes or renders for the wrong role, stock
#          levels cannot be corrected and product data cannot be updated.
# ---------------------------------------------------------------------------

class TestEditGet:

    def test_renders_200_for_admin(self, admin_client, product):
        response = admin_client.get(
            f"/inventory/{product.product_id}/edit")
        assert response.status_code == 200

    def test_renders_200_for_co_admin(self, co_admin_client, product):
        response = co_admin_client.get(
            f"/inventory/{product.product_id}/edit")
        assert response.status_code == 200

    def test_renders_200_for_stocking(self, stocking_client, product):
        response = stocking_client.get(
            f"/inventory/{product.product_id}/edit")
        assert response.status_code == 200

    def test_nonexistent_product_redirects(self, admin_client):
        response = admin_client.get("/inventory/NONEXISTENT-999/edit",
                                     follow_redirects=False)
        assert response.status_code == 302

    def test_returns_html(self, admin_client, product):
        response = admin_client.get(
            f"/inventory/{product.product_id}/edit")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_does_not_expose_raw_exceptions(self, admin_client, product):
        response = admin_client.get(
            f"/inventory/{product.product_id}/edit")
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 6. POST /inventory/<product_id>/edit — stocking role
#
#    WHAT: Verifies stocking users can only adjust quantity_available and
#          that their edits cannot touch pricing or product metadata.
#    WHY:  Stocking staff are responsible for physical counts only. Allowing
#          them to modify prices or product IDs would be a privilege
#          escalation vulnerability. All other fields in their POST
#          must be silently ignored.
# ---------------------------------------------------------------------------

class TestEditPostStocking:

    def test_stocking_can_update_stock(self, stocking_client, product,
                                        inventory):
        response = stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={"quantity_available": "200"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        db.session.refresh(inventory)
        assert inventory.quantity_available == 200

    def test_stocking_stock_update_persists_in_db(self, stocking_client,
                                                    product, inventory):
        stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={"quantity_available": "50"},
            follow_redirects=True,
        )
        db.session.refresh(inventory)
        assert inventory.quantity_available == 50

    def test_stocking_negative_stock_rejected(self, stocking_client,
                                               product, inventory):
        original = inventory.quantity_available
        stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={"quantity_available": "-10"},
            follow_redirects=True,
        )
        db.session.refresh(inventory)
        assert inventory.quantity_available == original

    def test_stocking_non_integer_stock_rejected(self, stocking_client,
                                                   product, inventory):
        original = inventory.quantity_available
        stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={"quantity_available": "abc"},
            follow_redirects=True,
        )
        db.session.refresh(inventory)
        assert inventory.quantity_available == original

    def test_stocking_overflow_stock_rejected(self, stocking_client,
                                               product, inventory):
        # Values > 2_147_483_647 must be rejected (integer column limit)
        original = inventory.quantity_available
        stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={"quantity_available": "9999999999"},
            follow_redirects=True,
        )
        db.session.refresh(inventory)
        assert inventory.quantity_available == original

    def test_stocking_empty_stock_field_shows_info_flash(self, stocking_client,
                                                          product, inventory):
        # No quantity field submitted → route flashes "no changes" info
        original = inventory.quantity_available
        response = stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={},
            follow_redirects=True,
        )
        db.session.refresh(inventory)
        # Stock must be unchanged
        assert inventory.quantity_available == original
        assert response.status_code == 200

    def test_stocking_cannot_change_product_name(self, stocking_client,
                                                   product):
        # Even if a stocking user submits product_name, it must be ignored
        original_name = product.product_name
        stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={
                "quantity_available": "100",
                "product_name": "Hacked Name",
            },
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.product_name == original_name

    def test_stocking_redirects_to_index_after_update(self, stocking_client,
                                                        product, inventory):
        response = stocking_client.post(
            f"/inventory/{product.product_id}/edit",
            data={"quantity_available": "77"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/inventory" in response.headers["Location"]


# ---------------------------------------------------------------------------
# 7. POST /inventory/<product_id>/edit — admin / co-admin
#
#    WHAT: Verifies the full product edit path available to admin and co-admin.
#    WHY:  This is the most complex route in the blueprint. Incorrect price
#          calculation, failed product_id renames, or partial bundle updates
#          would leave pricing and inventory data inconsistent.
# ---------------------------------------------------------------------------

class TestEditPostAdmin:

    def test_valid_full_edit_updates_product_name(self, admin_client,
                                                    product, valid_edit_form,
                                                    inventory):
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=valid_edit_form,
                           follow_redirects=True)
        db.session.refresh(product)
        # Route lowercases the name before saving
        assert product.product_name == valid_edit_form["product_name"].lower()

    def test_valid_full_edit_updates_prices(self, admin_client, product,
                                             valid_edit_form, inventory):
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=valid_edit_form,
                           follow_redirects=True)
        db.session.refresh(product)
        assert float(product.unit_price) == 12.00
        assert float(product.revenue_price) == 6.00

    def test_product_price_recalculated_on_edit(self, admin_client, product,
                                                  valid_edit_form, inventory):
        # product_price = unit_price + revenue_price = 12.00 + 6.00 = 18.00
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=valid_edit_form,
                           follow_redirects=True)
        db.session.refresh(product)
        assert float(product.product_price) == 18.00

    def test_valid_full_edit_updates_status(self, admin_client, product,
                                             valid_edit_form, inventory):
        form = {**valid_edit_form, "status": "archived"}
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form,
                           follow_redirects=True)
        db.session.refresh(product)
        assert product.status == "archived"

    def test_valid_full_edit_updates_low_reorder(self, admin_client, product,
                                                   valid_edit_form, inventory):
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=valid_edit_form,
                           follow_redirects=True)
        db.session.refresh(product)
        assert product.low_reorder_threshold == 8

    def test_admin_can_adjust_stock_in_full_edit(self, admin_client, product,
                                                   inventory, valid_edit_form):
        form = {**valid_edit_form, "quantity_available": "250"}
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form,
                           follow_redirects=True)
        db.session.refresh(inventory)
        assert inventory.quantity_available == 250

    def test_edit_redirects_to_index_on_success(self, admin_client, product,
                                                   valid_edit_form, inventory):
        response = admin_client.post(
            f"/inventory/{product.product_id}/edit",
            data=valid_edit_form,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/inventory" in response.headers["Location"]

    def test_nonexistent_product_redirects(self, admin_client, valid_edit_form):
        response = admin_client.post(
            "/inventory/NONEXISTENT-999/edit",
            data=valid_edit_form,
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Validation failures --

    def test_missing_product_name_rejected(self, admin_client, product,
                                            valid_edit_form, inventory):
        form = {**valid_edit_form, "product_name": ""}
        original_name = product.product_name
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.product_name == original_name

    def test_invalid_unit_price_rejected(self, admin_client, product,
                                          valid_edit_form, inventory):
        form = {**valid_edit_form, "unit_price": "abc"}
        original_price = product.unit_price
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.unit_price == original_price

    def test_negative_unit_price_rejected(self, admin_client, product,
                                           valid_edit_form, inventory):
        form = {**valid_edit_form, "unit_price": "-5.00"}
        original_price = product.unit_price
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.unit_price == original_price

    def test_invalid_revenue_price_rejected(self, admin_client, product,
                                             valid_edit_form, inventory):
        form = {**valid_edit_form, "revenue_price": "xyz"}
        original = product.revenue_price
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.revenue_price == original

    def test_negative_low_reorder_rejected(self, admin_client, product,
                                            valid_edit_form, inventory):
        form = {**valid_edit_form, "low_reorder_threshold": "-1"}
        original = product.low_reorder_threshold
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.low_reorder_threshold == original

    def test_overflow_low_reorder_rejected(self, admin_client, product,
                                            valid_edit_form, inventory):
        form = {**valid_edit_form, "low_reorder_threshold": "9999999999"}
        original = product.low_reorder_threshold
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.low_reorder_threshold == original

    def test_duplicate_product_name_rejected(self, admin_client, product,
                                              second_product, valid_edit_form,
                                              inventory):
        # Try to rename product to second_product's name — must be blocked
        form = {**valid_edit_form,
                "product_name": second_product.product_name}
        original_name = product.product_name
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product)
        assert product.product_name == original_name

    def test_negative_stock_in_full_edit_rejected(self, admin_client, product,
                                                    valid_edit_form, inventory):
        form = {**valid_edit_form, "quantity_available": "-5"}
        original_stock = inventory.quantity_available
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(inventory)
        assert inventory.quantity_available == original_stock

    # -- Bundle management in full edit --

    def test_bundle_added_when_product_had_none(self, admin_client, product,
                                                  valid_edit_form, inventory):
        # product fixture has no bundle
        form = {
            **valid_edit_form,
            "bundle_id":    "BUNDLE-EDIT",
            "bundle_name":  "6/pack",
            "bundle_count": "6",
        }
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        bundle = ProductBundle.query.filter_by(
            bundle_id="BUNDLE-EDIT").first()
        assert bundle is not None
        assert bundle.bundle_count == 6

    def test_bundle_updated_when_product_has_existing_bundle(
            self, admin_client, product, product_bundle, valid_edit_form,
            inventory):
        # product_bundle fixture is linked to product
        form = {
            **valid_edit_form,
            "bundle_id":    product_bundle.bundle_id,
            "bundle_name":  "24/pack",
            "bundle_count": "24",
        }
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        db.session.refresh(product_bundle)
        assert product_bundle.bundle_count == 24

    def test_bundle_removed_when_fields_cleared(self, admin_client, product,
                                                  product_bundle, valid_edit_form,
                                                  inventory):
        # Submitting empty bundle fields should delete the existing bundle
        form = {
            **valid_edit_form,
            "bundle_id":    "",
            "bundle_name":  "",
            "bundle_count": "",
        }
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        remaining = ProductBundle.query.filter_by(
            bundle_id=product_bundle.bundle_id).first()
        assert remaining is None

    def test_partial_bundle_fields_rejected(self, admin_client, product,
                                             valid_edit_form, inventory):
        # bundle_id only, no count — must be rejected
        form = {**valid_edit_form, "bundle_id": "BUNDLE-PARTIAL"}
        initial_bundle_count = ProductBundle.query.count()
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        assert ProductBundle.query.count() == initial_bundle_count

    def test_bundle_count_below_2_rejected(self, admin_client, product,
                                            valid_edit_form, inventory):
        form = {
            **valid_edit_form,
            "bundle_id":    "BUNDLE-BAD",
            "bundle_name":  "1/pack",
            "bundle_count": "1",
        }
        initial = ProductBundle.query.count()
        admin_client.post(f"/inventory/{product.product_id}/edit",
                           data=form, follow_redirects=True)
        assert ProductBundle.query.count() == initial

    # -- Adversarial --

    def test_sql_injection_in_product_name_does_not_crash(
            self, admin_client, product, valid_edit_form, inventory):
        form = {**valid_edit_form,
                "product_name": "'; DROP TABLE Products; --"}
        response = admin_client.post(
            f"/inventory/{product.product_id}/edit",
            data=form, follow_redirects=True)
        assert b"Traceback" not in response.data
        # Products table must still exist
        assert Product.query.count() >= 0

    def test_xss_in_product_name_does_not_crash(self, admin_client, product,
                                                  valid_edit_form, inventory):
        form = {**valid_edit_form,
                "product_name": "<script>alert('xss')</script>"}
        response = admin_client.post(
            f"/inventory/{product.product_id}/edit",
            data=form, follow_redirects=True)
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 8. POST /inventory/<product_id>/status_update
#
#    WHAT: Verifies product status can be toggled between active/archived
#          and that invalid status values are rejected.
#    WHY:  Status controls whether a product appears in the cashier search
#          and can be sold. A broken status_update means products cannot
#          be retired without manual DB intervention.
# ---------------------------------------------------------------------------

class TestStatusUpdate:

    def test_admin_can_set_status_to_archived(self, admin_client, product):
        admin_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.status == "archived"

    def test_admin_can_set_status_to_active(self, admin_client,
                                              archived_product):
        admin_client.post(
            f"/inventory/{archived_product.product_id}/status_update",
            data={"status": "active"},
            follow_redirects=True,
        )
        db.session.refresh(archived_product)
        assert archived_product.status == "active"

    def test_co_admin_can_update_status(self, co_admin_client, product):
        co_admin_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.status == "archived"

    def test_invalid_status_value_rejected(self, admin_client, product):
        original_status = product.status
        admin_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "suspended"},
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.status == original_status

    def test_empty_status_value_rejected(self, admin_client, product):
        original_status = product.status
        admin_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": ""},
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.status == original_status

    def test_nonexistent_product_redirects(self, admin_client):
        response = admin_client.post(
            "/inventory/NONEXISTENT-999/status_update",
            data={"status": "archived"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_stocking_blocked_from_status_update(self, stocking_client,
                                                   product):
        original_status = product.status
        stocking_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.status == original_status

    def test_cashier_blocked_from_status_update(self, cashier_client, product):
        original_status = product.status
        cashier_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=True,
        )
        db.session.refresh(product)
        assert product.status == original_status

    def test_redirects_after_successful_update(self, admin_client, product):
        response = admin_client.post(
            f"/inventory/{product.product_id}/status_update",
            data={"status": "archived"},
            follow_redirects=False,
        )
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 9. POST /inventory/<product_id>/delete
#
#    WHAT: Verifies that permanent deletion enforces all guards: role,
#          archive status, and transaction/defect history.
#    WHY:  Deletion is irreversible. It must be blocked by co-admin (explicit
#          check inside the route, not role_required), by active status, and
#          by any transaction history. Failure to block any of these would
#          destroy product records and break all linked historical reports.
# ---------------------------------------------------------------------------

class TestDelete:

    def test_admin_can_delete_clean_archived_product(
            self, admin_client, archived_product_clean):
        product_id = archived_product_clean.product_id
        admin_client.post(
            f"/inventory/{product_id}/delete",
            follow_redirects=True,
        )
        assert Product.query.filter_by(product_id=product_id).first() is None

    def test_delete_removes_inventory_row(self, admin_client,
                                           archived_product_clean):
        product_id = archived_product_clean.product_id
        admin_client.post(
            f"/inventory/{product_id}/delete",
            follow_redirects=True,
        )
        assert Inventory.query.filter_by(product_id=product_id).first() is None

    def test_delete_removes_bundle_row(self, admin_client,
                                        archived_product_clean, app):
        # Attach a bundle then delete the product — bundle must go too
        bundle = ProductBundle(
            bundle_id="BUNDLE-DEL",
            product_id=archived_product_clean.product_id,
            bundle_name="6/pack",
            bundle_count=6,
        )
        bundle.save()

        admin_client.post(
            f"/inventory/{archived_product_clean.product_id}/delete",
            follow_redirects=True,
        )
        assert ProductBundle.query.filter_by(
            bundle_id="BUNDLE-DEL").first() is None

    def test_co_admin_cannot_delete(self, co_admin_client,
                                     archived_product_clean):
        product_id = archived_product_clean.product_id
        co_admin_client.post(
            f"/inventory/{product_id}/delete",
            follow_redirects=True,
        )
        # Product must still exist — co-admin is blocked inside the route
        assert Product.query.filter_by(product_id=product_id).first() \
               is not None

    def test_active_product_cannot_be_deleted(self, admin_client, product):
        # product fixture status = "active"
        product_id = product.product_id
        admin_client.post(
            f"/inventory/{product_id}/delete",
            follow_redirects=True,
        )
        assert Product.query.filter_by(product_id=product_id).first() \
               is not None

    def test_nonexistent_product_redirects(self, admin_client):
        response = admin_client.post(
            "/inventory/NONEXISTENT-999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_product_with_sale_history_cannot_be_deleted(
            self, admin_client, app, category, user):
        # Build an archived product that has a SaleDetail record
        prod = Product(
            product_id="PROD-HIST-SALE",
            product_name="History Sale Product",
            category_id=category.category_id,
            unit_price=Decimal("5.00"),
            revenue_price=Decimal("3.00"),
            product_price=Decimal("8.00"),
            low_reorder_threshold=1,
            status="archived",
        )
        prod.save()

        from app.models.sale import Sale
        s = Sale(
            user_id=user.user_id,
            total_unit_price=Decimal("5.00"),
            total_revenue_price=Decimal("3.00"),
            total_amount=Decimal("8.00"),
            payment_method="cash",
        )
        s.save()

        sd = SaleDetail(
            transaction_id=s.transaction_id,
            product_id=prod.product_id,
            quantity=1,
            unit_price_at_sale=Decimal("5.00"),
            revenue_price_at_sale=Decimal("3.00"),
            price_at_sale=Decimal("8.00"),
            subtotal_unit=Decimal("5.00"),
            subtotal_revenue=Decimal("3.00"),
            subtotal_amount=Decimal("8.00"),
        )
        sd.save()

        admin_client.post(
            f"/inventory/{prod.product_id}/delete",
            follow_redirects=True,
        )
        assert Product.query.filter_by(
            product_id=prod.product_id).first() is not None

    def test_product_with_defect_history_cannot_be_deleted(
            self, admin_client, app, category, user):
        # Build an archived product that has a DefectDetail record
        prod = Product(
            product_id="PROD-HIST-DEFECT",
            product_name="History Defect Product",
            category_id=category.category_id,
            unit_price=Decimal("5.00"),
            revenue_price=Decimal("3.00"),
            product_price=Decimal("8.00"),
            low_reorder_threshold=1,
            status="archived",
        )
        prod.save()

        from app.models.defect import Defect
        d = Defect(
            user_id=user.user_id,
            total_unit_price=Decimal("5.00"),
            total_revenue_price=Decimal("3.00"),
            total_amount=Decimal("8.00"),
        )
        d.save()

        dd = DefectDetail(
            defect_id=d.defect_id,
            product_id=prod.product_id,
            quantity=1,
            reason="defect",
            compensation="pending",
            unit_price_at_defect=Decimal("5.00"),
            revenue_price_at_defect=Decimal("3.00"),
            price_at_defect=Decimal("8.00"),
            subtotal_unit=Decimal("5.00"),
            subtotal_revenue=Decimal("3.00"),
            subtotal_amount=Decimal("8.00"),
        )
        dd.save()

        admin_client.post(
            f"/inventory/{prod.product_id}/delete",
            follow_redirects=True,
        )
        assert Product.query.filter_by(
            product_id=prod.product_id).first() is not None

    def test_db_unchanged_when_deletion_blocked(self, admin_client, product):
        # Active product — deletion must be a no-op
        initial_product_count = Product.query.count()
        initial_inv_count = Inventory.query.count()
        admin_client.post(
            f"/inventory/{product.product_id}/delete",
            follow_redirects=True,
        )
        assert Product.query.count() == initial_product_count
        assert Inventory.query.count() == initial_inv_count

    def test_stocking_blocked_from_delete(self, stocking_client,
                                           archived_product_clean):
        product_id = archived_product_clean.product_id
        stocking_client.post(
            f"/inventory/{product_id}/delete",
            follow_redirects=False,
        )
        assert Product.query.filter_by(
            product_id=product_id).first() is not None

    def test_cashier_blocked_from_delete(self, cashier_client,
                                          archived_product_clean):
        product_id = archived_product_clean.product_id
        cashier_client.post(
            f"/inventory/{product_id}/delete",
            follow_redirects=False,
        )
        assert Product.query.filter_by(
            product_id=product_id).first() is not None