"""
tests/app_setting_test.py

Pytest suite for AppSettings model.
Covers: get(), next_user_id(), get_default_password(),
        set_default_password(), and to_dict().

app fixture comes from tests/conftest.py.
"""

import pytest
from datetime import datetime
from app.models.app_settings import AppSettings
from app.extensions import db


# ---------------------------------------------------------------------------
# AppSettings.get()
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_creates_row_when_none_exists(self, app):
        """get() auto-creates a settings row with correct defaults."""
        settings = AppSettings.get()

        assert settings is not None
        assert settings.id == 1
        assert settings.user_counter == 1000
        assert settings.counter_year == datetime.utcnow().year
        assert settings.default_password == "shekel123"

    def test_get_returns_existing_row(self, app):
        """get() returns the pre-existing row without creating a duplicate."""
        existing = AppSettings(
            id=1,
            counter_year=2024,
            user_counter=1005,
            default_password="custom_pass",
        )
        db.session.add(existing)
        db.session.commit()

        settings = AppSettings.get()

        assert settings.user_counter == 1005
        assert settings.default_password == "custom_pass"
        assert AppSettings.query.count() == 1

    def test_get_does_not_create_duplicate_rows(self, app):
        """Calling get() multiple times still results in exactly one row."""
        AppSettings.get()
        AppSettings.get()
        AppSettings.get()

        assert AppSettings.query.count() == 1


# ---------------------------------------------------------------------------
# AppSettings.next_user_id()
# ---------------------------------------------------------------------------

class TestNextUserId:
    def test_format_is_counter_then_year(self, app):
        """Returned ID must follow [counter][year] format."""
        user_id = AppSettings.next_user_id()
        year = str(datetime.utcnow().year)

        assert str(user_id).endswith(year)
        assert str(user_id).startswith("1000")

    def test_starts_at_1000_when_no_users(self, app):
        """Counter starts at 1000 when no users exist in the DB."""
        user_id = AppSettings.next_user_id()
        current_year = datetime.utcnow().year

        assert user_id == int(f"1000{current_year}")

    def test_resets_counter_on_year_change(self, app):
        """
        When counter_year in settings differs from the current year,
        the counter resets to 1000 and counter_year is updated.
        """
        old_year = datetime.utcnow().year - 1
        settings = AppSettings(id=1, counter_year=old_year, user_counter=1099)
        db.session.add(settings)
        db.session.commit()

        current_year = datetime.utcnow().year
        user_id = AppSettings.next_user_id()

        refreshed = AppSettings.query.first()
        assert refreshed.counter_year == current_year
        assert str(user_id).endswith(str(current_year))
        assert str(user_id).startswith("1000")

    def test_creates_settings_row_if_missing(self, app):
        """next_user_id() works correctly even if no settings row exists yet."""
        assert AppSettings.query.count() == 0

        user_id = AppSettings.next_user_id()

        assert user_id is not None
        assert isinstance(user_id, int)

    def test_syncs_user_counter_after_generation(self, app):
        """After generating an ID when no users exist, user_counter is set to 1000."""
        AppSettings.next_user_id()

        settings = AppSettings.query.first()
        assert settings.user_counter == 1000

    def test_returns_integer_type(self, app):
        """next_user_id() must always return an int, not a string."""
        user_id = AppSettings.next_user_id()
        assert isinstance(user_id, int)


# ---------------------------------------------------------------------------
# AppSettings.get_default_password()
# ---------------------------------------------------------------------------

class TestGetDefaultPassword:
    def test_returns_default_password(self, app):
        """Returns 'shekel123' out of the box."""
        password = AppSettings.get_default_password()
        assert password == "shekel123"

    def test_returns_updated_password_after_change(self, app):
        """Reflects the password after it has been changed."""
        AppSettings.set_default_password("newpass456")
        assert AppSettings.get_default_password() == "newpass456"

    def test_works_without_existing_row(self, app):
        """Can retrieve default password even if no row existed yet."""
        assert AppSettings.query.count() == 0
        password = AppSettings.get_default_password()
        assert password == "shekel123"


# ---------------------------------------------------------------------------
# AppSettings.set_default_password()
# ---------------------------------------------------------------------------

class TestSetDefaultPassword:
    def test_persists_new_password(self, app):
        """New password is committed to the database."""
        AppSettings.set_default_password("supersecure!")
        settings = AppSettings.query.first()
        assert settings.default_password == "supersecure!"

    def test_updates_updated_at_timestamp(self, app):
        """updated_at is refreshed when the password changes."""
        before = datetime.utcnow()
        AppSettings.set_default_password("timestamptest")
        settings = AppSettings.query.first()
        assert settings.updated_at >= before

    def test_overwrites_previous_password(self, app):
        """Setting password twice keeps only the latest value."""
        AppSettings.set_default_password("first_pass")
        AppSettings.set_default_password("second_pass")
        assert AppSettings.get_default_password() == "second_pass"

    def test_accepts_long_password(self, app):
        """Passwords up to 255 chars (column limit) are accepted."""
        long_password = "a" * 255
        AppSettings.set_default_password(long_password)
        assert AppSettings.get_default_password() == long_password

    def test_accepts_empty_string_password(self, app):
        """Empty string password is stored without error."""
        AppSettings.set_default_password("")
        assert AppSettings.get_default_password() == ""


# ---------------------------------------------------------------------------
# AppSettings.to_dict()
# ---------------------------------------------------------------------------

class TestToDict:
    def test_all_keys_present(self, app):
        """to_dict() returns all expected keys."""
        settings = AppSettings.get()
        result = settings.to_dict()

        assert set(result.keys()) == {
            "user_counter",
            "counter_year",
            "default_password",
            "updated_at",
        }

    def test_values_have_correct_types(self, app):
        """to_dict() returns correct Python types for each field."""
        settings = AppSettings.get()
        result = settings.to_dict()

        assert isinstance(result["user_counter"], int)
        assert isinstance(result["counter_year"], int)
        assert isinstance(result["default_password"], str)
        assert result["updated_at"] is None or isinstance(result["updated_at"], str)

    def test_updated_at_is_set_automatically_on_insert(self, app):
        """
        updated_at is auto-populated by SQLAlchemy on insert via
        set_default_password() which explicitly sets it — never None
        after a password update.
        """
        AppSettings.set_default_password("isocheck")
        settings = AppSettings.query.first()
        result = settings.to_dict()

        assert result["updated_at"] is not None

    def test_updated_at_is_iso_format(self, app):
        """When updated_at is set, it serializes as a valid ISO 8601 string."""
        AppSettings.set_default_password("isocheck")
        settings = AppSettings.query.first()
        result = settings.to_dict()

        parsed = datetime.fromisoformat(result["updated_at"])
        assert isinstance(parsed, datetime)

    def test_counter_year_matches_db(self, app):
        """counter_year in dict matches what was stored."""
        settings = AppSettings.get()
        result = settings.to_dict()
        assert result["counter_year"] == datetime.utcnow().year