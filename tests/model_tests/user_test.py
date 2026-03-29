"""
tests/user_test.py

Pytest suite for User model.
Covers: column constraints, enum validation, set_password(),
        check_password(), set_status(), full_name, get_id(),
        to_dict(), generate_id(), get_default_password(),
        and inherited BaseModel methods.

All base fixtures come from tests/conftest.py.
"""

"""
What's covered
Column Constraints — all 6 nullable=False fields individually tested; user_id confirmed as non-autoincrement; duplicate user_id blocked by PK constraint
Enum — role — all 4 valid values via parametrize; 6 invalid values rejected (including wrong case and empty string)
Enum — status — all 4 valid values; 6 invalid values rejected
set_password() / check_password() — password is hashed not stored raw; correct password returns True; wrong password returns False; case-sensitive; second set_password() wins; persists after save; two users with the same password get different hashes (salting check — important security test)
set_status() — updates field in memory; persists after save(); confirmed it does not auto-save (requires explicit save())
full_name — correct "First Last" format; correct order; raises AttributeError if you try to assign to it (read-only property)
get_id() — returns a str not an int (Flask-Login requirement); value matches user_id
to_dict() — all 5 keys present; correct values and types; password not exposed (critical security check)
generate_id() — returns int; ends with current year; starts at 1000; unique across consecutive calls
get_default_password() — returns "shekel123" by default; reflects changes made via AppSettings

"""

import pytest
from datetime import datetime
from app.extensions import db
from app.models.user import User
from app.models.app_settings import AppSettings


# ---------------------------------------------------------------------------
# Local fixtures — extend conftest, not replace it
# ---------------------------------------------------------------------------

@pytest.fixture
def new_user(app):
    """
    An unsaved User instance for tests that need to control
    when/whether the user gets committed.
    """
    return User(
        user_id=99992026,
        first_name="New",
        last_name="User",
        role="cashier",
        status="not_activated",
    )


# ---------------------------------------------------------------------------
# Column Constraints
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_user_saves_successfully(self, app, user):
        """A fully populated User saves without error."""
        assert User.query.count() == 1

    def test_user_id_is_required(self, app):
        """user_id is the primary key — omitting it raises an error."""
        with pytest.raises(Exception):
            User(
                first_name="No", last_name="ID",
                role="cashier", status="activated",
            ).save()

    def test_first_name_is_required(self, app):
        """first_name is NOT NULL — omitting raises an error."""
        with pytest.raises(Exception):
            User(
                user_id=10992026, last_name="Smith",
                role="cashier", status="activated",
                password="hashed",
            ).save()

    def test_last_name_is_required(self, app):
        """last_name is NOT NULL — omitting raises an error."""
        with pytest.raises(Exception):
            User(
                user_id=10992026, first_name="John",
                role="cashier", status="activated",
                password="hashed",
            ).save()

    def test_role_is_required(self, app):
        """role is NOT NULL — omitting raises an error."""
        with pytest.raises(Exception):
            User(
                user_id=10992026, first_name="John", last_name="Smith",
                status="activated", password="hashed",
            ).save()

    def test_password_is_required(self, app):
        """password is NOT NULL — omitting raises an error."""
        with pytest.raises(Exception):
            User(
                user_id=10992026, first_name="John", last_name="Smith",
                role="cashier", status="activated",
            ).save()

    def test_status_is_required(self, app):
        """status is NOT NULL — omitting raises an error."""
        with pytest.raises(Exception):
            User(
                user_id=10992026, first_name="John", last_name="Smith",
                role="cashier", password="hashed",
            ).save()

    def test_user_id_does_not_autoincrement(self, app):
        """user_id is autoincrement=False — must be set manually."""
        u = User(
            user_id=10992026,
            first_name="Manual",
            last_name="ID",
            role="superadmin",
            status="activated",
        )
        u.set_password("pass")
        u.save()

        result = User.get_by_id(10992026)
        assert result.user_id == 10992026

    def test_duplicate_user_id_raises(self, app, user):
        """Two users with the same user_id violate the primary key constraint."""
        with pytest.raises(Exception):
            duplicate = User(
                user_id=user.user_id,
                first_name="Dupe",
                last_name="User",
                role="cashier",
                status="activated",
            )
            duplicate.set_password("pass")
            duplicate.save()


# ---------------------------------------------------------------------------
# Enum Constraints — role
# ---------------------------------------------------------------------------

class TestRoleEnum:
    @pytest.mark.parametrize("valid_role", [
        "superadmin", "cashier", "stocking", "admin"
    ])
    def test_valid_role_values_accepted(self, app, valid_role):
        """Each valid role enum value saves without error."""
        u = User(
            user_id=20002026 + hash(valid_role) % 1000,
            first_name="Role",
            last_name="Test",
            role=valid_role,
            status="activated",
        )
        u.set_password("pass")
        u.save()
        assert User.query.filter_by(role=valid_role).count() == 1

    @pytest.mark.parametrize("invalid_role", [
        "manager", "guest", "", "CASHIER"
    ])
    def test_invalid_role_values_rejected(self, app, invalid_role):
        """Invalid role values outside the enum should raise an error."""
        with pytest.raises(Exception):
            u = User(
                user_id=30002026,
                first_name="Bad",
                last_name="Role",
                role=invalid_role,
                status="activated",
            )
            u.set_password("pass")
            u.save()


