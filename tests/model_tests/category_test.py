"""
tests/category_test.py

Pytest suite for Category model.
Covers: column constraints, defaults, to_dict(),
        and inherited BaseModel methods.

app and category fixtures come from tests/conftest.py.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.category import Category


# ---------------------------------------------------------------------------
# Column Constraints & Defaults
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_category_name_is_required(self, app):
        """category_name is NOT NULL — saving without it raises an error."""
        with pytest.raises(Exception):
            Category(description="no name here").save()

    def test_category_name_must_be_unique(self, app):
        """Two categories with the same name violate the unique constraint."""
        Category(category_name="Duplicated").save()

        with pytest.raises(Exception):
            Category(category_name="Duplicated").save()

    def test_description_is_optional(self, app):
        """description is nullable — saving without it should succeed."""
        cat = Category(category_name="No Description")
        cat.save()

        result = Category.get_by_id(cat.category_id)
        assert result.description is None

    def test_status_defaults_to_active(self, app):
        """status defaults to 'active' when not explicitly provided."""
        cat = Category(category_name="Default Status")
        cat.save()

        result = Category.get_by_id(cat.category_id)
        assert result.status == "active"

    def test_status_can_be_set_explicitly(self, app):
        """status can be set to a value other than the default."""
        cat = Category(category_name="Inactive Cat", status="inactive")
        cat.save()

        result = Category.get_by_id(cat.category_id)
        assert result.status == "inactive"

    def test_category_id_autoincrements(self, app):
        """category_id is auto-assigned and increments across inserts."""
        a = Category(category_name="First").save()
        b = Category(category_name="Second").save()

        assert a.category_id is not None
        assert b.category_id is not None
        assert b.category_id > a.category_id

    def test_category_name_max_length(self, app):
        """category_name accepts strings up to 100 characters."""
        long_name = "A" * 100
        cat = Category(category_name=long_name)
        cat.save()

        result = Category.get_by_id(cat.category_id)
        assert result.category_name == long_name


# ---------------------------------------------------------------------------
# Category.to_dict()
# ---------------------------------------------------------------------------

class TestToDict:
    def test_all_keys_present(self, app, category):
        """to_dict() returns all four expected keys."""
        result = category.to_dict()

        assert set(result.keys()) == {
            "category_id",
            "name",
            "description",
            "status",
        }

    def test_values_match_model_fields(self, app, category):
        """to_dict() values correctly reflect the model's field values."""
        result = category.to_dict()

        assert result["category_id"] == category.category_id
        assert result["name"] == category.category_name
        assert result["description"] == category.description
        assert result["status"] == category.status

    def test_description_none_returns_empty_string(self, app):
        """to_dict() converts None description to an empty string."""
        cat = Category(category_name="No Desc", description=None)
        cat.save()

        result = cat.to_dict()
        assert result["description"] == ""

    def test_description_with_value_is_preserved(self, app):
        """to_dict() returns the actual description string when set."""
        cat = Category(
            category_name="With Desc",
            description="Some useful description",
        )
        cat.save()

        result = cat.to_dict()
        assert result["description"] == "Some useful description"

    def test_correct_types(self, app, category):
        """to_dict() returns correct Python types for each field."""
        result = category.to_dict()

        assert isinstance(result["category_id"], int)
        assert isinstance(result["name"], str)
        assert isinstance(result["description"], str)
        assert isinstance(result["status"], str)

    def test_name_key_maps_to_category_name_column(self, app, category):
        """
        The dict key is 'name' but the column is 'category_name'.
        Ensures the mapping is correct and not accidentally swapped.
        """
        result = category.to_dict()
        assert result["name"] == category.category_name


# ---------------------------------------------------------------------------
# Inherited BaseModel methods
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_category(self, app):
        """save() commits a Category to the database."""
        cat = Category(category_name="Saved Cat")
        cat.save()

        assert Category.query.count() == 1

    def test_delete_removes_category(self, app, category):
        """delete() removes the Category from the database."""
        category.delete()
        assert Category.query.count() == 0

    def test_get_by_id_returns_correct_category(self, app, category):
        """get_by_id() retrieves the correct Category by primary key."""
        result = Category.get_by_id(category.category_id)

        assert result is not None
        assert result.category_name == category.category_name

    def test_get_by_id_returns_none_for_missing(self, app):
        """get_by_id() returns None for a non-existent category_id."""
        result = Category.get_by_id(9999)
        assert result is None

    def test_get_all_returns_all_categories(self, app):
        """get_all() returns every saved Category."""
        Category(category_name="Cat A").save()
        Category(category_name="Cat B").save()
        Category(category_name="Cat C").save()

        result = Category.get_all()
        assert len(result) == 3

    def test_get_all_empty_returns_empty_list(self, app):
        """get_all() returns an empty list when no categories exist."""
        result = Category.get_all()
        assert result == []


# ---------------------------------------------------------------------------
# Category update behavior
# ---------------------------------------------------------------------------

class TestCategoryUpdates:
    def test_update_category_name(self, app, category):
        """Updating category_name and saving persists the change."""
        category.category_name = "Updated Electronics"
        category.save()

        result = Category.get_by_id(category.category_id)
        assert result.category_name == "Updated Electronics"

    def test_update_status_to_inactive(self, app, category):
        """Status can be changed from active to inactive."""
        category.status = "inactive"
        category.save()

        result = Category.get_by_id(category.category_id)
        assert result.status == "inactive"

    def test_update_description(self, app, category):
        """Description can be updated to a new value."""
        category.description = "Updated description"
        category.save()

        result = Category.get_by_id(category.category_id)
        assert result.description == "Updated description"

    def test_update_name_to_duplicate_raises_error(self, app):
        """Updating a name to match another existing category raises an error."""
        Category(category_name="Original").save()
        other = Category(category_name="Other").save()

        with pytest.raises(Exception):
            other.category_name = "Original"
            other.save()