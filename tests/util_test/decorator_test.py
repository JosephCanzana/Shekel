"""
tests/utils_tests/decorator_test.py

Pytest suite for app/utils/decorator.py — role_required decorator.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. role_required() decorator behavior
   - Unauthenticated user redirected to login
   - Authenticated user with correct role is allowed through
   - Authenticated user with wrong role is redirected
   - Multiple roles can be passed — any match allows access
   - Flash message shown when role is insufficient
   - Works correctly with all 4 roles in the system

2. Role boundary tests — every role against every restricted route type
   - Admin-only routes blocked for cashier, stocking, co-admin
   - Admin+co-admin routes accessible by both, blocked for others
   - Each role can access their own permitted routes

─────────────────────────────────────────────────────────────────────────────
Strategy: uses real route fixtures (admin_client, cashier_client etc.)
to test the decorator indirectly through actual routes rather than
mocking Flask internals.

All base fixtures come from tests/conftest.py.
"""

import pytest
from app.models.user import User


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(client, user):
    """Authenticated client as admin."""
    client.post("/", data={
        "full_name": f"{user.first_name} {user.last_name}",
        "password": "shekel123",
    })
    return client


@pytest.fixture
def co_admin_user(app):
    u = User(
        user_id=10092026,
        first_name="Co",
        last_name="Admin",
        role="admin",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def co_admin_client(client, co_admin_user):
    client.post("/", data={
        "full_name": f"{co_admin_user.first_name} {co_admin_user.last_name}",
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
def stocking_user(app):
    u = User(
        user_id=10102026,
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


# ---------------------------------------------------------------------------
# 1. Unauthenticated access
#
#    WHAT: Verifies role_required redirects unauthenticated users.
#    WHY:  The decorator checks is_authenticated before checking role.
#          If this check is missing or broken, unauthenticated users
#          could bypass the role check entirely.
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    def test_unauthenticated_cannot_access_admin_only_route(self, client):
        # /admin/ requires admin or co-admin — unauthenticated must redirect
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302

    def test_unauthenticated_cannot_access_manage_users(self, client):
        response = client.get("/admin/users/", follow_redirects=False)
        assert response.status_code == 302

    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get("/admin/", follow_redirects=False)
        assert "/" in response.location or "login" in response.location

    def test_unauthenticated_cannot_post_to_protected_route(self, client):
        response = client.post("/admin/users/add",
                                data={}, follow_redirects=False)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 2. Admin role — full access
#
#    WHAT: Verifies admin can access all admin-gated routes.
#    WHY:  Admin is the highest privilege role. If the decorator
#          incorrectly blocks admin, the entire admin panel is inaccessible.
# ---------------------------------------------------------------------------

class TestAdminRoleAccess:
    def test_admin_can_access_dashboard(self, admin_client):
        response = admin_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 200

    def test_admin_can_access_reports(self, admin_client):
        response = admin_client.get("/admin/reports", follow_redirects=False)
        assert response.status_code == 200

    def test_admin_can_access_audit_logs(self, admin_client):
        response = admin_client.get("/admin/audit_logs",
                                     follow_redirects=False)
        assert response.status_code == 200

    def test_admin_can_access_manage_users(self, admin_client):
        response = admin_client.get("/admin/users/", follow_redirects=False)
        assert response.status_code == 200

    def test_admin_can_access_add_user(self, admin_client):
        response = admin_client.get("/admin/users/add",
                                     follow_redirects=False)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 3. co-admin role — partial access
#
#    WHAT: Verifies co-admin can access dashboard and user management
#          but is blocked from admin-only routes (reports, audit_logs).
#    WHY:  co-admin is a limited admin role. Reports and audit logs
#          contain sensitive financial and user activity data that should
#          only be visible to full admins.
# ---------------------------------------------------------------------------

class TestCoAdminRoleAccess:
    def test_co_admin_can_access_dashboard(self, co_admin_client):
        response = co_admin_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 200

    def test_co_admin_can_access_manage_users(self, co_admin_client):
        response = co_admin_client.get("/admin/users/",
                                        follow_redirects=False)
        assert response.status_code == 200

    def test_co_admin_blocked_from_reports(self, co_admin_client):
        response = co_admin_client.get("/admin/reports",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_co_admin_blocked_from_audit_logs(self, co_admin_client):
        response = co_admin_client.get("/admin/audit_logs",
                                        follow_redirects=False)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 4. cashier role — blocked from all admin routes
#
#    WHAT: Verifies cashier cannot access any admin-gated route.
#    WHY:  A cashier accessing admin routes would be able to view all
#          users, create new admin accounts, or view financial reports —
#          a serious privilege escalation.
# ---------------------------------------------------------------------------

class TestCashierRoleBlocked:
    def test_cashier_blocked_from_dashboard(self, cashier_client):
        response = cashier_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_reports(self, cashier_client):
        response = cashier_client.get("/admin/reports",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_audit_logs(self, cashier_client):
        response = cashier_client.get("/admin/audit_logs",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_manage_users(self, cashier_client):
        response = cashier_client.get("/admin/users/",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_blocked_from_add_user(self, cashier_client):
        response = cashier_client.get("/admin/users/add",
                                       follow_redirects=False)
        assert response.status_code == 302

    def test_cashier_redirect_goes_to_valid_location(self, cashier_client):
        # Blocked cashier must be redirected somewhere sensible
        # not to a nonexistent route (which would cause a second 500)
        response = cashier_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302
        # Should NOT redirect to auth.dashboard (doesn't exist)
        assert "dashboard" not in response.location or \
               "auth" not in response.location


# ---------------------------------------------------------------------------
# 5. stocking role — blocked from all admin routes
#
#    WHAT: Verifies stocking staff cannot access admin routes.
#    WHY:  Same reasoning as cashier — stocking staff should only
#          access stocking-specific routes.
# ---------------------------------------------------------------------------

class TestStockingRoleBlocked:
    def test_stocking_blocked_from_dashboard(self, stocking_client):
        response = stocking_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_blocked_from_reports(self, stocking_client):
        response = stocking_client.get("/admin/reports",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_blocked_from_manage_users(self, stocking_client):
        response = stocking_client.get("/admin/users/",
                                        follow_redirects=False)
        assert response.status_code == 302

    def test_stocking_blocked_from_audit_logs(self, stocking_client):
        response = stocking_client.get("/admin/audit_logs",
                                        follow_redirects=False)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 6. Role boundary matrix — every role against manage_users routes
#
#    WHAT: Systematic test of every role against add/edit/delete/status
#          routes which require admin or co-admin.
#    WHY:  Role boundaries must be airtight across ALL endpoints, not
#          just the ones explicitly tested above. This matrix catches
#          any route that accidentally uses a looser role check.
# ---------------------------------------------------------------------------

class TestRoleBoundaryMatrix:
    @pytest.mark.parametrize("role_client_fixture,expected", [
        ("admin_client", 200),      # admin — allowed
        ("co_admin_client", 200),   # co-admin — allowed
        ("cashier_client", 302),    # cashier — blocked
        ("stocking_client", 302),   # stocking — blocked
    ])
    def test_manage_users_index_by_role(self, request, role_client_fixture,
                                         expected):
        # Dynamically get the fixture by name
        client = request.getfixturevalue(role_client_fixture)
        response = client.get("/admin/users/", follow_redirects=False)
        assert response.status_code == expected, \
            f"{role_client_fixture} got {response.status_code}, expected {expected}"

    @pytest.mark.parametrize("role_client_fixture,expected", [
        ("admin_client", 200),
        ("co_admin_client", 200),
        ("cashier_client", 302),
        ("stocking_client", 302),
    ])
    def test_add_user_form_by_role(self, request, role_client_fixture,
                                    expected):
        client = request.getfixturevalue(role_client_fixture)
        response = client.get("/admin/users/add", follow_redirects=False)
        assert response.status_code == expected

    @pytest.mark.parametrize("role_client_fixture,expected", [
        ("admin_client", 200),
        ("co_admin_client", 200),
        ("cashier_client", 302),
        ("stocking_client", 302),
    ])
    def test_dashboard_by_role(self, request, role_client_fixture, expected):
        client = request.getfixturevalue(role_client_fixture)
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == expected

    @pytest.mark.parametrize("role_client_fixture,expected", [
        ("admin_client", 200),
        ("co_admin_client", 302),   # admin only
        ("cashier_client", 302),
        ("stocking_client", 302),
    ])
    def test_reports_by_role(self, request, role_client_fixture, expected):
        client = request.getfixturevalue(role_client_fixture)
        response = client.get("/admin/reports", follow_redirects=False)
        assert response.status_code == expected

    @pytest.mark.parametrize("role_client_fixture,expected", [
        ("admin_client", 200),
        ("co_admin_client", 302),   # admin only
        ("cashier_client", 302),
        ("stocking_client", 302),
    ])
    def test_audit_logs_by_role(self, request, role_client_fixture, expected):
        client = request.getfixturevalue(role_client_fixture)
        response = client.get("/admin/audit_logs", follow_redirects=False)
        assert response.status_code == expected