"""
tests/base_model_test.py

Pytest suite for BaseModel.
Tests all shared methods: save(), delete(), get_by_id(), get_all()
and rollback behavior — via a lightweight DummyModel concrete subclass.

app fixture comes from tests/conftest.py.
"""

import pytest
from unittest.mock import patch
from app.extensions import db
from app.models.base import BaseModel


# ---------------------------------------------------------------------------
# Concrete test model — only exists in tests
# ---------------------------------------------------------------------------

class DummyModel(BaseModel):
    """
    Minimal concrete subclass of BaseModel used solely for testing.
    Never exists in production — only created in the in-memory SQLite DB.
    """
    __tablename__ = "dummy"
    id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)


# ---------------------------------------------------------------------------
# Dummy-specific fixture (not in conftest — only relevant here)
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy(app):
    """A pre-saved DummyModel instance available to tests that need one."""
    instance = DummyModel(name="test_record")
    instance.save()
    return instance


# ---------------------------------------------------------------------------
# BaseModel.save()
# ---------------------------------------------------------------------------

class TestSave:
    def test_save_persists_to_db(self, app):
        """save() commits the instance to the database."""
        instance = DummyModel(name="alpha")
        instance.save()

        result = DummyModel.query.first()
        assert result is not None
        assert result.name == "alpha"

    def test_save_returns_self(self, app):
        """save() returns the instance itself for chaining."""
        instance = DummyModel(name="bravo")
        returned = instance.save()

        assert returned is instance

    def test_save_multiple_records(self, app):
        """Multiple save() calls each add a new row."""
        DummyModel(name="one").save()
        DummyModel(name="two").save()
        DummyModel(name="three").save()

        assert DummyModel.query.count() == 3

    def test_save_rollback_on_failure(self, app):
        """
        save() rolls back the session and re-raises the exception
        when the commit fails, leaving the DB unchanged.
        """
        DummyModel(name="safe_record").save()

        with patch.object(db.session, "commit", side_effect=Exception("DB error")):
            with pytest.raises(Exception, match="DB error"):
                DummyModel(name="bad_record").save()

        assert DummyModel.query.count() == 1

    def test_save_assigns_primary_key(self, app):
        """save() causes SQLAlchemy to populate the auto-increment id."""
        instance = DummyModel(name="charlie")
        assert instance.id is None

        instance.save()
        assert instance.id is not None


# ---------------------------------------------------------------------------
# BaseModel.delete()
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_removes_from_db(self, app, dummy):
        """delete() removes the record from the database."""
        assert DummyModel.query.count() == 1

        dummy.delete()

        assert DummyModel.query.count() == 0

    def test_delete_returns_self(self, app, dummy):
        """delete() returns the deleted instance for reference."""
        returned = dummy.delete()
        assert returned is dummy

    def test_delete_only_removes_target(self, app):
        """delete() removes only the specified record, not others."""
        a = DummyModel(name="keep_me").save()
        b = DummyModel(name="delete_me").save()

        b.delete()

        remaining = DummyModel.query.all()
        assert len(remaining) == 1
        assert remaining[0].name == "keep_me"

    def test_delete_rollback_on_failure(self, app, dummy):
        """
        delete() rolls back and re-raises the exception on commit failure,
        leaving the record intact in the DB.
        """
        with patch.object(db.session, "commit", side_effect=Exception("DB error")):
            with pytest.raises(Exception, match="DB error"):
                dummy.delete()

        assert DummyModel.query.count() == 1


# ---------------------------------------------------------------------------
# BaseModel.get_by_id()
# ---------------------------------------------------------------------------

class TestGetById:
    def test_get_by_id_returns_correct_record(self, app, dummy):
        """get_by_id() returns the record matching the given primary key."""
        result = DummyModel.get_by_id(dummy.id)

        assert result is not None
        assert result.id == dummy.id
        assert result.name == dummy.name

    def test_get_by_id_returns_none_for_missing_id(self, app):
        """get_by_id() returns None when no record matches the id."""
        result = DummyModel.get_by_id(9999)
        assert result is None

    def test_get_by_id_returns_none_on_empty_table(self, app):
        """get_by_id() returns None when the table is completely empty."""
        result = DummyModel.get_by_id(1)
        assert result is None

    def test_get_by_id_only_returns_own_model(self, app):
        """get_by_id() is scoped to the calling model, not all models."""
        from app.models.app_settings import AppSettings
        AppSettings.get()  # creates an AppSettings row with id=1

        dummy = DummyModel(name="scoped").save()

        result = DummyModel.get_by_id(dummy.id)
        assert isinstance(result, DummyModel)


# ---------------------------------------------------------------------------
# BaseModel.get_all()
# ---------------------------------------------------------------------------

class TestGetAll:
    def test_get_all_returns_empty_list_when_no_records(self, app):
        """get_all() returns an empty list when the table is empty."""
        result = DummyModel.get_all()
        assert result == []

    def test_get_all_returns_all_records(self, app):
        """get_all() returns every record in the table."""
        DummyModel(name="x").save()
        DummyModel(name="y").save()
        DummyModel(name="z").save()

        result = DummyModel.get_all()
        assert len(result) == 3

    def test_get_all_returns_list_type(self, app):
        """get_all() always returns a list, never None."""
        result = DummyModel.get_all()
        assert isinstance(result, list)

    def test_get_all_returns_correct_instances(self, app):
        """get_all() returns instances of the calling model class."""
        DummyModel(name="instance_check").save()

        result = DummyModel.get_all()
        assert all(isinstance(r, DummyModel) for r in result)

    def test_get_all_reflects_deletions(self, app):
        """get_all() count decreases after a record is deleted."""
        a = DummyModel(name="stay").save()
        b = DummyModel(name="go").save()

        b.delete()

        result = DummyModel.get_all()
        assert len(result) == 1
        assert result[0].name == "stay"