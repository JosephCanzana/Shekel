"""
tests/defect_detail_test.py

Pytest suite for DefectDetail model.
Focuses on: nullable constraints, enum validation, FK integrity,
            ondelete=RESTRICT behavior, and Numeric precision.

All fixtures come from tests/conftest.py.
"""

import pytest
from decimal import Decimal
from app.extensions import db
from app.models.defect_detail import DefectDetail
from app.models.product import Product


# ---------------------------------------------------------------------------
# Helper — valid data dict built from live fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(defect, product):
    """Returns a dict of all valid fields for a DefectDetail."""
    return dict(
        defect_id=defect.defect_id,
        product_id=product.product_id,
        quantity=2,
        reason="defect",
        compensation="pending",
        cost_price_at_defect=Decimal("10.00"),
        revenue_price_at_defect=Decimal("12.00"),
        price_at_defect=Decimal("15.00"),
        subtotal_unit=Decimal("20.00"),
        subtotal_revenue=Decimal("24.00"),
        subtotal_amount=Decimal("30.00"),
    )


# ---------------------------------------------------------------------------
# Nullable / Required Column Constraints
# ---------------------------------------------------------------------------

class TestNullConstraints:
    def test_all_required_fields_saves_successfully(self, app, valid_data):
        """A DefectDetail with all required fields saves without error."""
        DefectDetail(**valid_data).save()
        assert DefectDetail.query.count() == 1

    def test_missing_defect_id_raises(self, app, valid_data):
        valid_data.pop("defect_id")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_product_id_raises(self, app, valid_data):
        valid_data.pop("product_id")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_quantity_raises(self, app, valid_data):
        valid_data.pop("quantity")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_reason_raises(self, app, valid_data):
        valid_data.pop("reason")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_compensation_raises(self, app, valid_data):
        valid_data.pop("compensation")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_cost_price_at_defect_raises(self, app, valid_data):
        valid_data.pop("cost_price_at_defect")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_price_at_defect_raises(self, app, valid_data):
        valid_data.pop("price_at_defect")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_missing_subtotal_amount_raises(self, app, valid_data):
        valid_data.pop("subtotal_amount")
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()


# ---------------------------------------------------------------------------
# Enum Constraints — reason
# ---------------------------------------------------------------------------

class TestReasonEnum:
    @pytest.mark.parametrize("valid_reason", [
        "defect", "damage", "expired", "change_of_mind"
    ])
    def test_valid_reason_values_are_accepted(self, app, valid_data, valid_reason):
        valid_data["reason"] = valid_reason
        DefectDetail(**valid_data).save()
        assert DefectDetail.query.count() == 1

    @pytest.mark.parametrize("invalid_reason", [
        "lost", "stolen", "broken", "", "DEFECT", "Defect"
    ])
    def test_invalid_reason_values_are_rejected(self, app, valid_data, invalid_reason):
        valid_data["reason"] = invalid_reason
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()


# ---------------------------------------------------------------------------
# Enum Constraints — compensation
# ---------------------------------------------------------------------------

class TestCompensationEnum:
    @pytest.mark.parametrize("valid_comp", [
        "pending", "loss", "returned", "replacement"
    ])
    def test_valid_compensation_values_are_accepted(self, app, valid_data, valid_comp):
        valid_data["compensation"] = valid_comp
        DefectDetail(**valid_data).save()
        assert DefectDetail.query.count() == 1

    @pytest.mark.parametrize("invalid_comp", [
        "refund", "rejected", "approved", "", "PENDING", "Pending"
    ])
    def test_invalid_compensation_values_are_rejected(self, app, valid_data, invalid_comp):
        valid_data["compensation"] = invalid_comp
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()


# ---------------------------------------------------------------------------
# Foreign Key Constraints
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_defect_id_raises(self, app, valid_data):
        """defect_id must reference an existing Defect row."""
        valid_data["defect_id"] = 99999
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_invalid_product_id_raises(self, app, valid_data):
        """product_id must reference an existing Product row."""
        valid_data["product_id"] = "NONEXISTENT-SKU"
        with pytest.raises(Exception):
            DefectDetail(**valid_data).save()

    def test_valid_fk_references_save_successfully(self, app, defect_detail):
        """DefectDetail with valid FK references saves cleanly."""
        assert defect_detail.defect_detail_id is not None


