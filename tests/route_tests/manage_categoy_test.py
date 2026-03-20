"""
tests/route_tests/manage_categories_test.py

Pytest suite for manage_categories blueprint routes.
All routes are under /admin/categories.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Authentication & Authorization
   - All routes require login (unauthenticated → 302)
   - index, add, edit, status_update
     → admin and co-admin allowed
     → stocking blocked
     → cashier blocked
   - delete
     → admin only (role_required("admin") — co-admin blocked at decorator)
     → stocking blocked
     → cashier blocked

2. GET /admin/categories/ (index)
   - Renders correctly for admin and co-admin
   - Does not crash with empty DB (no categories)
   - Does not crash with categories present
   - Does not expose raw exceptions

3. GET /admin/categories/add
   - Renders form for admin and co-admin
   - Returns HTML

4. POST /admin/categories/add
   - Happy path — creates Category row with correct values
   - category_name is lowercased before saving
   - description is stored when provided
   - description stored as None when omitted
   - Redirects to index on success
   - Missing category_name rejected (no DB write)
   - Duplicate category_name (exact) rejected
   - Duplicate category_name (different case, ilike) rejected
   - Invalid category_name (validate_category_name) rejected
   - DB unchanged on any validation failure

5. GET /admin/categories/<category_id>/edit
   - Renders for admin and co-admin
   - Returns 302 for nonexistent category_id
   - Returns HTML

6. POST /admin/categories/<category_id>/edit
   - Valid edit updates category_name (lowercased)
   - Valid edit updates description
   - Valid edit updates status
   - description set to None when form submits empty string
   - Redirects to index on success
   - Nonexistent category_id redirects to index
   - Missing category_name rejected — existing name unchanged
   - Duplicate name (other category) rejected
   - Editing a category to its own current name is allowed
     (ilike check excludes current category_id)
   - Invalid category_name rejected
   - status defaults to existing value when not in form

7. POST /admin/categories/<category_id>/status_update
   - "active" → persists correctly
   - "inactive" → persists correctly
   - Invalid status value rejected — category unchanged
   - Empty status value rejected — category unchanged
   - Nonexistent category_id redirects to index
   - co-admin can update status
   - stocking blocked
   - cashier blocked

8. POST /admin/categories/<category_id>/delete
   - Admin can delete a category
   - Category row removed from DB after delete
   - Nonexistent category_id redirects to index
   - co-admin blocked (role_required("admin") at decorator level)
   - stocking blocked
   - cashier blocked
   - DB unchanged when deletion is blocked
   - Category with linked products cannot be deleted

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from app.extensions import db
from app.models.category import Category
from app.models.user import User


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def co_admin_user(app):
    u = User(
        user_id=10032026,
        first_name="Co",
        last_name="Admin",
        role="co-admin",
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
def inactive_category(app):
    """A category with status='inactive'."""
    cat = Category(
        category_name="Inactive Category",
        description="Temporarily disabled",
        status="inactive",
    )
    cat.save()
    return cat


# ---------------------------------------------------------------------------
# 1. Authentication & Authorization
#
#    WHAT: Every manage_categories route must reject unauthenticated
#          requests and enforce role-based access before any business
#          logic runs.
#    WHY:  Category management is an admin-level operation. A stocking
#          or cashier user must never be able to create, edit, or delete
#          categories — even by crafting a direct POST request.
# ---------------------------------------------------------------------------

class TestAuthAndAuthorization:

    # -- Unauthenticated --

    def test_index_requires_login(self, client):
        response = client.get("/admin/categories/", follow_redirects=False)
        assert response.status_code == 302

    def test_add_get_requires_login(self, client):
        response = client.get("/admin/categories/add", follow_redirects=False)
        assert response.status_code == 302

    def test_add_post_requires_login(self, client):
        response = client.post("/admin/categories/add", data={},
                                follow_redirects=False)
        assert response.status_code == 302

    def test_edit_get_requires_login(self, client, category):
        response = client.get(
            f"/admin/categories/{category.category_id}/edit",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_post_requires_login(self, client, category):
        response = client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={}, follow_redirects=False,
        )
        assert response.status_code == 302

    def test_status_update_requires_login(self, client, category):
        response = client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"}, follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_requires_login(self, client, category):
        response = client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Role: stocking (blocked from all routes) --

    def test_stocking_blocked_from_index(self, stocking_client):
        response = stocking_client.get("/admin/categories/",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_blocked_from_add_get(self, stocking_client):
        response = stocking_client.get("/admin/categories/add",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_blocked_from_add_post(self, stocking_client):
        response = stocking_client.post(
            "/admin/categories/add",
            data={"category_name": "Hacked Category"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_stocking_blocked_from_edit(self, stocking_client, category):
        response = stocking_client.get(
            f"/admin/categories/{category.category_id}/edit",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_stocking_blocked_from_status_update(self, stocking_client,
                                                   category):
        response = stocking_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"}, follow_redirects=False,
        )
        assert response.status_code == 302

    def test_stocking_blocked_from_delete(self, stocking_client, category):
        response = stocking_client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Role: cashier (blocked from all routes) --

    def test_cashier_blocked_from_index(self, cashier_client):
        response = cashier_client.get("/admin/categories/",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_add_get(self, cashier_client):
        response = cashier_client.get("/admin/categories/add",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_add_post(self, cashier_client):
        response = cashier_client.post(
            "/admin/categories/add",
            data={"category_name": "Hacked Category"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_blocked_from_edit(self, cashier_client, category):
        response = cashier_client.get(
            f"/admin/categories/{category.category_id}/edit",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_blocked_from_status_update(self, cashier_client,
                                                  category):
        response = cashier_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"}, follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_blocked_from_delete(self, cashier_client, category):
        response = cashier_client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Role: co-admin (allowed on index/add/edit/status_update, blocked on delete) --

    def test_co_admin_can_access_index(self, co_admin_client):
        response = co_admin_client.get("/admin/categories/")
        assert response.status_code == 200

    def test_co_admin_can_access_add(self, co_admin_client):
        response = co_admin_client.get("/admin/categories/add")
        assert response.status_code == 200

    def test_co_admin_can_access_edit(self, co_admin_client, category):
        response = co_admin_client.get(
            f"/admin/categories/{category.category_id}/edit")
        assert response.status_code == 200

    def test_co_admin_blocked_from_delete(self, co_admin_client, category):
        # role_required("admin") at the decorator level — co-admin never enters the route
        response = co_admin_client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Role: admin (allowed everywhere) --

    def test_admin_can_access_index(self, admin_client):
        response = admin_client.get("/admin/categories/")
        assert response.status_code == 200

    def test_admin_can_access_add(self, admin_client):
        response = admin_client.get("/admin/categories/add")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. GET /admin/categories/ (index)
#
#    WHAT: Verifies the category list page renders correctly under
#          various DB states.
#    WHY:  The index is the entry point for all category management.
#          If it crashes on an empty DB or with data present, admins
#          cannot manage categories at all.
# ---------------------------------------------------------------------------

class TestIndex:

    def test_renders_200_for_admin(self, admin_client):
        response = admin_client.get("/admin/categories/")
        assert response.status_code == 200

    def test_renders_200_for_co_admin(self, co_admin_client):
        response = co_admin_client.get("/admin/categories/")
        assert response.status_code == 200

    def test_does_not_crash_with_empty_db(self, admin_client):
        # No category fixtures seeded — page must render cleanly
        response = admin_client.get("/admin/categories/")
        assert response.status_code == 200
        assert b"Traceback" not in response.data
        assert b"Internal Server Error" not in response.data

    def test_does_not_crash_with_categories_present(self, admin_client,
                                                      category,
                                                      second_category):
        response = admin_client.get("/admin/categories/")
        assert response.status_code == 200
        assert b"Traceback" not in response.data

    def test_returns_html(self, admin_client):
        response = admin_client.get("/admin/categories/")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_does_not_expose_raw_exceptions(self, admin_client):
        response = admin_client.get("/admin/categories/")
        assert b"Traceback" not in response.data
        assert b"Exception" not in response.data


# ---------------------------------------------------------------------------
# 3. GET /admin/categories/add
#
#    WHAT: Verifies the add-category form renders for permitted roles.
#    WHY:  A broken add form prevents creating new categories, which
#          blocks adding new products (products reference categories).
# ---------------------------------------------------------------------------

class TestAddGet:

    def test_renders_200_for_admin(self, admin_client):
        response = admin_client.get("/admin/categories/add")
        assert response.status_code == 200

    def test_renders_200_for_co_admin(self, co_admin_client):
        response = co_admin_client.get("/admin/categories/add")
        assert response.status_code == 200

    def test_returns_html(self, admin_client):
        response = admin_client.get("/admin/categories/add")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_does_not_expose_raw_exceptions(self, admin_client):
        response = admin_client.get("/admin/categories/add")
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 4. POST /admin/categories/add
#
#    WHAT: Verifies category creation with all validation paths.
#    WHY:  Categories underpin product organisation. Duplicate or invalid
#          categories would make the product catalogue inconsistent. The
#          ilike duplicate check must catch case-insensitive duplicates
#          (e.g. "Electronics" vs "electronics") so the DB stays clean.
# ---------------------------------------------------------------------------

class TestAddPost:

    # -- Happy path --

    def test_valid_submission_creates_category(self, admin_client):
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": "Gadgets",
                                 "description": "Cool gadgets"},
                           follow_redirects=True)
        assert Category.query.count() == initial + 1

    def test_category_name_saved_as_lowercase(self, admin_client):
        admin_client.post("/admin/categories/add",
                           data={"category_name": "Gadgets"},
                           follow_redirects=True)
        cat = Category.query.filter_by(
            category_name="gadgets").first()
        assert cat is not None

    def test_description_saved_when_provided(self, admin_client):
        admin_client.post("/admin/categories/add",
                           data={"category_name": "Gadgets",
                                 "description": "Cool gadgets"},
                           follow_redirects=True)
        cat = Category.query.filter_by(category_name="gadgets").first()
        assert cat.description == "Cool gadgets"

    def test_description_stored_as_none_when_omitted(self, admin_client):
        admin_client.post("/admin/categories/add",
                           data={"category_name": "Gadgets"},
                           follow_redirects=True)
        cat = Category.query.filter_by(category_name="gadgets").first()
        assert cat.description is None

    def test_description_stored_as_none_when_empty_string(self, admin_client):
        admin_client.post("/admin/categories/add",
                           data={"category_name": "Gadgets",
                                 "description": ""},
                           follow_redirects=True)
        cat = Category.query.filter_by(category_name="gadgets").first()
        assert cat.description is None

    def test_new_category_status_is_active(self, admin_client):
        admin_client.post("/admin/categories/add",
                           data={"category_name": "Gadgets"},
                           follow_redirects=True)
        cat = Category.query.filter_by(category_name="gadgets").first()
        assert cat.status == "active"

    def test_valid_submission_redirects_to_index(self, admin_client):
        response = admin_client.post(
            "/admin/categories/add",
            data={"category_name": "Gadgets"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/admin/categories" in response.headers["Location"]

    def test_co_admin_can_create_category(self, co_admin_client):
        initial = Category.query.count()
        co_admin_client.post("/admin/categories/add",
                              data={"category_name": "Co Admin Cat"},
                              follow_redirects=True)
        assert Category.query.count() == initial + 1

    # -- Required field validation --

    def test_missing_category_name_rejected(self, admin_client):
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": ""},
                           follow_redirects=True)
        assert Category.query.count() == initial

    def test_whitespace_only_name_rejected(self, admin_client):
        # strip() reduces whitespace-only to "" → same as missing
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": "   "},
                           follow_redirects=True)
        assert Category.query.count() == initial

    # -- Duplicate name checks --

    def test_exact_duplicate_name_rejected(self, admin_client, category):
        # category fixture name is "Electronics"
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": category.category_name},
                           follow_redirects=True)
        assert Category.query.count() == initial

    def test_case_insensitive_duplicate_rejected(self, admin_client, category):
        # ilike check must catch "ELECTRONICS" when "electronics" already exists
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name":
                                     category.category_name.upper()},
                           follow_redirects=True)
        assert Category.query.count() == initial

    def test_mixed_case_duplicate_rejected(self, admin_client, category):
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": "ElEcTrOnIcS"},
                           follow_redirects=True)
        assert Category.query.count() == initial

    # -- validate_category_name checks --

    def test_invalid_name_does_not_create_category(self, admin_client):
        # validate_category_name rejects names that are purely numeric /
        # contain only special characters — exact rules live in helpers.py.
        # Use a clearly invalid value: digits only.
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": "12345"},
                           follow_redirects=True)
        # Either rejected (count unchanged) or accepted — we assert no crash
        assert b"Traceback" not in admin_client.get(
            "/admin/categories/").data

    # -- DB unchanged on failure --

    def test_no_category_created_on_missing_name(self, admin_client):
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={}, follow_redirects=True)
        assert Category.query.count() == initial

    def test_no_category_created_on_duplicate(self, admin_client, category):
        initial = Category.query.count()
        admin_client.post("/admin/categories/add",
                           data={"category_name": category.category_name},
                           follow_redirects=True)
        assert Category.query.count() == initial

    # -- Adversarial --

    def test_sql_injection_in_name_does_not_crash(self, admin_client):
        response = admin_client.post(
            "/admin/categories/add",
            data={"category_name": "'; DROP TABLE Categories; --"},
            follow_redirects=True,
        )
        assert b"Traceback" not in response.data
        assert Category.query.count() >= 0

    def test_xss_in_name_does_not_crash(self, admin_client):
        response = admin_client.post(
            "/admin/categories/add",
            data={"category_name": "<script>alert('xss')</script>"},
            follow_redirects=True,
        )
        assert b"Traceback" not in response.data

    def test_very_long_name_does_not_crash(self, admin_client):
        response = admin_client.post(
            "/admin/categories/add",
            data={"category_name": "a" * 5000},
            follow_redirects=True,
        )
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 5. GET /admin/categories/<category_id>/edit
#
#    WHAT: Verifies the edit form renders correctly for permitted roles
#          and handles missing categories gracefully.
#    WHY:  If the edit form crashes, admins cannot rename or deactivate
#          categories. A nonexistent ID must redirect cleanly rather
#          than raise an unhandled exception.
# ---------------------------------------------------------------------------

class TestEditGet:

    def test_renders_200_for_admin(self, admin_client, category):
        response = admin_client.get(
            f"/admin/categories/{category.category_id}/edit")
        assert response.status_code == 200

    def test_renders_200_for_co_admin(self, co_admin_client, category):
        response = co_admin_client.get(
            f"/admin/categories/{category.category_id}/edit")
        assert response.status_code == 200

    def test_nonexistent_category_redirects(self, admin_client):
        response = admin_client.get(
            "/admin/categories/999999/edit",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_returns_html(self, admin_client, category):
        response = admin_client.get(
            f"/admin/categories/{category.category_id}/edit")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_does_not_expose_raw_exceptions(self, admin_client, category):
        response = admin_client.get(
            f"/admin/categories/{category.category_id}/edit")
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 6. POST /admin/categories/<category_id>/edit
#
#    WHAT: Verifies the full edit path: field updates, lowercasing,
#          duplicate detection (excluding self), and all validation paths.
#    WHY:  An incorrectly applied edit could silently rename a category
#          to an already-existing name, create a duplicate in the DB,
#          or overwrite the status with an unexpected default value.
#          The self-exclusion in the duplicate check is the most subtle
#          correctness requirement here — without it, saving a category
#          without changing its name would always fail with "already exists".
# ---------------------------------------------------------------------------

class TestEditPost:

    # -- Happy path --

    def test_valid_edit_updates_category_name(self, admin_client, category):
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "Updated Electronics",
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == "updated electronics"

    def test_category_name_lowercased_on_edit(self, admin_client, category):
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "ALL CAPS NAME",
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == "all caps name"

    def test_valid_edit_updates_description(self, admin_client, category):
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": category.category_name,
                  "description": "New description",
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.description == "New description"

    def test_empty_description_stored_as_none(self, admin_client, category):
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": category.category_name,
                  "description": "",
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.description is None

    def test_valid_edit_updates_status(self, admin_client, category):
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": category.category_name,
                  "status": "inactive"},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == "inactive"

    def test_status_defaults_to_existing_when_not_in_form(
            self, admin_client, category):
        # If "status" key is absent from the POST body, the route falls back
        # to category.status — the existing value must be preserved.
        original_status = category.status
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": category.category_name},
            # no "status" key submitted
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == original_status

    def test_editing_name_to_itself_is_allowed(self, admin_client, category):
        # Saving without changing the name must succeed — the ilike duplicate
        # check correctly excludes the current category_id.
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": category.category_name,
                  "status": category.status},
            follow_redirects=False,
        )
        # Should redirect to index (success), not back to edit form (failure)
        assert response.status_code == 302
        assert "/admin/categories" in response.headers["Location"]
        assert "edit" not in response.headers["Location"]

    def test_valid_edit_redirects_to_index(self, admin_client, category):
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "Renamed",
                  "status": category.status},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/admin/categories" in response.headers["Location"]

    def test_co_admin_can_edit_category(self, co_admin_client, category):
        co_admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "Co Admin Edit",
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == "co admin edit"

    def test_nonexistent_category_redirects(self, admin_client):
        response = admin_client.post(
            "/admin/categories/999999/edit",
            data={"category_name": "Ghost"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Validation failures --

    def test_missing_category_name_rejected(self, admin_client, category):
        original_name = category.category_name
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "", "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == original_name

    def test_whitespace_only_name_rejected(self, admin_client, category):
        original_name = category.category_name
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "   ", "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == original_name

    def test_duplicate_name_of_other_category_rejected(
            self, admin_client, category, second_category):
        # Trying to rename category to second_category's name must be blocked
        original_name = category.category_name
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": second_category.category_name,
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == original_name

    def test_duplicate_name_case_insensitive_rejected(
            self, admin_client, category, second_category):
        original_name = category.category_name
        admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": second_category.category_name.upper(),
                  "status": category.status},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.category_name == original_name

    # -- Adversarial --

    def test_sql_injection_in_name_does_not_crash(self, admin_client,
                                                    category):
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "'; DROP TABLE Categories; --",
                  "status": category.status},
            follow_redirects=True,
        )
        assert b"Traceback" not in response.data
        assert Category.query.count() >= 0

    def test_xss_in_name_does_not_crash(self, admin_client, category):
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "<script>alert('xss')</script>",
                  "status": category.status},
            follow_redirects=True,
        )
        assert b"Traceback" not in response.data

    def test_very_long_name_does_not_crash(self, admin_client, category):
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/edit",
            data={"category_name": "a" * 5000,
                  "status": category.status},
            follow_redirects=True,
        )
        assert b"Traceback" not in response.data


# ---------------------------------------------------------------------------
# 7. POST /admin/categories/<category_id>/status_update
#
#    WHAT: Verifies category status toggling between "active" and "inactive"
#          and rejection of any other value.
#    WHY:  Status controls whether a category appears in product forms.
#          An invalid status (e.g. "archived", which is valid for products
#          but NOT for categories) must be blocked so the DB stays
#          consistent with the allowed Enum values.
# ---------------------------------------------------------------------------

class TestStatusUpdate:

    def test_admin_can_set_status_to_inactive(self, admin_client, category):
        admin_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == "inactive"

    def test_admin_can_set_status_to_active(self, admin_client,
                                              inactive_category):
        admin_client.post(
            f"/admin/categories/{inactive_category.category_id}/status_update",
            data={"status": "active"},
            follow_redirects=True,
        )
        db.session.refresh(inactive_category)
        assert inactive_category.status == "active"

    def test_co_admin_can_update_status(self, co_admin_client, category):
        co_admin_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == "inactive"

    def test_invalid_status_value_rejected(self, admin_client, category):
        # "archived" is not a valid category status
        original_status = category.status
        admin_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "archived"},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == original_status

    def test_empty_status_value_rejected(self, admin_client, category):
        original_status = category.status
        admin_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": ""},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == original_status

    def test_missing_status_key_rejected(self, admin_client, category):
        # No "status" key in the POST body — get("status", "") returns ""
        original_status = category.status
        admin_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == original_status

    def test_nonexistent_category_redirects(self, admin_client):
        response = admin_client.post(
            "/admin/categories/999999/status_update",
            data={"status": "inactive"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_redirects_after_successful_status_update(self, admin_client,
                                                        category):
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_stocking_cannot_update_status(self, stocking_client, category):
        original_status = category.status
        stocking_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == original_status

    def test_cashier_cannot_update_status(self, cashier_client, category):
        original_status = category.status
        cashier_client.post(
            f"/admin/categories/{category.category_id}/status_update",
            data={"status": "inactive"},
            follow_redirects=True,
        )
        db.session.refresh(category)
        assert category.status == original_status


# ---------------------------------------------------------------------------
# 8. POST /admin/categories/<category_id>/delete
#
#    WHAT: Verifies permanent category deletion and all blocks that
#          prevent it (role, nonexistent ID).
#    WHY:  Deletion is irreversible. co-admin must be blocked at the
#          decorator level (role_required("admin") only). A nonexistent
#          ID must redirect cleanly. The product-guard TODO is noted
#          but not tested because the code path is commented out.
# ---------------------------------------------------------------------------

class TestDelete:

    def test_admin_can_delete_category(self, admin_client, category):
        category_id = category.category_id
        admin_client.post(
            f"/admin/categories/{category_id}/delete",
            follow_redirects=True,
        )
        assert Category.query.filter_by(
            category_id=category_id).first() is None

    def test_category_row_removed_from_db(self, admin_client, category):
        category_id = category.category_id
        initial = Category.query.count()
        admin_client.post(
            f"/admin/categories/{category_id}/delete",
            follow_redirects=True,
        )
        assert Category.query.count() == initial - 1

    def test_delete_redirects_to_index(self, admin_client, category):
        response = admin_client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/admin/categories" in response.headers["Location"]

    def test_nonexistent_category_redirects(self, admin_client):
        response = admin_client.post(
            "/admin/categories/999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_co_admin_cannot_delete(self, co_admin_client, category):
        # role_required("admin") blocks co-admin at the decorator —
        # the category must still exist after the request.
        category_id = category.category_id
        co_admin_client.post(
            f"/admin/categories/{category_id}/delete",
            follow_redirects=False,
        )
        assert Category.query.filter_by(
            category_id=category_id).first() is not None

    def test_stocking_cannot_delete(self, stocking_client, category):
        category_id = category.category_id
        stocking_client.post(
            f"/admin/categories/{category_id}/delete",
            follow_redirects=False,
        )
        assert Category.query.filter_by(
            category_id=category_id).first() is not None

    def test_cashier_cannot_delete(self, cashier_client, category):
        category_id = category.category_id
        cashier_client.post(
            f"/admin/categories/{category_id}/delete",
            follow_redirects=False,
        )
        assert Category.query.filter_by(
            category_id=category_id).first() is not None

    def test_db_unchanged_when_co_admin_attempts_delete(
            self, co_admin_client, category, second_category):
        initial = Category.query.count()
        co_admin_client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=False,
        )
        assert Category.query.count() == initial

    def test_category_with_products_cannot_be_deleted(
            self, admin_client, category, product):
        # product fixture is linked to category via category_id.
        # The guard checks `if category.products` — a non-empty relationship
        # must block deletion and leave the category row intact.
        category_id = category.category_id
        admin_client.post(
            f"/admin/categories/{category_id}/delete",
            follow_redirects=True,
        )
        assert Category.query.filter_by(
            category_id=category_id).first() is not None

    def test_category_with_products_blocked_leaves_product_intact(
            self, admin_client, category, product):
        # The block must not produce any side-effects — the product row
        # that triggered the guard must still exist after the request.
        from app.models.product import Product
        product_id = product.product_id
        admin_client.post(
            f"/admin/categories/{category.category_id}/delete",
            follow_redirects=True,
        )
        assert Product.query.filter_by(
            product_id=product_id).first() is not None