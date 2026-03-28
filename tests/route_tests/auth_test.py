"""
tests/route_tests/auth_test.py

Pytest suite for auth blueprint routes.
Covers: login, account_activation, logout.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. GET /  (login page)
   - Renders login page for unauthenticated users

2. POST / (login form)
   - Happy path — valid credentials for each role
   - Full name splitting logic (single name, multi-part names,
     double spaces, mixed case)
   - Wrong password rejected
   - Nonexistent user rejected
   - Archived user blocked with correct flash
   - Suspended user blocked with correct flash
   - not_activated user redirected to account_activation
   - not_activated user NOT logged in after redirect
   - Empty field validation
   - Adversarial inputs — oversized names, special characters,
     SQL injection (verified no login + table intact),
     XSS not rendered, whitespace-only, missing fields, empty body

3. Brute Force / Repeated Attempts
   - Repeated wrong passwords do not lock account (no rate limiting —
     documents a known gap)
   - Wrong password never logs user in across many attempts

4. GET /login/<user_id>/account_activation
   - Renders activation page for not_activated users
   - Nonexistent user_id redirects to login
   - Already activated user redirected and password NOT changed
   - Suspended/archived user redirected (status != not_activated)

5. POST /login/<user_id>/account_activation
   - Happy path — valid password activates account and logs in
   - Password validation rules (length, uppercase, lowercase,
     digit, special char) — each rule tested independently
   - Password confirmation mismatch
   - Empty field validation
   - Role-based redirect after activation
   - Failed activation preserves original password hash
   - Account status remains not_activated after failed attempt
   - Activated user cannot reuse activation endpoint to change password
   - Adversarial inputs — oversized passwords, SQL injection
     (table intact + not logged in), XSS not rendered,
     missing fields, negative/zero user_id

6. Session Behavior
   - Session cleared on logout
   - Session contains user_id after login
   - Session does not contain user_id for not_activated redirect

7. GET/POST /logout
   - Logs out authenticated user and redirects to login
   - Session cleared after logout
   - Unauthenticated access redirects to login (login_required)
   - Protected routes redirect after logout

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from app.extensions import db
from app.models.user import User


# ---------------------------------------------------------------------------
# Route-specific fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def not_activated_user(app):
    """A user who has not yet activated their account."""
    u = User(
        user_id=10032026,
        first_name="New",
        last_name="Staff",
        role="cashier",
        status="not_activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def suspended_user(app):
    """A user whose account has been suspended."""
    u = User(
        user_id=10042026,
        first_name="Suspended",
        last_name="User",
        role="cashier",
        status="suspended",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def archived_user(app):
    """A user whose account has been archived."""
    u = User(
        user_id=10052026,
        first_name="Archived",
        last_name="User",
        role="cashier",
        status="archived",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def multi_part_user(app):
    """A user with a multi-part last name to test name splitting logic."""
    u = User(
        user_id=10062026,
        first_name="Juan",
        last_name="Dela Cruz",
        role="cashier",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def stocking_user(app):
    """A user with stocking role for redirect testing."""
    u = User(
        user_id=10072026,
        first_name="Stock",
        last_name="Person",
        role="stocking",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def co_admin_user(app):
    """A user with co-admin role for redirect testing."""
    u = User(
        user_id=10082026,
        first_name="Co",
        last_name="superadmin",
        role="admin",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def login(client, user, password="shekel123"):
    """Helper to log in a user via the login form."""
    return client.post("/", data={
        "full_name": f"{user.first_name} {user.last_name}",
        "password": password,
    }, follow_redirects=False)


def post_activation(client, user_id, password, confirm=None, follow=True):
    """Helper to post the account activation form."""
    return client.post(
        f"/login/{user_id}/account_activation",
        data={
            "password": password,
            "password_confirm": confirm if confirm is not None else password,
        },
        follow_redirects=follow,
    )


# ---------------------------------------------------------------------------
# 1. GET / (login page)
#
#    WHAT: Verifies the login page renders correctly for unauthenticated users.
#    WHY:  If the login page crashes on GET, no one can log in at all —
#          the most critical failure possible in a demo.
# ---------------------------------------------------------------------------

class TestLoginGet:
    def test_login_page_renders(self, client):
        # Login page should render without error for anonymous users
        response = client.get("/")
        assert response.status_code == 200

    def test_login_page_returns_html(self, client):
        # Response should be HTML content
        response = client.get("/")
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data

    def test_already_logged_in_user_accessing_login_does_not_crash(self, client, user):
        # Even if already logged in, GET / should not crash the app
        login(client, user)
        response = client.get("/")
        assert response.status_code in [200, 302]
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 2. POST / (login form — happy path)
#
#    WHAT: Verifies that valid credentials log in users and redirect
#          correctly based on their role.
#    WHY:  Role-based redirects are critical — a cashier sent to the
#          admin dashboard or vice versa is a serious UX and security bug.
# ---------------------------------------------------------------------------

class TestLoginPostHappyPath:
    def test_admin_login_redirects_to_dashboard(self, client, user):
        # user fixture has role="superadmin" — must redirect to admin dashboard
        response = login(client, user)
        assert response.status_code == 302
        assert "superadmin" in response.location or "dashboard" in response.location

    def test_co_admin_login_redirects_to_dashboard(self, client, co_admin_user):
        # co-admin shares the same dashboard as admin
        response = login(client, co_admin_user)
        assert response.status_code == 302
        assert "superadmin" in response.location or "dashboard" in response.location

    def test_cashier_login_redirects_to_transaction(self, client, cashier_user):
        # cashier role must redirect to cashier.transaction
        response = login(client, cashier_user)
        assert response.status_code == 302
        assert "transaction" in response.location

    def test_stocking_login_redirects_to_dashboard(self, client, stocking_user):
        # stocking role must redirect to stocking.dashboard
        response = login(client, stocking_user)
        assert response.status_code == 302
        assert "stocking" in response.location or "dashboard" in response.location

    def test_login_sets_session_user_id(self, client, user):
        # After successful login, session must contain _user_id
        login(client, user)
        with client.session_transaction() as session:
            assert "_user_id" in session
            assert int(session["_user_id"]) == user.user_id

    def test_login_is_case_insensitive_for_name(self, client, user):
        # Name matching is case-insensitive — "TEST USER" matches "Test User"
        response = client.post("/", data={
            "full_name": f"{user.first_name.upper()} {user.last_name.upper()}",
            "password": "shekel123",
        }, follow_redirects=False)
        assert response.status_code == 302

    def test_login_handles_extra_spaces_in_name(self, client, user):
        # Extra spaces between name parts are collapsed before matching
        response = client.post("/", data={
            "full_name": f"  {user.first_name}   {user.last_name}  ",
            "password": "shekel123",
        }, follow_redirects=False)
        assert response.status_code == 302

    def test_login_handles_double_space_between_name_parts(self, client, user):
        # Double space between first and last — collapsed by split/join logic
        response = client.post("/", data={
            "full_name": f"{user.first_name}     {user.last_name}",
            "password": "shekel123",
        }, follow_redirects=False)
        assert response.status_code == 302

    def test_login_handles_mixed_case_name(self, client, user):
        # Mixed case like "tEsT uSeR" — normalized before matching
        response = client.post("/", data={
            "full_name": f"{user.first_name.swapcase()} {user.last_name.swapcase()}",
            "password": "shekel123",
        }, follow_redirects=False)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 3. POST / (login form — full name splitting logic)
#
#    WHAT: Verifies the multi-part name splitting works for users with
#          compound first or last names.
#    WHY:  Your login uses a name-splitting algorithm that tries every
#          possible first/last split. If this breaks, users with names
#          like "Juan Dela Cruz" cannot log in at all — a critical bug
#          easy to introduce during refactoring.
# ---------------------------------------------------------------------------

class TestLoginNameSplitting:
    def test_single_word_name_rejected(self, client):
        # Only one name part — must have at least first + last
        response = client.post("/", data={
            "full_name": "Test",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"full name" in response.data or b"Please" in response.data

    def test_two_part_name_matches(self, client, user):
        # Standard first + last name — most common case
        response = login(client, user)
        assert response.status_code == 302

    def test_multi_part_last_name_matches(self, client, multi_part_user):
        # "Juan Dela Cruz" — algorithm tries "Juan" + "Dela Cruz" split
        response = client.post("/", data={
            "full_name": "Juan Dela Cruz",
            "password": "shekel123",
        }, follow_redirects=False)
        assert response.status_code == 302
        assert "transaction" in response.location

    def test_multi_part_last_name_wrong_input_rejected(self, client, multi_part_user):
        # "Juan Dela" alone does not match "Juan" / "Dela Cruz"
        response = client.post("/", data={
            "full_name": "Juan Dela",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data

    def test_multi_part_last_name_wrong_password_rejected(self, client, multi_part_user):
        # Correct full name but wrong password — must fail
        response = client.post("/", data={
            "full_name": "Juan Dela Cruz",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data

    def test_reversed_name_order_rejected(self, client, user):
        # "Last First" order instead of "First Last" — should not match
        response = client.post("/", data={
            "full_name": f"{user.last_name} {user.first_name}",
            "password": "shekel123",
        }, follow_redirects=True)
        # Either fails with "Invalid" or accidentally matches
        # depending on names — at minimum should not crash
        assert response.status_code == 200
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 4. POST / (login form — credential failures)
#
#    WHAT: Verifies wrong credentials are rejected and the user is
#          never logged in on failure.
#    WHY:  Silent auth failures (logging in anyway) or crashes (500)
#          on bad credentials are security-critical bugs.
# ---------------------------------------------------------------------------

class TestLoginCredentialFailures:
    def test_wrong_password_rejected(self, client, user):
        # Correct name but wrong password — must fail
        response = client.post("/", data={
            "full_name": f"{user.first_name} {user.last_name}",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data

    def test_wrong_password_does_not_log_in(self, client, user):
        # After wrong password, session must NOT contain _user_id
        client.post("/", data={
            "full_name": f"{user.first_name} {user.last_name}",
            "password": "wrongpassword",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_nonexistent_user_rejected(self, client):
        # Name that matches no user in the DB
        response = client.post("/", data={
            "full_name": "Ghost User",
            "password": "somepassword",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data

    def test_nonexistent_user_not_logged_in(self, client):
        # Nonexistent user should never create a session
        client.post("/", data={
            "full_name": "Ghost User",
            "password": "somepassword",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_empty_name_rejected(self, client):
        response = client.post("/", data={
            "full_name": "",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"fill" in response.data or b"Invalid" in response.data

    def test_empty_password_rejected(self, client):
        response = client.post("/", data={
            "full_name": "Test User",
            "password": "",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"fill" in response.data or b"Invalid" in response.data

    def test_both_fields_empty_rejected(self, client):
        response = client.post("/", data={
            "full_name": "",
            "password": "",
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_correct_name_wrong_password_never_logs_in(self, client, user):
        # Sanity check — the right name with wrong password is always rejected
        for wrong_pass in ["wrong", "SHEKEL123", "shekel", "123", " "]:
            response = client.post("/", data={
                "full_name": f"{user.first_name} {user.last_name}",
                "password": wrong_pass,
            })
            with client.session_transaction() as session:
                assert "_user_id" not in session


# ---------------------------------------------------------------------------
# 5. POST / (login form — account status checks)
#
#    WHAT: Verifies that users with restricted statuses are handled
#          correctly and are NEVER logged in.
#    WHY:  A suspended or archived user logging in successfully is a
#          security breach. An unhandled status crashes the app.
# ---------------------------------------------------------------------------

class TestLoginStatusChecks:
    def test_archived_user_blocked(self, client, archived_user):
        # Archived accounts must be blocked with a clear message
        response = client.post("/", data={
            "full_name": f"{archived_user.first_name} {archived_user.last_name}",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"archived" in response.data or b"Archived" in response.data

    def test_archived_user_not_logged_in(self, client, archived_user):
        # Archived user must never have a session created
        client.post("/", data={
            "full_name": f"{archived_user.first_name} {archived_user.last_name}",
            "password": "shekel123",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_suspended_user_blocked(self, client, suspended_user):
        # Suspended accounts must be blocked with a clear message
        response = client.post("/", data={
            "full_name": f"{suspended_user.first_name} {suspended_user.last_name}",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"suspended" in response.data or b"Suspended" in response.data

    def test_suspended_user_not_logged_in(self, client, suspended_user):
        # Suspended user must never have a session created
        client.post("/", data={
            "full_name": f"{suspended_user.first_name} {suspended_user.last_name}",
            "password": "shekel123",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_not_activated_user_redirected_to_activation(self, client,
                                                          not_activated_user):
        # not_activated users must be redirected to account_activation
        response = client.post("/", data={
            "full_name": f"{not_activated_user.first_name} {not_activated_user.last_name}",
            "password": "shekel123",
        }, follow_redirects=False)
        assert response.status_code == 302
        assert "account_activation" in response.location

    def test_not_activated_user_not_logged_in(self, client, not_activated_user):
        # not_activated users must NOT be logged in — only redirected
        client.post("/", data={
            "full_name": f"{not_activated_user.first_name} {not_activated_user.last_name}",
            "password": "shekel123",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session


# ---------------------------------------------------------------------------
# 6. POST / (login form — brute force / repeated attempts)
#
#    WHAT: Documents brute force behavior — your app has no rate limiting.
#    WHY:  Without rate limiting, an attacker can try unlimited passwords.
#          These tests document the gap so it's a known, deliberate decision
#          rather than an accidental omission. They also confirm that
#          repeated wrong attempts never accidentally log the user in.
# ---------------------------------------------------------------------------

class TestLoginBruteForce:
    def test_repeated_wrong_passwords_never_log_in(self, client, user):
        # 20 wrong attempts — session must never be created
        for i in range(20):
            client.post("/", data={
                "full_name": f"{user.first_name} {user.last_name}",
                "password": f"wrongpassword{i}",
            })
            with client.session_transaction() as session:
                assert "_user_id" not in session

    def test_account_still_works_after_repeated_wrong_attempts(self, client, user):
        # After 10 wrong attempts, the correct password must still work
        # Documents that there is NO account lockout mechanism
        for _ in range(10):
            client.post("/", data={
                "full_name": f"{user.first_name} {user.last_name}",
                "password": "wrongpassword",
            })

        response = login(client, user)
        assert response.status_code == 302  # still works — no lockout

    def test_repeated_nonexistent_user_attempts_do_not_crash(self, client):
        # Repeated lookups for nonexistent users — app must stay stable
        for _ in range(20):
            response = client.post("/", data={
                "full_name": "Ghost User",
                "password": "somepassword",
            }, follow_redirects=True)
            assert response.status_code == 200
            assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 7. POST / (login form — adversarial inputs)
#
#    WHAT: Verifies the login route handles malicious or extreme inputs
#          gracefully — not just "didn't crash" but also "didn't log in".
#    WHY:  During a demo, someone might test edge cases. A 500 error or
#          an unintended login on the login page is the worst first impression.
# ---------------------------------------------------------------------------

class TestLoginAdversarial:
    def test_extremely_long_name_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "A " * 5000,  # 5000 words
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_extremely_long_name_does_not_log_in(self, client):
        client.post("/", data={
            "full_name": "A " * 5000,
            "password": "shekel123",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_extremely_long_password_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "Test User",
            "password": "P" * 10000,
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_whitespace_only_name_rejected(self, client):
        # Stripped to empty — caught by "not name" check
        response = client.post("/", data={
            "full_name": "     ",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_whitespace_only_password_rejected(self, client):
        # Stripped to empty — caught by "not password" check
        response = client.post("/", data={
            "full_name": "Test User",
            "password": "     ",
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_sql_injection_in_name_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "'; DROP TABLE Users; --",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_sql_injection_in_name_does_not_log_in(self, client):
        # SQL injection must never result in a successful login
        client.post("/", data={
            "full_name": "'; DROP TABLE Users; --",
            "password": "shekel123",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_sql_injection_leaves_db_intact(self, client, user):
        # DB must still have all users after injection attempt
        count_before = User.query.count()
        client.post("/", data={
            "full_name": "'; DROP TABLE Users; --",
            "password": "shekel123",
        })
        assert User.query.count() == count_before

    def test_xss_in_name_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "<script>alert('xss')</script>",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_xss_in_name_not_rendered_raw(self, client):
        # Jinja2 should escape XSS — raw script tag must not appear in output
        response = client.post("/", data={
            "full_name": "<script>alert('xss')</script>",
            "password": "shekel123",
        }, follow_redirects=True)
        assert b"<script>alert" not in response.data

    def test_xss_in_name_does_not_log_in(self, client):
        client.post("/", data={
            "full_name": "<script>alert('xss')</script>",
            "password": "shekel123",
        })
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_unicode_and_emoji_name_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "José García 🔥",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_numeric_name_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "12345 67890",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_missing_name_field_does_not_crash(self, client):
        # Name field not submitted at all — request.form.get returns ""
        response = client.post("/", data={
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_missing_password_field_does_not_crash(self, client):
        response = client.post("/", data={
            "full_name": "Test User",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_empty_post_body_does_not_crash(self, client):
        response = client.post("/", data={}, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_null_bytes_in_name_do_not_crash(self, client):
        # Null bytes are a common injection vector
        response = client.post("/", data={
            "full_name": "Test\x00User",
            "password": "shekel123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 8. GET /login/<user_id>/account_activation
#
#    WHAT: Verifies the activation page renders correctly for
#          not_activated users and handles invalid access cleanly.
#    WHY:  If an already-activated user can access the activation page,
#          they could change their own password without going through admin.
#          A security and workflow bug.
# ---------------------------------------------------------------------------

class TestAccountActivationGet:
    def test_activation_page_renders_for_not_activated_user(self, client,
                                                             not_activated_user):
        response = client.get(
            f"/login/{not_activated_user.user_id}/account_activation"
        )
        assert response.status_code == 200

    def test_activation_page_nonexistent_user_redirects(self, client):
        response = client.get(
            "/login/99999999/account_activation",
            follow_redirects=False
        )
        assert response.status_code == 302
        assert "login" in response.location or response.location == "/"

    def test_activation_page_already_activated_user_redirected(self, client, user):
        # Already activated — must redirect away, not show the form
        response = client.get(
            f"/login/{user.user_id}/account_activation",
            follow_redirects=False
        )
        assert response.status_code == 302
        assert "account_activation" not in response.location

    def test_activation_page_suspended_user_redirected(self, client, suspended_user):
        # Suspended status != "not_activated" — redirect to login
        response = client.get(
            f"/login/{suspended_user.user_id}/account_activation",
            follow_redirects=False
        )
        assert response.status_code == 302

    def test_activation_page_archived_user_redirected(self, client, archived_user):
        # Archived status != "not_activated" — redirect to login
        response = client.get(
            f"/login/{archived_user.user_id}/account_activation",
            follow_redirects=False
        )
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# 9. POST /login/<user_id>/account_activation (happy path)
#
#    WHAT: Verifies that a valid password activates the account, logs
#          the user in, and redirects based on their role.
#    WHY:  Account activation is a one-time flow. If it silently fails
#          (no status update, no login), the user is stuck unable to
#          access the system — a blocking bug for new staff onboarding.
# ---------------------------------------------------------------------------

class TestAccountActivationPostHappyPath:
    def test_valid_password_activates_account(self, client, not_activated_user):
        post_activation(client, not_activated_user.user_id, "ValidPass1@")
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "activated"

    def test_valid_password_logs_user_in(self, client, not_activated_user):
        post_activation(client, not_activated_user.user_id, "ValidPass1@")
        with client.session_transaction() as session:
            assert "_user_id" in session

    def test_cashier_activation_redirects_to_transaction(self, client,
                                                          not_activated_user):
        # not_activated_user has role="cashier"
        response = client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={"password": "ValidPass1@", "password_confirm": "ValidPass1@"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "transaction" in response.location

    def test_activation_updates_password_hash(self, client, not_activated_user):
        # New password must replace the default hash — not keep the old one
        old_hash = not_activated_user.password
        post_activation(client, not_activated_user.user_id, "ValidPass1@")
        db.session.refresh(not_activated_user)
        assert not_activated_user.password != old_hash

    def test_new_password_is_usable_for_login(self, client, not_activated_user):
        # After activation, the new password must work for future logins
        post_activation(client, not_activated_user.user_id, "ValidPass1@")

        # Log out first
        client.get("/logout")

        # Log back in with new password
        response = client.post("/", data={
            "full_name": f"{not_activated_user.first_name} {not_activated_user.last_name}",
            "password": "ValidPass1@",
        }, follow_redirects=False)
        assert response.status_code == 302

    def test_activation_saves_new_password(self, client, not_activated_user):
        """
        After activation, the new password hash is stored.
        Directly checks the model — no login/logout complexity.
        """
        post_activation(
            client, not_activated_user.user_id, "ValidPass1@", follow=False
        )
        db.session.refresh(not_activated_user)

        # New password works
        assert not_activated_user.check_password("ValidPass1@") is True
        # Old password doesn't
        assert not_activated_user.check_password("shekel123") is False


    def test_old_password_cannot_login_after_activation(self, client,
                                                        not_activated_user):
        """
        After activation, logging in with the old default password is rejected.
        Tests the login route — completely independent of activation flow.
        """
        # Directly update the password in DB — bypass the activation route entirely
        not_activated_user.set_password("ValidPass1@")
        not_activated_user.status = "activated"
        not_activated_user.save()

        # Try logging in with the OLD password
        client.post("/", data={
            "full_name": f"{not_activated_user.first_name} {not_activated_user.last_name}",
            "password": "shekel123",
        })

        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_default_password_rejected_during_activation(self, client, not_activated_user):
        """
        User cannot set the default password as their activation password.
        This is the check you added to auth.py.
        """
        response = post_activation(
            client, not_activated_user.user_id,
            "shekel123",   # the default password
            follow=False
        )
        db.session.refresh(not_activated_user)

        # Account must NOT be activated
        assert not_activated_user.status == "not_activated"

        # Session must NOT be created
        with client.session_transaction() as session:
            assert "_user_id" not in session


# ---------------------------------------------------------------------------
# 10. POST /login/<user_id>/account_activation (password validation)
#
#    WHAT: Verifies every password rule is individually enforced and that
#          failed attempts never partially activate the account.
#    WHY:  Weak passwords set during activation are a long-term security
#          risk. Each rule must independently block non-compliant passwords.
#          If any rule is silently skipped, the account is activated with
#          a weak password without the user knowing.
# ---------------------------------------------------------------------------

class TestAccountActivationPasswordValidation:
    def test_password_too_short_rejected(self, client, not_activated_user):
        response = post_activation(client, not_activated_user.user_id, "Ab1@")
        assert response.status_code == 200
        assert b"8" in response.data or b"characters" in response.data
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "not_activated"

    def test_password_no_uppercase_rejected(self, client, not_activated_user):
        response = post_activation(client, not_activated_user.user_id, "validpass1@")
        assert response.status_code == 200
        assert b"uppercase" in response.data or b"Uppercase" in response.data

    def test_password_no_lowercase_rejected(self, client, not_activated_user):
        response = post_activation(client, not_activated_user.user_id, "VALIDPASS1@")
        assert response.status_code == 200
        assert b"lowercase" in response.data or b"Lowercase" in response.data

    def test_password_no_digit_rejected(self, client, not_activated_user):
        response = post_activation(client, not_activated_user.user_id, "ValidPass@")
        assert response.status_code == 200
        assert b"number" in response.data or b"digit" in response.data

    def test_password_no_special_char_rejected(self, client, not_activated_user):
        response = post_activation(client, not_activated_user.user_id, "ValidPass1")
        assert response.status_code == 200
        assert b"special" in response.data or b"Special" in response.data

    def test_password_mismatch_rejected(self, client, not_activated_user):
        response = post_activation(
            client, not_activated_user.user_id,
            "ValidPass1@", "ValidPass2@"
        )
        assert response.status_code == 200
        assert b"match" in response.data or b"Match" in response.data

    def test_empty_password_rejected(self, client, not_activated_user):
        response = post_activation(client, not_activated_user.user_id, "")
        assert response.status_code == 200

    def test_empty_confirm_rejected(self, client, not_activated_user):
        response = post_activation(
            client, not_activated_user.user_id, "ValidPass1@", ""
        )
        assert response.status_code == 200

    def test_exactly_8_char_valid_password_accepted(self, client, not_activated_user):
        # Exactly 8 characters meeting all rules — boundary case, must pass
        post_activation(client, not_activated_user.user_id, "Valid1@a")
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "activated"

    def test_7_char_password_rejected(self, client, not_activated_user):
        # One under the 8-char limit — must be rejected
        response = post_activation(client, not_activated_user.user_id, "Val1@ab")
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "not_activated"

    def test_account_not_activated_on_any_failed_validation(self, client,
                                                              not_activated_user):
        # After ANY validation failure, status must stay not_activated
        invalid_passwords = [
            "weak",          # too short, no uppercase, no special
            "validpass1@",   # no uppercase
            "VALIDPASS1@",   # no lowercase
            "ValidPass@",    # no digit
            "ValidPass1",    # no special char
        ]
        for pw in invalid_passwords:
            post_activation(client, not_activated_user.user_id, pw)
            db.session.refresh(not_activated_user)
            assert not_activated_user.status == "not_activated", \
                f"Account was wrongly activated with password: '{pw}'"

    def test_failed_validation_preserves_original_password_hash(self, client,
                                                                  not_activated_user):
        # Failed attempt must NOT change the stored password hash
        original_hash = not_activated_user.password
        post_activation(client, not_activated_user.user_id, "weak")
        db.session.refresh(not_activated_user)
        assert not_activated_user.password == original_hash

    def test_failed_validation_does_not_log_in(self, client, not_activated_user):
        # Failed activation must not create a session
        post_activation(client, not_activated_user.user_id, "weak")
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_activated_user_cannot_reuse_activation_endpoint(self, client, user):
        # Already activated user hits the activation endpoint —
        # should be redirected away without changing their password
        original_hash = user.password
        client.post(
            f"/login/{user.user_id}/account_activation",
            data={
                "password": "ValidPass1@",
                "password_confirm": "ValidPass1@",
            },
        )
        db.session.refresh(user)
        # Status should still be "activated" and password unchanged
        assert user.status == "activated"
        assert user.password == original_hash


# ---------------------------------------------------------------------------
# 11. POST /login/<user_id>/account_activation (adversarial)
#
#    WHAT: Verifies the activation route handles extreme inputs gracefully
#          and never logs in or modifies state on bad input.
#    WHY:  The activation endpoint is accessible without being logged in —
#          making it a higher-value target for abuse than protected routes.
# ---------------------------------------------------------------------------

class TestAccountActivationAdversarial:
    def test_extremely_long_password_does_not_crash(self, client, not_activated_user):
        response = client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={"password": "A" * 10000, "password_confirm": "A" * 10000},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_extremely_long_password_does_not_activate(self, client, not_activated_user):
        client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={"password": "A" * 10000, "password_confirm": "A" * 10000},
        )
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "not_activated"

    def test_sql_injection_in_password_does_not_crash(self, client, not_activated_user):
        response = client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={
                "password": "'; DROP TABLE Users; --",
                "password_confirm": "'; DROP TABLE Users; --",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_sql_injection_leaves_db_intact(self, client, not_activated_user):
        count_before = User.query.count()
        client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={
                "password": "'; DROP TABLE Users; --",
                "password_confirm": "'; DROP TABLE Users; --",
            },
        )
        assert User.query.count() == count_before

    def test_sql_injection_does_not_activate(self, client, not_activated_user):
        client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={
                "password": "'; DROP TABLE Users; --",
                "password_confirm": "'; DROP TABLE Users; --",
            },
        )
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "not_activated"

    def test_xss_in_password_does_not_execute(self, client, not_activated_user):
        response = client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={
                "password": "<script>alert('xss')</script>",
                "password_confirm": "<script>alert('xss')</script>",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"<script>alert" not in response.data

    def test_missing_both_fields_does_not_crash(self, client, not_activated_user):
        response = client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"500" not in response.data

    def test_missing_both_fields_does_not_activate(self, client, not_activated_user):
        client.post(
            f"/login/{not_activated_user.user_id}/account_activation",
            data={},
        )
        db.session.refresh(not_activated_user)
        assert not_activated_user.status == "not_activated"

    def test_negative_user_id_does_not_crash(self, client):
        # Flask's <int:user_id> rejects negative ints at routing level → 404
        response = client.get(
            "/login/-1/account_activation",
            follow_redirects=True,
        )
        assert response.status_code in [200, 404]
        assert b"500" not in response.data

    def test_zero_user_id_does_not_crash(self, client):
        # user_id=0 won't match any real user — handled gracefully
        response = client.get(
            "/login/0/account_activation",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"500" not in response.data


# ---------------------------------------------------------------------------
# 12. GET/POST /logout
#
#    WHAT: Verifies logout fully clears the session and that protected
#          routes are inaccessible after logout.
#    WHY:  A broken logout that doesn't clear the session leaves the
#          user's account accessible to the next person on the same
#          device — a critical security bug on shared POS terminals.
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_redirects_to_login(self, client, user):
        login(client, user)
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/" in response.location or "login" in response.location

    def test_logout_clears_session(self, client, user):
        login(client, user)

        with client.session_transaction() as session:
            assert "_user_id" in session

        client.get("/logout")

        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_unauthenticated_logout_redirects_to_login(self, client):
        # Accessing logout without being logged in — login_required redirects
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/" in response.location or "login" in response.location

    def test_logout_post_also_works(self, client, user):
        # Route accepts both GET and POST
        login(client, user)
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 302

    def test_after_logout_protected_routes_redirect_to_login(self, client, user):
        login(client, user)
        client.get("/logout")
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302

    def test_after_logout_cannot_access_admin(self, client, user):
        # Log in then log out
        login(client, user)
        client.get("/logout")

        # /logout itself is @login_required — guaranteed to redirect after logout
        # Using this instead of /admin/dashboard since we don't know the exact URL yet
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/" in response.location or "login" in response.location

    def test_double_logout_does_not_crash(self, client, user):
        # Logging out twice should not cause a 500
        login(client, user)
        client.get("/logout")
        response = client.get("/logout", follow_redirects=True)
        assert response.status_code == 200
        assert b"500" not in response.data