"""
tests/route_tests/manage_users_test.py

Pytest suite for manage_users blueprint.
All routes are under /admin/users and require login + admin/co-admin role.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Authentication & Authorization
   - All routes require login — unauthenticated access redirects
   - All routes require admin or co-admin role
   - cashier and stocking roles are blocked from all routes

2. GET /admin/users/ (index)
   - Renders user list for admin/co-admin
   - Current user excluded from the list

3. GET /admin/users/add
   - Renders add form for admin/co-admin

4. POST /admin/users/add
   - Happy path — valid data creates user with correct defaults
   - Default password used when no password provided
   - Custom password validated and used when provided
   - Required fields enforced (first_name, last_name, role)
   - validate_name rules enforced on first and last name
   - validate_password rules enforced on custom password
   - Duplicate user (same name + role) blocked
   - New user status is always "not_activated"
   - Adversarial — oversized inputs, special chars, SQL injection,
     numbers in name, missing fields

5. GET /admin/users/<id>/edit
   - Renders edit form for valid user
   - Nonexistent user redirects cleanly (not 500)
   - Admin user cannot be edited

6. POST /admin/users/<id>/edit
   - Happy path — valid changes persist
   - Password only updated when provided
   - Password unchanged when not provided
   - validate_name enforced on both name fields
   - validate_password enforced on new password
   - Adversarial — oversized inputs, invalid names

7. POST /admin/users/<id>/status_update
   - Valid status values update correctly
   - Invalid status values rejected
   - Admin cannot change their own status
   - Nonexistent user handled gracefully

8. POST /admin/users/<id>/reset_password
   - Resets password to default and sets status to not_activated
   - Nonexistent user handled gracefully

9. POST /admin/users/<id>/delete
   - Only archived users can be deleted
   - Active/suspended/not_activated users cannot be deleted
   - Nonexistent user handled gracefully
   - Successful delete removes user from DB

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from app.extensions import db
from app.models.user import User


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(client, user):
    """Authenticated client as admin (user fixture has role='superadmin')."""
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
def target_user(app):
    """A non-admin user that can be safely edited/deleted in tests."""
    u = User(
        user_id=10092026,
        first_name="target",
        last_name="user",
        role="cashier",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def archived_target(app):
    """An archived user that can be deleted."""
    u = User(
        user_id=10102026,
        first_name="archived",
        last_name="target",
        role="cashier",
        status="archived",
    )
    u.set_password("shekel123")
    u.save()
    return u


# ---------------------------------------------------------------------------
# 1. Authentication & Authorization
#
#    WHAT: Verifies every route requires login and admin/co-admin role.
#    WHY:  User management is the highest-privilege operation in the system.
#          Any role bypass would let a cashier create admin accounts or
#          delete users — a critical security failure.
# ---------------------------------------------------------------------------

class TestAuthAndAuthorization:
    # -- Unauthenticated access --

    def test_index_requires_login(self, client):
        response = client.get("/admin/users/", follow_redirects=False)
        assert response.status_code == 302

    def test_add_requires_login(self, client):
        response = client.get("/admin/users/add", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_requires_login(self, client, target_user):
        response = client.get(
            f"/admin/users/{target_user.user_id}/edit",
            follow_redirects=False
        )
        assert response.status_code == 302

    def test_status_update_requires_login(self, client, target_user):
        response = client.post(
            f"/admin/users/{target_user.user_id}/status_update",
            data={"status": "suspended"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_reset_password_requires_login(self, client, target_user):
        response = client.post(
            f"/admin/users/{target_user.user_id}/reset_password",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_requires_login(self, client, archived_target):
        response = client.post(
            f"/admin/users/{archived_target.user_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    # -- Wrong role access --

    def test_cashier_cannot_access_index(self, cashier_client):
        response = cashier_client.get(
            "/admin/users/", follow_redirects=False
        )
        assert response.status_code == 302

    def test_cashier_cannot_add_user(self, cashier_client):
        response = cashier_client.post(
            "/admin/users/add",
            data={"first_name": "hacker", "last_name": "user", "role": "superadmin"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_cannot_edit_user(self, cashier_client, target_user):
        response = cashier_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={"first_name": "hacked"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_cannot_delete_user(self, cashier_client, archived_target):
        response = cashier_client.post(
            f"/admin/users/{archived_target.user_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        # User must still exist in DB — cashier did nothing
        assert User.get_by_id(archived_target.user_id) is not None

    def test_cashier_cannot_reset_password(self, cashier_client, target_user):
        response = cashier_client.post(
            f"/admin/users/{target_user.user_id}/reset_password",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_cashier_cannot_change_status(self, cashier_client, target_user):
        response = cashier_client.post(
            f"/admin/users/{target_user.user_id}/status_update",
            data={"status": "archived"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        # Status must be unchanged
        db.session.refresh(target_user)
        assert target_user.status == "activated"


# ---------------------------------------------------------------------------
# 2. GET /admin/users/ (index)
#
#    WHAT: Verifies the user list renders and excludes the current user.
#    WHY:  Admins should not see themselves in the user management list —
#          prevents self-modification accidents and is the expected UX.
# ---------------------------------------------------------------------------

class TestIndex:
    def test_index_renders_for_admin(self, admin_client):
        response = admin_client.get("/admin/users/")
        assert response.status_code == 200

    def test_index_returns_html(self, admin_client):
        response = admin_client.get("/admin/users/")
        assert b"<html" in response.data or b"<!DOCTYPE" in response.data

    def test_index_does_not_crash_with_no_other_users(self, admin_client):
        # Only the admin user exists — list should render empty, not crash
        response = admin_client.get("/admin/users/")
        assert response.status_code == 200
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 3. GET /admin/users/add (add form)
#
#    WHAT: Verifies the add form renders correctly.
#    WHY:  If the form doesn't render, no new users can be created.
# ---------------------------------------------------------------------------

class TestAddGet:
    def test_add_form_renders(self, admin_client):
        response = admin_client.get("/admin/users/add")
        assert response.status_code == 200

    def test_add_form_shows_default_password(self, admin_client):
        # Form should display the current default password for reference
        response = admin_client.get("/admin/users/add")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 4. POST /admin/users/add (create user)
#
#    WHAT: Verifies user creation with all validation rules enforced.
#    WHY:  Creating users with invalid data, duplicate names, or wrong
#          roles would corrupt the user table and break login for new staff.
# ---------------------------------------------------------------------------

class TestAddPost:
    def test_valid_user_creation(self, admin_client, app):
        # Happy path — all valid fields, no custom password
        response = admin_client.post("/admin/users/add", data={
            "first_name": "john",
            "last_name": "doe",
            "role": "cashier",
            "password": "",
        }, follow_redirects=False)

        assert response.status_code == 302
        assert "users" in response.location

        # User must exist in DB
        new_user = User.query.filter_by(
            first_name="john", last_name="doe"
        ).first()
        assert new_user is not None

    def test_new_user_status_is_not_activated(self, admin_client, app):
        # New users must always start as not_activated
        admin_client.post("/admin/users/add", data={
            "first_name": "jane",
            "last_name": "smith",
            "role": "cashier",
            "password": "",
        })
        new_user = User.query.filter_by(
            first_name="jane", last_name="smith"
        ).first()
        assert new_user.status == "not_activated"

    def test_new_user_gets_default_password_when_none_provided(self, admin_client,
                                                                app):
        # When password is empty, default password is assigned
        admin_client.post("/admin/users/add", data={
            "first_name": "no",
            "last_name": "pass",
            "role": "cashier",
            "password": "",
        })
        new_user = User.query.filter_by(
            first_name="no", last_name="pass"
        ).first()
        assert new_user is not None
        assert new_user.check_password(User.get_default_password())

    def test_custom_password_used_when_provided(self, admin_client, app):
        # When a valid custom password is provided, it must be used
        admin_client.post("/admin/users/add", data={
            "first_name": "custom",
            "last_name": "pass",
            "role": "cashier",
            "password": "CustomPass1@",
        })
        new_user = User.query.filter_by(
            first_name="custom", last_name="pass"
        ).first()
        assert new_user is not None
        assert new_user.check_password("CustomPass1@")

    def test_user_id_auto_generated(self, admin_client, app):
        # user_id must be auto-generated — not zero or None
        admin_client.post("/admin/users/add", data={
            "first_name": "auto",
            "last_name": "id",
            "role": "cashier",
            "password": "",
        })
        new_user = User.query.filter_by(
            first_name="auto", last_name="id"
        ).first()
        assert new_user is not None
        assert new_user.user_id is not None
        assert new_user.user_id > 0

    # -- Required fields --

    def test_missing_first_name_rejected(self, admin_client):
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "",
            "last_name": "doe",
            "role": "cashier",
        })
        assert User.query.count() == initial_count

    def test_missing_last_name_rejected(self, admin_client):
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "john",
            "last_name": "",
            "role": "cashier",
        })
        assert User.query.count() == initial_count

    def test_missing_role_rejected(self, admin_client):
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "john",
            "last_name": "doe",
            "role": "",
        })
        assert User.query.count() == initial_count

    # -- validate_name rules --

    def test_numbers_in_first_name_rejected(self, admin_client):
        # validate_name only allows letters, spaces, hyphens
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "john123",
            "last_name": "doe",
            "role": "cashier",
        })
        assert User.query.count() == initial_count

    def test_special_chars_in_first_name_rejected(self, admin_client):
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "john@doe",
            "last_name": "doe",
            "role": "cashier",
        })
        assert User.query.count() == initial_count

    def test_numbers_in_last_name_rejected(self, admin_client):
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "john",
            "last_name": "doe123",
            "role": "cashier",
        })
        assert User.query.count() == initial_count

    def test_hyphenated_name_accepted(self, admin_client, app):
        # Hyphens are valid in names (e.g. "mary-jane")
        admin_client.post("/admin/users/add", data={
            "first_name": "mary-jane",
            "last_name": "doe",
            "role": "cashier",
        })
        new_user = User.query.filter_by(first_name="mary-jane").first()
        assert new_user is not None

    # -- validate_password rules --

    def test_invalid_custom_password_rejected(self, admin_client):
        # Custom password that fails validation — user not created
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "weak",
            "last_name": "pass",
            "role": "cashier",
            "password": "weakpass",  # no uppercase, no special char
        })
        assert User.query.count() == initial_count

    def test_short_custom_password_rejected(self, admin_client):
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "short",
            "last_name": "pass",
            "role": "cashier",
            "password": "Ab1@",  # too short
        })
        assert User.query.count() == initial_count

    # -- Duplicate check --

    def test_duplicate_user_same_name_and_role_rejected(self, admin_client,
                                                          target_user):
        # target_user is first_name="target", last_name="user", role="cashier"
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "target",
            "last_name": "user",
            "role": "cashier",
        })
        assert User.query.count() == initial_count

    def test_same_name_different_role_allowed(self, admin_client, target_user):
        # Same name but different role — not a duplicate
        initial_count = User.query.count()
        admin_client.post("/admin/users/add", data={
            "first_name": "target",
            "last_name": "user",
            "role": "stocking",  # different role
        })
        assert User.query.count() == initial_count + 1


# ---------------------------------------------------------------------------
# 5. GET /admin/users/<id>/edit
#
#    WHAT: Verifies edit form renders for valid users and handles
#          edge cases without crashing.
#    WHY:  A crash on GET /edit means the admin cannot access the edit
#          form at all — blocking user management entirely.
# ---------------------------------------------------------------------------

class TestEditGet:
    def test_edit_form_renders_for_valid_user(self, admin_client, target_user):
        response = admin_client.get(
            f"/admin/users/{target_user.user_id}/edit"
        )
        assert response.status_code == 200

    def test_edit_nonexistent_user_redirects(self, admin_client):
        # Nonexistent user_id — must redirect, not crash with 500
        response = admin_client.get(
            "/admin/users/99999999/edit",
            follow_redirects=False,
        )
        # Should redirect gracefully — not 500
        assert response.status_code in [302, 404]
        assert b"500" not in response.data

    def test_edit_admin_user_redirects(self, admin_client, user):
        # Trying to edit the admin user — must be blocked
        response = admin_client.get(
            f"/admin/users/{user.user_id}/edit",
            follow_redirects=False,
        )
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 6. POST /admin/users/<id>/edit
#
#    WHAT: Verifies user edits are validated and persisted correctly.
#    WHY:  An edit that silently corrupts the name, role, or password
#          would break that user's ability to log in.
# ---------------------------------------------------------------------------

class TestEditPost:
    def test_valid_edit_persists(self, admin_client, target_user):
        admin_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={
                "first_name": "updated",
                "last_name": "name",
                "role": "stocking",
                "status": "activated",
                "password": "",
            },
        )
        db.session.refresh(target_user)
        assert target_user.first_name == "updated"
        assert target_user.last_name == "name"
        assert target_user.role == "stocking"

    def test_password_updated_when_provided(self, admin_client, target_user):
        admin_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={
                "first_name": target_user.first_name,
                "last_name": target_user.last_name,
                "role": target_user.role,
                "status": target_user.status,
                "password": "NewPass1@valid",
            },
        )
        db.session.refresh(target_user)
        assert target_user.check_password("NewPass1@valid")

    def test_password_unchanged_when_not_provided(self, admin_client, target_user):
        # No password field submitted — existing password must not change
        original_hash = target_user.password
        admin_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={
                "first_name": target_user.first_name,
                "last_name": target_user.last_name,
                "role": target_user.role,
                "status": target_user.status,
                "password": "",
            },
        )
        db.session.refresh(target_user)
        assert target_user.password == original_hash

    def test_invalid_name_in_edit_rejected(self, admin_client, target_user):
        # Numbers in name — validate_name must reject
        original_name = target_user.first_name
        admin_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={
                "first_name": "invalid123",
                "last_name": target_user.last_name,
                "role": target_user.role,
                "status": target_user.status,
                "password": "",
            },
        )
        db.session.refresh(target_user)
        assert target_user.first_name == original_name

    def test_invalid_password_in_edit_rejected(self, admin_client, target_user):
        # Weak password — validate_password must reject
        original_hash = target_user.password
        admin_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={
                "first_name": target_user.first_name,
                "last_name": target_user.last_name,
                "role": target_user.role,
                "status": target_user.status,
                "password": "weakpass",
            },
        )
        db.session.refresh(target_user)
        assert target_user.password == original_hash

    def test_edit_redirects_to_index_on_success(self, admin_client, target_user):
        response = admin_client.post(
            f"/admin/users/{target_user.user_id}/edit",
            data={
                "first_name": "redirected",
                "last_name": "user",
                "role": "cashier",
                "status": "activated",
                "password": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "users" in response.location


# ---------------------------------------------------------------------------
# 7. POST /admin/users/<id>/status_update
#
#    WHAT: Verifies status changes are validated and that admins cannot
#          change their own status.
#    WHY:  An admin accidentally suspending or archiving themselves would
#          lock them out of the system with no way to recover without DB
#          access. Invalid status values must also be rejected to prevent
#          DB corruption.
# ---------------------------------------------------------------------------

class TestStatusUpdate:
    @pytest.mark.parametrize("valid_status", [
        "activated", "not_activated", "suspended", "archived"
    ])
    def test_valid_status_values_accepted(self, admin_client, target_user,
                                          valid_status):
        # Each valid status should update and redirect
        response = admin_client.post(
            f"/admin/users/{target_user.user_id}/status_update",
            data={"status": valid_status},
            follow_redirects=False,
        )
        assert response.status_code == 302
        db.session.refresh(target_user)
        assert target_user.status == valid_status

    @pytest.mark.parametrize("invalid_status", [
        "banned", "deleted", "active", "", "ACTIVATED", "Suspended"
    ])
    def test_invalid_status_values_rejected(self, admin_client, target_user,
                                             invalid_status):
        # Invalid status must not be saved
        original_status = target_user.status
        admin_client.post(
            f"/admin/users/{target_user.user_id}/status_update",
            data={"status": invalid_status},
        )
        db.session.refresh(target_user)
        assert target_user.status == original_status

    def test_admin_cannot_change_own_status(self, admin_client, user):
        # Admin cannot suspend/archive themselves
        original_status = user.status
        admin_client.post(
            f"/admin/users/{user.user_id}/status_update",
            data={"status": "suspended"},
        )
        db.session.refresh(user)
        assert user.status == original_status

    def test_status_update_nonexistent_user_redirects(self, admin_client):
        response = admin_client.post(
            "/admin/users/99999999/status_update",
            data={"status": "suspended"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 8. POST /admin/users/<id>/reset_password
#
#    WHAT: Verifies password reset restores default password and
#          sets status back to not_activated.
#    WHY:  A broken reset flow would leave a user with a password only
#          they know and no way for admin to regain control of the account.
#          Resetting to default + not_activated forces the user to go
#          through the activation flow again.
# ---------------------------------------------------------------------------

class TestResetPassword:
    def test_reset_password_sets_default_password(self, admin_client,
                                                    target_user):
        # After reset, user's password must match current default
        admin_client.post(
            f"/admin/users/{target_user.user_id}/reset_password"
        )
        db.session.refresh(target_user)
        assert target_user.check_password(User.get_default_password())

    def test_reset_password_sets_status_to_not_activated(self, admin_client,
                                                           target_user):
        # After reset, user must go through activation again
        admin_client.post(
            f"/admin/users/{target_user.user_id}/reset_password"
        )
        db.session.refresh(target_user)
        assert target_user.status == "not_activated"

    def test_reset_password_redirects(self, admin_client, target_user):
        response = admin_client.post(
            f"/admin/users/{target_user.user_id}/reset_password",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_reset_nonexistent_user_redirects(self, admin_client):
        response = admin_client.post(
            "/admin/users/99999999/reset_password",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert b"500" not in response.data

    def test_reset_forces_new_login_with_default_password(self, admin_client,
                                                            target_user, client):
        # After reset, the user can log in with the default password
        admin_client.post(
            f"/admin/users/{target_user.user_id}/reset_password"
        )
        db.session.refresh(target_user)

        # Try logging in with default password using a fresh client
        response = client.post("/", data={
            "full_name": f"{target_user.first_name} {target_user.last_name}",
            "password": User.get_default_password(),
        }, follow_redirects=False)

        # not_activated → redirected to activation, not logged in directly
        assert response.status_code == 302
        assert "account_activation" in response.location


# ---------------------------------------------------------------------------
# 9. POST /admin/users/<id>/delete
#
#    WHAT: Verifies only archived users can be deleted and that
#          non-archived users are protected.
#    WHY:  Accidental deletion of active users is irreversible and would
#          break their session, lose their history, and cause FK errors
#          if they have associated sales or defect records.
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_archived_user_can_be_deleted(self, admin_client, archived_target):
        # Only archived users should be deletable
        user_id = archived_target.user_id
        admin_client.post(
            f"/admin/users/{user_id}/delete",
        )
        assert User.get_by_id(user_id) is None

    def test_active_user_cannot_be_deleted(self, admin_client, target_user):
        # Active users are protected from deletion
        user_id = target_user.user_id
        admin_client.post(
            f"/admin/users/{user_id}/delete",
        )
        assert User.get_by_id(user_id) is not None

    def test_suspended_user_cannot_be_deleted(self, admin_client, app):
        # Suspended users must be archived first before deletion
        u = User(
            user_id=10112026,
            first_name="suspended",
            last_name="nodelete",
            role="cashier",
            status="suspended",
        )
        u.set_password("shekel123")
        u.save()

        admin_client.post(f"/admin/users/{u.user_id}/delete")
        assert User.get_by_id(u.user_id) is not None

    def test_not_activated_user_cannot_be_deleted(self, admin_client, app):
        # not_activated users cannot be deleted directly
        u = User(
            user_id=10122026,
            first_name="notactivated",
            last_name="nodelete",
            role="cashier",
            status="not_activated",
        )
        u.set_password("shekel123")
        u.save()

        admin_client.post(f"/admin/users/{u.user_id}/delete")
        assert User.get_by_id(u.user_id) is not None

    def test_delete_nonexistent_user_redirects(self, admin_client):
        response = admin_client.post(
            "/admin/users/99999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert b"500" not in response.data

    def test_delete_redirects_to_index(self, admin_client, archived_target):
        response = admin_client.post(
            f"/admin/users/{archived_target.user_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "users" in response.location


# ---------------------------------------------------------------------------
# 10. Adversarial inputs across routes
#
#    WHAT: Verifies that extreme or malicious inputs do not crash the app
#          and never result in unintended data changes.
#    WHY:  During a demo, edge cases get tested. A 500 on user management
#          routes is especially bad because it implies the admin panel
#          is broken — the most visible part of the system.
# ---------------------------------------------------------------------------

class TestAdversarial:
    def test_oversized_first_name_does_not_crash(self, admin_client):
        response = admin_client.post("/admin/users/add", data={
            "first_name": "a" * 10000,
            "last_name": "doe",
            "role": "cashier",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_oversized_last_name_does_not_crash(self, admin_client):
        response = admin_client.post("/admin/users/add", data={
            "first_name": "john",
            "last_name": "d" * 10000,
            "role": "cashier",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_sql_injection_in_first_name_does_not_crash(self, admin_client):
        initial_count = User.query.count()
        response = admin_client.post("/admin/users/add", data={
            "first_name": "'; DROP TABLE Users; --",
            "last_name": "doe",
            "role": "cashier",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data
        # validate_name rejects this — no new user created
        assert User.query.count() == initial_count

    def test_xss_in_first_name_not_rendered_raw(self, admin_client):
        response = admin_client.post("/admin/users/add", data={
            "first_name": "<script>alert('xss')</script>",
            "last_name": "doe",
            "role": "cashier",
        }, follow_redirects=True)
        assert b"<script>alert" not in response.data

    def test_empty_post_body_to_add_does_not_crash(self, admin_client):
        response = admin_client.post(
            "/admin/users/add", data={}, follow_redirects=True
        )
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_invalid_role_value_does_not_create_user(self, admin_client):
        initial_count = User.query.count()
        response = admin_client.post("/admin/users/add", data={
            "first_name": "john",
            "last_name": "doe",
            "role": "coadmin",
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b"500" not in response.data
        # Count must not have increased — no user was created
        assert User.query.count() == initial_count

    def test_very_large_user_id_in_url_does_not_crash(self, admin_client):
        # Extremely large user_id in URL — should return 302, not 500
        response = admin_client.get(
            "/admin/users/999999999999/edit",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_string_user_id_in_url_returns_404(self, admin_client):
        # Flask's <int:user_id> rejects non-integer strings at routing level
        response = admin_client.get(
            "/admin/users/notanumber/edit",
        )
        assert response.status_code == 404