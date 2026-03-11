from datetime import datetime


# ── helper ────────────────────────────────────────────────────────────────────

def get_time_of_day():
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 18:
        return "afternoon"
    return "evening"


# ── placeholder data — replace with real queries later ───────────────────────

def get_admin_stats():
    return {
        "sales_today":        "0.00",
        "transactions_today": 0,
        "inventory_value":    "0.00",
        "total_products":     0,
        "low_stock_count":    0,
        "defects_count":      0,
    }

def get_recent_transactions():
    # each dict: reference, cashier, time, total
    return []

def get_low_stock_items():
    # each dict: name, category, stock
    return []

def get_defects():
    # each dict: name, reported_by, date, qty
    return []

def get_recent_stockins():
    # each dict: name, stocked_by, date, qty
    return []

def get_stocking_stats():
    return {
        "total_products":  0,
        "low_stock_count": 0,
        "defects_count":   0,
    }