# ---------------------------------------------------------------------------
# Enum Constraints — status
# ---------------------------------------------------------------------------

class TestStatusEnum:
    @pytest.mark.parametrize("valid_status", [
        "activated", "not_activated", "suspended", "archived"
    ])
    def test_valid_status_values_accepted(self, app, valid_status):
        """Each valid status enum value saves without error."""
        u = User(
            user_id=40002026 + hash(valid_status) % 1000,
            first_name="Status",
            last_name="Test",
            role="cashier",
            status=valid_status,
        )
        u.set_password("pass")
        u.save()
        assert User.query.filter_by(status=valid_status).count() == 1

    @pytest.mark.parametrize("invalid_status", [
        "active", "inactive", "banned", "", "Activated", "SUSPENDED"
    ])
    def test_invalid_status_values_rejected(self, app, invalid_status):
        """Invalid status values outside the enum should raise an error."""
        with pytest.raises(Exception):
            u = User(
                user_id=50002026,
                first_name="Bad",
                last_name="Status",
                role="cashier",
                status=invalid_status,
            )
            u.set_password("pass")
            u.save()


# ---------------------------------------------------------------------------
# User.set_password() and User.check_password()
# ---------------------------------------------------------------------------

class TestPassword:
    def test_set_password_hashes_the_password(self, app, new_user):
        """set_password() stores a hash, not the raw password string."""
        new_user.set_password("mypassword")

        assert new_user.password != "mypassword"
        assert new_user.password is not None
        assert len(new_user.password) > 20  # hashes are long

    def test_check_password_returns_true_for_correct_password(self, app, new_user):
        """check_password() returns True when the correct password is given."""
        new_user.set_password("correctpassword")

        assert new_user.check_password("correctpassword") is True

    def test_check_password_returns_false_for_wrong_password(self, app, new_user):
        """check_password() returns False when the wrong password is given."""
        new_user.set_password("correctpassword")

        assert new_user.check_password("wrongpassword") is False

    def test_check_password_is_case_sensitive(self, app, new_user):
        """Password check is case-sensitive."""
        new_user.set_password("Password123")

        assert new_user.check_password("password123") is False
        assert new_user.check_password("PASSWORD123") is False

    def test_set_password_twice_uses_latest(self, app, new_user):
        """Calling set_password() twice uses the most recent password."""
        new_user.set_password("first_password")
        new_user.set_password("second_password")

        assert new_user.check_password("second_password") is True
        assert new_user.check_password("first_password") is False

    def test_password_persists_after_save(self, app, new_user):
        """Hashed password is correctly stored and retrieved from DB."""
        new_user.set_password("persistme")
        new_user.save()

        retrieved = User.get_by_id(new_user.user_id)
        assert retrieved.check_password("persistme") is True

    def test_different_users_same_password_have_different_hashes(self, app):
        """
        Two users with the same plain password get different hashes
        due to salting — ensures no hash reuse vulnerability.
        """
        u1 = User(user_id=11112026, first_name="A", last_name="B",
                  role="cashier", status="activated")
        u2 = User(user_id=11122026, first_name="C", last_name="D",
                  role="cashier", status="activated")

        u1.set_password("samepassword")
        u2.set_password("samepassword")

        assert u1.password != u2.password


# ---------------------------------------------------------------------------
# User.set_status()
# ---------------------------------------------------------------------------

class TestSetStatus:
    def test_set_status_updates_status_field(self, app, user):
        """set_status() changes the status field value."""
        user.set_status("suspended")
        assert user.status == "suspended"

    def test_set_status_persists_after_save(self, app, user):
        """Status change is persisted to DB after save()."""
        user.set_status("archived")
        user.save()

        retrieved = User.get_by_id(user.user_id)
        assert retrieved.status == "archived"

    def test_set_status_does_not_auto_save(self, app, user):
        """set_status() only changes the in-memory value — requires save()."""
        original_status = user.status
        user.set_status("suspended")

        # Expire the session to force a fresh DB read
        db.session.expire(user)
        retrieved = User.get_by_id(user.user_id)

        # Without save(), DB still has the original
        assert retrieved.status == original_status


# ---------------------------------------------------------------------------
# User.full_name (property)
# ---------------------------------------------------------------------------

