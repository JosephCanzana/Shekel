"""
tests/conftest.py

Shared fixtures for all test files.

Two critical SQLite testing fixes applied here:

1. PRAGMA foreign_keys=ON
   SQLite disables FK enforcement by default. The event listener below
   enables it for every connection so FK constraint tests work correctly.

2. validate_strings=True on db.Enum (applied in models, not here)
   SQLite maps Enum to VARCHAR and won't reject invalid values at the DB
   level. Add validate_strings=True to every db.Enum() in your models so
   SQLAlchemy validates values in Python before hitting the DB.

FK dependency order (bottom-up):
  Category
  User
  Product        (→ Category)
  Inventory      (→ Product)
  ProductBundle  (→ Product)
  Defect         (→ User)
  DefectDetail   (→ Defect, Product)
  Sale           (→ User)
  SaleDetail     (→ Sale, Product)
  StockIn        (→ Product, User)
  AuditLog       (→ User)
  RecoveryDetail (→ User)
"""

import sqlite3
import pytest
from decimal import Decimal
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app import create_app
from app.extensions import db

from app.models.category import Category
from app.models.user import User
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.product_bundle import ProductBundle
from app.models.defect import Defect
from app.models.defect_detail import DefectDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.stock_in import StockIn
from app.models.audit_log import AuditLog
from app.models.recovery_detail import RecoveryDetail


# ---------------------------------------------------------------------------
# Fix 1 — Enable SQLite FK enforcement for ALL test connections
# ---------------------------------------------------------------------------

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    SQLite disables foreign key constraints by default.
    This enables them on every new connection so FK tests work correctly.
    Has no effect on MySQL/PostgreSQL (which enforce FKs natively).
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ---------------------------------------------------------------------------
# App & DB
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def app():
    """
    Fresh Flask app with isolated in-memory SQLite DB per test.
    test_config is injected BEFORE db.init_app() runs so SQLAlchemy
    never sees a missing DATABASE_URL.
    """
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret-key-not-for-production",  
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Flask test client for route testing."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

@pytest.fixture
def category(app):
    cat = Category(
        category_name="Electronics",
        description="Electronic devices",
        status="active",
    )
    cat.save()
    return cat


@pytest.fixture
def second_category(app):
    cat = Category(
        category_name="Beverages",
        description="Drinks and beverages",
        status="active",
    )
    cat.save()
    return cat


# ---------------------------------------------------------------------------
# User
# Exact columns: user_id, first_name, last_name, role, password, status
# ---------------------------------------------------------------------------

