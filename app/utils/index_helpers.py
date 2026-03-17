from flask import flash
from datetime import datetime, timedelta
import pytz
from sqlalchemy import extract

from app.models.user import User
from app.models.product import Product
from app.models.sale import Sale
from app.models.inventory import Inventory

from app.utils.helpers import get_time_of_day, pht_now, pht_today, to_pht


def get_admin_stats():
    now_pht = pht_now()

    start_today = now_pht.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today   = start_today + timedelta(days=1)
    start_utc   = start_today.astimezone(pytz.utc)
    end_utc     = end_today.astimezone(pytz.utc)

    # fetch once
    sales_today = Sale.query.filter(
        Sale.sale_datetime >= start_utc,
        Sale.sale_datetime < end_utc
    ).all()

    total_amount_sales = sum(sale.total_amount for sale in sales_today)
    transactions_count = len(sales_today)

    recent_transactions = sorted(sales_today, key=lambda s: s.sale_datetime, reverse=True)[:7]
    recent_transactions_list = [
        {
            "reference": f"TXN-{sale.transaction_id:05d}",
            "cashier":   sale.user.full_name if sale.user else "Unknown",
            "time":      to_pht(sale.sale_datetime).strftime("%I:%M %p"),
            "total":     f"{sale.total_amount:,.2f}",
        }
        for sale in recent_transactions
    ]

    new_products_this_month = Product.query.filter(
        extract('month', Product.created_at) == now_pht.month,
        extract('year',  Product.created_at) == now_pht.year
    ).count()

    low_stock_count = Inventory.query.join(Product).filter(
        Product.status == "active",
        Inventory.quantity_available <= Product.low_reorder_threshold
    ).count()

    return {
        "sales_today":         total_amount_sales,
        "transactions_today":  transactions_count,
        "new_added_product":   new_products_this_month,
        "total_products":      Product.query.count(),
        "low_stock_count":     low_stock_count,
        "defects_count":       0,
        "recent_transactions": recent_transactions_list,
    }

def get_recent_transactions():
    return get_admin_stats()["recent_transactions"]


def get_low_stock_items():
    low_stock = Inventory.query.join(Product).filter(
        Product.status == "active",
        Inventory.quantity_available <= Product.low_reorder_threshold
    ).order_by(Inventory.quantity_available.asc()).limit(5).all()

    return [
        {
            "name":     item.product.product_name.capitalize(),
            "category": item.product.category.category_name if item.product.category else "—",
            "stock":    item.quantity_available,
        }
        for item in low_stock
    ]

def get_defects():
    # each dict: name, reported_by, date, qty
    return []

from app.models.stock_in import StockIn

def get_recent_stockins():
    recent = StockIn.query.order_by(StockIn.stockin_datetime.desc()).limit(5).all()
    return [
        {
            "name":       item.product.product_name.capitalize() if item.product else "Deleted Product",
            "stocked_by": item.user.full_name if item.user else "Unknown",
            "date":       to_pht(item.stockin_datetime).strftime("%b %d, %Y %I:%M %p"),
            "qty":        item.quantity_received,
        }
        for item in recent
        if item.product is not None  # skip fully broken records
    ]

def get_stocking_stats():
    low_stock_count = Inventory.query.join(Product).filter(
        Product.status == "active",
        Inventory.quantity_available <= Product.low_reorder_threshold
    ).count()

    return {
        "total_products":  Product.query.filter(Product.status == "active").count(),
        "low_stock_count": low_stock_count,
        "defects_count":   0,
    }