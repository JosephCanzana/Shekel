from datetime import datetime, timedelta
import pytz
from sqlalchemy import extract
from app.models.product import Product
from app.models.sale import Sale
from app.models.inventory import Inventory
from app.models.stock_in import StockIn
from app.models.defect import Defect
from app.models.defect_detail import DefectDetail
from app.utils.helpers import get_time_of_day, pht_now, pht_today, to_pht


# ── Shared helpers ────────────────────────────────────────────────────────────

def _today_utc_range():
    now_pht     = pht_now()
    start_today = now_pht.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today   = start_today + timedelta(days=1)
    return start_today.astimezone(pytz.utc), end_today.astimezone(pytz.utc)

def _month_filters(now_pht=None):
    if now_pht is None:
        now_pht = pht_now()
    return now_pht.month, now_pht.year


# ── Low stock ─────────────────────────────────────────────────────────────────

def get_low_stock_items(limit=5):
    low_stock = (
        Inventory.query
        .join(Product)
        .filter(
            Product.status == "active",
            Inventory.quantity_available <= Product.low_reorder_threshold
        )
        .order_by(Inventory.quantity_available.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "name":     item.product.product_name.capitalize(),
            "category": item.product.category.category_name if item.product.category else "—",
            "stock":    item.quantity_available,
            "threshold": item.product.low_reorder_threshold,
        }
        for item in low_stock
    ]


# ── Defects ───────────────────────────────────────────────────────────────────

def get_defects(limit=5):
    """Recent defect detail records this month with product + logged-by info."""
    from app.extensions import db
    from app.models.user import User
    now_pht       = pht_now()
    month, year   = _month_filters(now_pht)

    rows = (
        db.session.query(DefectDetail, Defect, Product, User)
        .join(Defect,   Defect.defect_id     == DefectDetail.defect_id)
        .join(Product,  Product.product_id   == DefectDetail.product_id)
        .join(User,     User.user_id         == Defect.user_id)
        .filter(
            extract("month", Defect.defect_datetime) == month,
            extract("year",  Defect.defect_datetime) == year,
        )
        .order_by(Defect.defect_datetime.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "name":        product.product_name.capitalize(),
            "reported_by": f"{user.first_name} {user.last_name}".strip().title(),
            "date":        to_pht(defect.defect_datetime).strftime("%b %d"),
            "qty":         detail.quantity,
            "reason":      detail.reason.replace("_", " ").title(),
            "compensation": detail.compensation.title(),
        }
        for detail, defect, product, user in rows
    ]

def _defects_count_this_month():
    from app.extensions import db
    now_pht     = pht_now()
    month, year = _month_filters(now_pht)
    return (
        db.session.query(DefectDetail)
        .join(Defect, Defect.defect_id == DefectDetail.defect_id)
        .filter(
            extract("month", Defect.defect_datetime) == month,
            extract("year",  Defect.defect_datetime) == year,
        )
        .count()
    )


# ── Recent stock-ins ──────────────────────────────────────────────────────────

def get_recent_stockins(limit=5):
    recent = (
        StockIn.query
        .order_by(StockIn.stockin_datetime.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "name":       item.product.product_name.capitalize() if item.product else "Deleted Product",
            "stocked_by": f"{item.user.first_name} {item.user.last_name}".strip().title()
                          if item.user else "Unknown",
            "date":       to_pht(item.stockin_datetime).strftime("%b %d, %Y %I:%M %p"),
            "qty":        item.quantity_received,
        }
        for item in recent
        if item.product is not None
    ]


# ── Admin stats ───────────────────────────────────────────────────────────────

def get_admin_stats():
    now_pht              = pht_now()
    start_utc, end_utc   = _today_utc_range()
    month, year          = _month_filters(now_pht)

    sales_today = Sale.query.filter(
        Sale.sale_datetime >= start_utc,
        Sale.sale_datetime <  end_utc
    ).all()

    total_amount    = sum(float(s.total_amount) for s in sales_today)
    transactions    = len(sales_today)

    recent = sorted(sales_today, key=lambda s: s.sale_datetime, reverse=True)[:7]
    recent_list = [
        {
            "reference": f"TXN-{s.transaction_id:05d}",
            "cashier":   f"{s.user.first_name} {s.user.last_name}".strip().title()
                         if s.user else "Unknown",
            "time":      to_pht(s.sale_datetime).strftime("%I:%M %p"),
            "total":     f"{float(s.total_amount):,.2f}",
        }
        for s in recent
    ]

    new_products = Product.query.filter(
        extract("month", Product.created_at) == month,
        extract("year",  Product.created_at) == year,
    ).count()

    low_stock_count = Inventory.query.join(Product).filter(
        Product.status == "active",
        Inventory.quantity_available <= Product.low_reorder_threshold
    ).count()

    defects_count = _defects_count_this_month()

    return {
        "sales_today":        f"{total_amount:,.2f}",
        "transactions_today": transactions,
        "new_added_product":  new_products,
        "total_products":     Product.query.count(),
        "low_stock_count":    low_stock_count,
        "defects_count":      defects_count,
        "recent_transactions": recent_list,
    }


# ── Stocking stats ────────────────────────────────────────────────────────────

def get_stocking_stats():
    now_pht     = pht_now()
    month, year = _month_filters(now_pht)

    low_stock_count = Inventory.query.join(Product).filter(
        Product.status == "active",
        Inventory.quantity_available <= Product.low_reorder_threshold
    ).count()

    defects_count = _defects_count_this_month()

    new_products = Product.query.filter(
        extract("month", Product.created_at) == month,
        extract("year",  Product.created_at) == year,
    ).count()

    return {
        "total_products":    Product.query.filter(Product.status == "active").count(),
        "new_added_product": new_products,
        "low_stock_count":   low_stock_count,
        "defects_count":     defects_count,
    }