@pytest.fixture
def user(app):
    u = User(
        user_id=10002026,
        first_name="Test",
        last_name="User",
        role="superadmin",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def cashier_user(app):
    u = User(
        user_id=10012026,
        first_name="Jane",
        last_name="Doe",
        role="cashier",
        status="activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


@pytest.fixture
def inactive_user(app):
    u = User(
        user_id=10022026,
        first_name="Inactive",
        last_name="User",
        role="stocking",
        status="not_activated",
    )
    u.set_password("shekel123")
    u.save()
    return u


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

@pytest.fixture
def product(app, category):
    prod = Product(
        product_id="PROD-001",
        product_name="Test Product",
        category_id=category.category_id,
        cost_price=Decimal("10.00"),
        revenue_price=Decimal("12.00"),
        total_price=Decimal("15.00"),
        low_reorder_threshold=5,
        status="active",
    )
    prod.save()
    return prod


@pytest.fixture
def second_product(app, category):
    prod = Product(
        product_id="PROD-002",
        product_name="Second Product",
        category_id=category.category_id,
        cost_price=Decimal("20.00"),
        revenue_price=Decimal("24.00"),
        total_price=Decimal("30.00"),
        low_reorder_threshold=3,
        status="active",
    )
    prod.save()
    return prod


@pytest.fixture
def archived_product(app, category):
    prod = Product(
        product_id="PROD-ARCH",
        product_name="Archived Product",
        category_id=category.category_id,
        cost_price=Decimal("5.00"),
        revenue_price=Decimal("6.00"),
        total_price=Decimal("8.00"),
        low_reorder_threshold=2,
        status="archived",
    )
    prod.save()
    return prod


@pytest.fixture
def product_no_category(app):
    """Product with no category (category_id is nullable)."""
    prod = Product(
        product_id="PROD-NOCAT",
        product_name="No Category Product",
        category_id=None,
        cost_price=Decimal("5.00"),
        revenue_price=Decimal("6.00"),
        total_price=Decimal("8.00"),
        low_reorder_threshold=2,
        status="active",
    )
    prod.save()
    return prod


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@pytest.fixture
def inventory(app, product):
    inv = Inventory(
        product_id=product.product_id,
        quantity_available=100,
        quantity_defective=5,
        last_updated=datetime.utcnow(),
    )
    inv.save()
    return inv


@pytest.fixture
def low_stock_inventory(app, second_product):
    """Inventory where quantity_available is below low_reorder_threshold."""
    inv = Inventory(
        product_id=second_product.product_id,
        quantity_available=1,
        quantity_defective=0,
        last_updated=datetime.utcnow(),
    )
    inv.save()
    return inv


# ---------------------------------------------------------------------------
# ProductBundle
# ---------------------------------------------------------------------------

@pytest.fixture
def product_bundle(app, product):
    bundle = ProductBundle(
        bundle_id="BUNDLE-001",
        product_id=product.product_id,
        bundle_name="12-pack",
        bundle_count=12,
    )
    bundle.save()
    return bundle


# ---------------------------------------------------------------------------
# Defect
# ---------------------------------------------------------------------------

@pytest.fixture
def defect(app, user):
    d = Defect(
        user_id=user.user_id,
        total_cost_price=Decimal("20.00"),
        total_revenue_price=Decimal("24.00"),
        total_amount=Decimal("30.00"),
    )
    d.save()
    return d


# ---------------------------------------------------------------------------
# DefectDetail
# ---------------------------------------------------------------------------

@pytest.fixture
def defect_detail(app, defect, product):
    dd = DefectDetail(
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
    dd.save()
    return dd


# ---------------------------------------------------------------------------
# Sale
# ---------------------------------------------------------------------------

@pytest.fixture
def sale(app, user):
    s = Sale(
        user_id=user.user_id,
        total_cost_price=Decimal("20.00"),
        total_revenue_price=Decimal("24.00"),
        total_amount=Decimal("30.00"),
        payment_method="cash",
    )
    s.save()
    return s


# ---------------------------------------------------------------------------
# SaleDetail
# ---------------------------------------------------------------------------

@pytest.fixture
def sale_detail(app, sale, product):
    sd = SaleDetail(
        transaction_id=sale.transaction_id,
        product_id=product.product_id,
        quantity=2,
        cost_price_at_sale=Decimal("10.00"),
        revenue_price_at_sale=Decimal("12.00"),
        price_at_sale=Decimal("15.00"),
        subtotal_unit=Decimal("20.00"),
        subtotal_revenue=Decimal("24.00"),
        subtotal_amount=Decimal("30.00"),
    )
    sd.save()
    return sd


# ---------------------------------------------------------------------------
# StockIn
# ---------------------------------------------------------------------------

@pytest.fixture
def stock_in(app, product, user):
    s = StockIn(
        product_id=product.product_id,
        user_id=user.user_id,
        quantity_received=50,
        notes="Initial stock",
    )
    s.save()
    return s


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_log(app, user):
    log = AuditLog(
        user_id=user.user_id,
        action_type="INSERT",
        module="products",
        description="Created a new product",
        reference_id=1,
        reference_table="Products",
    )
    log.save()
    return log


# ---------------------------------------------------------------------------
# RecoveryDetail
# ---------------------------------------------------------------------------

@pytest.fixture
def recovery_detail(app, user):
    rd = RecoveryDetail(
        user_id=user.user_id,
        email="test@example.com",
        phone_number="09171234567",
    )
    rd.save()
    return rd


# ---------------------------------------------------------------------------
# Per role
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
def cashier_client(client, cashier_user):
    """Authenticated client as cashier."""
    client.post("/", data={
        "full_name": f"{cashier_user.first_name} {cashier_user.last_name}",
        "password": "shekel123",
    })
    return client

@pytest.fixture
def stocking_client(client, stocking_user):
    """Authenticated client as stocking staff."""
    client.post("/", data={
        "full_name": f"{stocking_user.first_name} {stocking_user.last_name}",
        "password": "shekel123",
    })
    return client