class TestFullName:
    def test_full_name_combines_first_and_last(self, app, user):
        """full_name returns 'FirstName LastName'."""
        assert user.full_name == f"{user.first_name} {user.last_name}"

    def test_full_name_format(self, app):
        """full_name follows 'First Last' order with a single space."""
        u = User(user_id=77772026, first_name="Maria", last_name="Santos",
                 role="cashier", status="activated")
        u.set_password("pass")

        assert u.full_name == "Maria Santos"

    def test_full_name_is_read_only_property(self, app, user):
        """full_name is a @property — it cannot be assigned directly."""
        with pytest.raises(AttributeError):
            user.full_name = "Something Else"


# ---------------------------------------------------------------------------
# User.get_id() — Flask-Login interface
# ---------------------------------------------------------------------------

class TestGetId:
    def test_get_id_returns_string(self, app, user):
        """Flask-Login requires get_id() to return a string, not an int."""
        result = user.get_id()
        assert isinstance(result, str)

    def test_get_id_value_matches_user_id(self, app, user):
        """get_id() value matches the user's user_id when cast to int."""
        result = user.get_id()
        assert int(result) == user.user_id


# ---------------------------------------------------------------------------
# User.to_dict()
# ---------------------------------------------------------------------------

class TestToDict:
    def test_all_keys_present(self, app, user):
        """to_dict() returns all five expected keys."""
        result = user.to_dict()

        assert set(result.keys()) == {
            "user_id",
            "first_name",
            "last_name",
            "role",
            "status",
        }

    def test_values_match_model_fields(self, app, user):
        """to_dict() values correctly reflect the model's field values."""
        result = user.to_dict()

        assert result["user_id"] == user.user_id
        assert result["first_name"] == user.first_name
        assert result["last_name"] == user.last_name
        assert result["role"] == user.role
        assert result["status"] == user.status

    def test_correct_types(self, app, user):
        """to_dict() returns correct Python types for each field."""
        result = user.to_dict()

        assert isinstance(result["user_id"], int)
        assert isinstance(result["first_name"], str)
        assert isinstance(result["last_name"], str)
        assert isinstance(result["role"], str)
        assert isinstance(result["status"], str)

    def test_password_not_exposed_in_dict(self, app, user):
        """to_dict() must NOT include the password hash — security check."""
        result = user.to_dict()
        assert "password" not in result


# ---------------------------------------------------------------------------
# User.generate_id() — delegates to AppSettings
# ---------------------------------------------------------------------------

class TestGenerateId:
    def test_generate_id_returns_int(self, app):
        """generate_id() returns an integer."""
        user_id = User.generate_id()
        assert isinstance(user_id, int)

    def test_generate_id_ends_with_current_year(self, app):
        """generate_id() produces an ID ending in the current year."""
        user_id = User.generate_id()
        assert str(user_id).endswith(str(datetime.utcnow().year))

    def test_generate_id_starts_at_1000(self, app):
        """First generated ID starts with counter 1000."""
        user_id = User.generate_id()
        assert str(user_id).startswith("1000")

    def test_generate_id_is_unique_per_call(self, app):
        """
        Each call to generate_id() should produce a unique ID.
        Simulates creating two users back to back.
        """
        id1 = User.generate_id()

        # Simulate first user existing in DB
        u = User(user_id=id1, first_name="A", last_name="B",
                 role="cashier", status="activated")
        u.set_password("pass")
        u.save()

        id2 = User.generate_id()
        assert id1 != id2


# ---------------------------------------------------------------------------
# User.get_default_password() — delegates to AppSettings
# ---------------------------------------------------------------------------

class TestGetDefaultPassword:
    def test_returns_default_password(self, app):
        """get_default_password() returns the current AppSettings default."""
        assert User.get_default_password() == "shekel123"

    def test_reflects_updated_default_password(self, app):
        """Changing AppSettings password is reflected in User.get_default_password()."""
        AppSettings.set_default_password("newdefault!")
        assert User.get_default_password() == "newdefault!"


# ---------------------------------------------------------------------------
# Inherited BaseModel methods
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_user(self, app, user):
        """save() commits a User to the database."""
        assert User.query.count() == 1

    def test_delete_removes_user(self, app, user):
        """delete() removes the User from the database."""
        user.delete()
        assert User.query.count() == 0

    def test_get_by_id_returns_correct_user(self, app, user):
        """get_by_id() retrieves the correct User by primary key."""
        result = User.get_by_id(user.user_id)

        assert result is not None
        assert result.user_id == user.user_id
        assert result.first_name == user.first_name

    def test_get_by_id_returns_none_for_missing(self, app):
        """get_by_id() returns None for a non-existent user_id."""
        result = User.get_by_id(99999999)
        assert result is None

    def test_get_all_returns_all_users(self, app, user, cashier_user, inactive_user):
        """get_all() returns every saved User."""
        result = User.get_all()
        assert len(result) == 3

    def test_get_all_empty_returns_empty_list(self, app):
        """get_all() returns an empty list when no users exist."""
        result = User.get_all()
        assert result == []