# ---------------------------------------------------------------------------
# ondelete=RESTRICT — product_id FK
# ---------------------------------------------------------------------------

class TestOnDeleteRestrict:
    def test_deleting_product_with_defect_detail_raises(self, app, defect_detail, product):
        """Deleting a Product that has DefectDetail rows should be RESTRICTED."""
        with pytest.raises(Exception):
            db.session.delete(product)
            db.session.commit()

    def test_defect_detail_survives_after_failed_product_delete(self, app, defect_detail, product):
        """After a failed product delete, the DefectDetail row still exists."""
        try:
            db.session.delete(product)
            db.session.commit()
        except Exception:
            db.session.rollback()

        assert DefectDetail.query.count() == 1

    def test_cannot_null_product_id_to_bypass_restrict(self, app, defect_detail, product):
        """
        Unlike SaleDetail, DefectDetail.product_id is NOT NULL —
        you cannot null it out to bypass RESTRICT.
        The only way to delete the product is to delete the DefectDetail first.
        """
        with pytest.raises(Exception):
            defect_detail.product_id = None
            defect_detail.save()

    def test_product_can_be_deleted_after_defect_detail_removed(self, app, defect_detail, product, defect):
        """
        The correct workflow: delete the DefectDetail first,
        then the Product can be deleted freely with no RESTRICT blocking it.
        """
        defect_detail.delete()
        product.delete()

        assert Product.query.count() == 0
        assert DefectDetail.query.count() == 0


# ---------------------------------------------------------------------------
# cascade="all, delete-orphan" — defect_id FK
# ---------------------------------------------------------------------------

class TestCascadeDeleteOnDefect:
    def test_deleting_defect_cascades_to_detail(self, app, defect_detail, defect):
        """Deleting a Defect cascades and removes its DefectDetail children."""
        assert DefectDetail.query.count() == 1

        db.session.delete(defect)
        db.session.commit()

        assert DefectDetail.query.count() == 0


# ---------------------------------------------------------------------------
# Numeric Precision — financial fields
# ---------------------------------------------------------------------------

class TestNumericPrecision:
    def test_prices_stored_with_two_decimal_places(self, app, defect_detail):
        result = DefectDetail.get_by_id(defect_detail.defect_detail_id)

        assert result.cost_price_at_defect == Decimal("10.00")
        assert result.revenue_price_at_defect == Decimal("12.00")
        assert result.price_at_defect == Decimal("15.00")
        assert result.subtotal_unit == Decimal("20.00")
        assert result.subtotal_revenue == Decimal("24.00")
        assert result.subtotal_amount == Decimal("30.00")

    def test_prices_are_decimal_type(self, app, defect_detail):
        result = DefectDetail.get_by_id(defect_detail.defect_detail_id)

        assert isinstance(result.cost_price_at_defect, Decimal)
        assert isinstance(result.subtotal_amount, Decimal)

    def test_large_price_within_bounds(self, app, valid_data):
        """Numeric(10, 2) allows values up to 99999999.99."""
        for field in [
            "cost_price_at_defect", "revenue_price_at_defect", "price_at_defect",
            "subtotal_unit", "subtotal_revenue", "subtotal_amount"
        ]:
            valid_data[field] = Decimal("99999999.99")

        DefectDetail(**valid_data).save()
        assert DefectDetail.query.count() == 1


# ---------------------------------------------------------------------------
# Inherited BaseModel Methods
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_and_get_by_id(self, app, defect_detail):
        result = DefectDetail.get_by_id(defect_detail.defect_detail_id)
        assert result is not None
        assert result.defect_detail_id == defect_detail.defect_detail_id

    def test_get_all_returns_all_records(self, app, valid_data):
        DefectDetail(**valid_data).save()
        assert len(DefectDetail.get_all()) == 1

    def test_delete_removes_record(self, app, defect_detail):
        defect_detail.delete()
        assert DefectDetail.query.count() == 0