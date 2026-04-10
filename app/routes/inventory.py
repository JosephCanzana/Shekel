import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text
from sqlalchemy.exc import DataError
from app.extensions import db
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.user_column_preference import UserColumnPreference
from app.models.role_column_setting import RoleColumnSetting
from app.models.stock_adjustment_request import StockAdjustmentRequest
from app.models.stock_adjustment_detail import StockAdjustmentDetail
from app.models.stock_in import StockIn
from app.utils.helpers import validate_product_name, validate_price, get_active_categories, get_product, is_admin_or_coadmin, barcode_in_use, get_category_thresholds, to_pht
from app.utils.decorator import role_required
from app.utils.audit import audit

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")

@inventory_bp.route("/")
@login_required
@role_required("superadmin", "admin", "stocking")
def index():
    products      = Product.query.order_by(Product.created_at.desc()).all()
    products_data = [p.to_dict() for p in products]
    return render_template("inventory/index.html",
                           products=products,
                           products_data=products_data,
                           can_manage=is_admin_or_coadmin())


@inventory_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("superadmin", "admin")
def add():
    categories = get_active_categories()

    if request.method == "POST":
        try:
            product_id    = request.form.get("product_id",    "").strip()
            product_name  = request.form.get("product_name",  "").strip()
            category_id   = request.form.get("category_id",   "").strip()
            cost_price    = request.form.get("cost_price",    "").strip()
            revenue_price = request.form.get("revenue_price", "").strip()
            low_reorder   = request.form.get("low_reorder_threshold", "").strip()
            bundle_id     = request.form.get("bundle_id",    "").strip()
            bundle_count  = request.form.get("bundle_count", "").strip()
            bundle_name   = request.form.get("bundle_name",  f"{bundle_count}/pack").strip()

            if not bundle_count:
                bundle_name = ""

            if not low_reorder and category_id:
                from app.models.category import Category
                cat = Category.query.get(int(category_id))
                if cat:
                    low_reorder = str(cat.default_low_stock_threshold)
    
            if not all([product_id, product_name, cost_price, revenue_price, low_reorder]):
                flash("Product ID, name, prices, and low stock threshold are required.", "danger")
                return redirect(url_for("inventory.add"))

            ok, err = validate_product_name(product_name)
            if not ok:
                flash(err, "danger")
                return redirect(url_for("inventory.add"))

            ok, err = validate_price(cost_price, "Unit price")
            if not ok:
                flash(err, "danger")
                return redirect(url_for("inventory.add"))

            ok, err = validate_price(revenue_price, "Revenue price")
            if not ok:
                flash(err, "danger")
                return redirect(url_for("inventory.add"))

            try:
                low_reorder = int(low_reorder)
                if low_reorder < 0:
                    raise ValueError
            except ValueError:
                flash("Low stock threshold must be a positive whole number.", "danger")
                return redirect(url_for("inventory.add"))

            err = barcode_in_use(product_id)
            if err:
                flash(err, "danger")
                return redirect(url_for("inventory.add"))

            if bundle_id and bundle_id == product_id:
                flash("Product ID and Bundle ID cannot be the same barcode.", "danger")
                return redirect(url_for("inventory.add"))

            cost_price    = float(cost_price)
            revenue_price = float(revenue_price)
            total_price = round(cost_price + revenue_price, 2)
            category_id   = int(category_id) if category_id else None

            has_bundle = any([bundle_id, bundle_name, bundle_count])
            if has_bundle:
                if not all([bundle_id, bundle_name, bundle_count]):
                    flash("Bundle ID, name, and count are all required together.", "danger")
                    return redirect(url_for("inventory.add"))
                try:
                    bundle_count = int(bundle_count)
                    if bundle_count < 2:
                        raise ValueError
                except ValueError:
                    flash("Bundle count must be 2 or more.", "danger")
                    return redirect(url_for("inventory.add"))

                err = barcode_in_use(bundle_id)
                if err:
                    flash(err, "danger")
                    return redirect(url_for("inventory.add"))

            product = Product(
                product_id            = product_id,
                product_name          = product_name.lower(),
                category_id           = category_id,
                cost_price            = cost_price,
                revenue_price         = revenue_price,
                total_price         = total_price,
                low_reorder_threshold = low_reorder,
                status                = "active"
            )
            db.session.add(product)
            db.session.add(Inventory(
                product_id         = product_id,
                quantity_available = 0,
                quantity_defective = 0,
                last_updated       = datetime.utcnow()
            ))
            if has_bundle:
                db.session.add(ProductBundle(
                    bundle_id    = bundle_id,
                    product_id   = product_id,
                    bundle_name  = bundle_name,
                    bundle_count = bundle_count
                ))

            audit(
                "INSERT",
                "Products",
                f'Created product "{product_name}" (ID: {product_id})',
                reference_id=product.product_id,
                reference_table="Products",
                user_id=current_user.user_id
            )
            db.session.commit()
        except DataError:
            db.session.rollback()
            flash("One or more values are out of range. Please check your input.", "danger")
            return redirect(url_for("inventory.add", product_id=product_id))
        
        flash(f'Product "{product_name}" has been created.', "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/form.html",
                             categories=categories,
                             category_thresholds=get_category_thresholds(),
                             can_manage=True)

@inventory_bp.route("/<string:product_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("superadmin", "admin", "stocking")  
def edit(product_id):
    product    = get_product(product_id)
    categories = get_active_categories()
    can_manage = is_admin_or_coadmin()

    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("inventory.index"))

    if request.method == "POST":
        try:
            new_stock        = request.form.get("quantity_available", "").strip()
            adjustment_notes = request.form.get("adjustment_notes",   "").strip()

            # ── stocking: stock adjustment → pending request ──────────────────────────
            if not can_manage:
                new_stock    = request.form.get("quantity_available", "").strip()
                item_notes   = request.form.get("adjustment_notes",  "").strip()

                if new_stock == "":
                    flash("No stock changes were made.", "info")
                    return redirect(url_for("inventory.index"))

                try:
                    new_stock_val = int(new_stock)
                    if new_stock_val < 0 or new_stock_val > 2_147_483_647:
                        raise ValueError
                except ValueError:
                    flash("Stock must be a non-negative whole number.", "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))

                current_stock = product.inventory.quantity_available if product.inventory else 0

                if new_stock_val == current_stock:
                    flash("No change detected — stock is already at that value.", "info")
                    return redirect(url_for("inventory.index"))

                from app.models.stock_adjustment_request import StockAdjustmentRequest
                from app.models.stock_adjustment_detail  import StockAdjustmentDetail

                req = StockAdjustmentRequest(
                    requested_by = current_user.user_id,
                    request_type = "adjustment",
                    status       = "pending",
                    submitted_at = datetime.utcnow()
                )
                db.session.add(req)
                db.session.flush()

                db.session.add(StockAdjustmentDetail(
                    request_id         = req.request_id,
                    product_id         = product_id,
                    quantity_requested = new_stock_val,
                    quantity_approved  = None,
                    status             = "pending",
                    note               = item_notes or None,
                ))

                try:
                    db.session.commit()
                    flash(f'Adjustment request submitted for "{product.product_name.capitalize()}". Awaiting admin approval.', "success")
                except Exception:
                    db.session.rollback()
                    flash("Failed to submit request. Please try again.", "danger")

                return redirect(url_for("inventory.index"))

            # ── admin / co-admin: full edit ───────────────────────────────────────
            product_id_new = request.form.get("product_id", "").strip()
            product_name  = request.form.get("product_name",  "").strip()
            category_id   = request.form.get("category_id",   "").strip()
            cost_price    = request.form.get("cost_price",    "").strip()
            revenue_price = request.form.get("revenue_price", "").strip()
            low_reorder   = request.form.get("low_reorder_threshold", "").strip()
            status        = request.form.get("status", product.status).strip()
            bundle_id     = request.form.get("bundle_id",    "").strip()
            bundle_count  = request.form.get("bundle_count", "").strip()
            bundle_name   = request.form.get("bundle_name",  f"{bundle_count}/pack").strip()

            if not bundle_count:
                bundle_name = ""

            if not low_reorder and category_id:
                from app.models.category import Category
                cat = Category.query.get(int(category_id))
                if cat:
                    low_reorder = str(cat.default_low_stock_threshold)
    
            if not all([product_id_new, product_name, cost_price, revenue_price, low_reorder]):
                flash("Name, prices, and low stock threshold are required.", "danger")
                return redirect(url_for("inventory.edit", product_id=product_id))

            ok, err = validate_product_name(product_name)
            if not ok:
                flash(err, "danger")
                return redirect(url_for("inventory.edit", product_id=product_id))

            ok, err = validate_price(cost_price, "Unit price")
            if not ok:
                flash(err, "danger")
                return redirect(url_for("inventory.edit", product_id=product_id))

            ok, err = validate_price(revenue_price, "Revenue price")
            if not ok:
                flash(err, "danger")
                return redirect(url_for("inventory.edit", product_id=product_id))

            try:
                low_reorder = int(low_reorder)
                if low_reorder < 0 or low_reorder > 2_147_483_647:
                    raise ValueError
            except ValueError:
                flash("Low stock threshold must be a positive whole number.", "danger")
                return redirect(url_for("inventory.edit", product_id=product_id))

            id_changing = product_id_new != product_id
            if id_changing:
                err = barcode_in_use(
                    product_id_new,
                    exclude_product_id=product_id,
                    exclude_bundle_id=product.bundle.bundle_id if product.bundle else None
                )
                if err:
                    flash(err, "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))

                product.product_id = product_id_new
                db.session.flush()
                db.session.expire(product)
                product = db.session.get(Product, product_id_new)

            existing = Product.query.filter(
                Product.product_name.ilike(product_name),
                Product.product_id != product_id_new
            ).first()
            if existing:
                flash(f'A product named "{product_name}" already exists.', "danger")
                return redirect(url_for("inventory.edit", product_id=product_id))

            if bundle_id:
                err = barcode_in_use(
                    bundle_id,
                    exclude_product_id=product_id,
                    exclude_bundle_id=product.bundle.bundle_id if product.bundle else None
                )
                if err:
                    flash(err, "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))

            cost_price    = float(cost_price)
            revenue_price = float(revenue_price)
            total_price = round(cost_price + revenue_price, 2)

            if id_changing:
                with db.session.no_autoflush:
                    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                    db.session.execute(
                        text("UPDATE Products SET product_id = :new WHERE product_id = :old"),
                        {"new": product_id_new, "old": product_id}
                    )
                    db.session.execute(
                        text("UPDATE Inventory SET product_id = :new WHERE product_id = :old"),
                        {"new": product_id_new, "old": product_id}
                    )
                    db.session.execute(
                        text("UPDATE ProductBundles SET product_id = :new WHERE product_id = :old"),
                        {"new": product_id_new, "old": product_id}
                    )
                    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
                db.session.expire(product)
                product = db.session.get(Product, product_id_new)

            product.product_name          = product_name.lower()
            product.category_id           = int(category_id) if category_id else None
            product.cost_price            = cost_price
            product.revenue_price         = revenue_price
            product.total_price         = total_price
            product.low_reorder_threshold = low_reorder
            product.status                = status

            if product.inventory and new_stock != "":
                try:
                    new_stock_val = int(new_stock)
                    if new_stock_val < 0:
                        raise ValueError
                    product.inventory.quantity_available = new_stock_val
                    product.inventory.last_updated       = datetime.utcnow()
                except ValueError:
                    flash("Stock must be a non-negative whole number.", "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))

            has_bundle = any([bundle_id, bundle_name, bundle_count])
            if has_bundle:
                if not all([bundle_id, bundle_name, bundle_count]):
                    flash("Bundle ID, name, and count are all required together.", "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))
                try:
                    bundle_count = int(bundle_count)
                    if bundle_count < 2:
                        raise ValueError
                except ValueError:
                    flash("Bundle count must be 2 or more.", "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))

                if product.bundle:
                    product.bundle.bundle_id    = bundle_id
                    product.bundle.bundle_name  = bundle_name
                    product.bundle.bundle_count = bundle_count
                else:
                    db.session.add(ProductBundle(
                        bundle_id    = bundle_id,
                        product_id   = product_id_new,
                        bundle_name  = bundle_name,
                        bundle_count = bundle_count
                    ))
            else:
                if product.bundle:
                    db.session.delete(product.bundle)

            audit(
                "UPDATE",
                "Products",
                f'Updated product "{product_name}" (ID: {product.product_id})',
                reference_id=product.product_id,
                reference_table="Products",
                user_id=current_user.user_id
            )
            db.session.commit()

        except DataError:
            db.session.rollback()
            flash("One or more values are out of range. Please check your input.", "danger")
            return redirect(url_for("inventory.edit", product_id=product_id))

        flash(f'Product "{product_name}" has been updated.', "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/form.html",
                             product=product,
                             categories=categories,
                             category_thresholds=get_category_thresholds(),
                             can_manage=can_manage)

@inventory_bp.route("/<string:product_id>/status_update", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def status_update(product_id):
    product = get_product(product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("inventory.index"))

    new_status = request.form.get("status", "").strip()
    if new_status not in {"active", "archived"}:
        flash("Invalid status.", "danger")
        return redirect(request.referrer or url_for("inventory.index"))

    product.status = new_status
    audit(
        "UPDATE",
        "Products",
        f'Status of "{product.product_name}" (ID: {product.product_id}) changed to {new_status}',
        reference_table="Products",
        user_id=current_user.user_id
    )
    product.save()
    flash(f'"{product.product_name}" is now {new_status}.', "success")
    return redirect(request.referrer or url_for("inventory.index"))


@inventory_bp.route("/<string:product_id>/delete", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def delete(product_id):
    product = get_product(product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("inventory.index"))

    if product.status != "archived":
        flash("Only archived products can be deleted.", "danger")
        return redirect(url_for("inventory.index"))

    from app.models.sale_detail    import SaleDetail
    from app.models.defect_detail  import DefectDetail
    has_sales   = SaleDetail.query.filter_by(product_id=product_id).first()
    has_defects = DefectDetail.query.filter_by(product_id=product_id).first()
    if has_sales or has_defects:
        flash(
            f'"{product.product_name.capitalize()}" cannot be deleted because it has '
            f'transaction or defect history. Archiving it is the correct action.',
            "danger"
        )
        return redirect(url_for("inventory.index"))

    name = product.product_name
    if product.bundle:
        db.session.delete(product.bundle)
    if product.inventory:
        db.session.delete(product.inventory)
    audit(
        action_type="DELETE",
        module="Products",
        description=f'Product "{name}" (ID: {product.product_id}) permanently deleted',
        reference_id=None,  # cannot use string barcode for INT column
        reference_table="Products",
        user_id=current_user.user_id
        )
    db.session.delete(product)
    db.session.commit()

    flash(f'Product "{name}" has been permanently deleted.', "success")
    return redirect(url_for("inventory.index"))

import json
from app.models.user_column_preference import UserColumnPreference
from app.models.role_column_setting    import RoleColumnSetting

# ── Default columns per role ──────────────────────────────────────────────────
ROLE_COLUMN_DEFAULTS = {
    "superadmin": {
        "available": ["sku", "bundle_barcode", "bundle_name", "units_per_bundle",
                      "stock", "unit_cost", "unit_revenue", "unit_price",
                      "bundle_cost", "bundle_revenue", "bundle_price",
                      "stock_cost_value", "stock_revenue_value", "stock_total_value",
                      "category", "low_stock_threshold", "status", "last_updated"],
        "defaults":  ["stock", "unit_price", "stock_total_value", "low_stock_threshold"]
    },
    "admin": {
        "available": ["sku", "bundle_barcode", "bundle_name", "units_per_bundle",
                      "stock", "unit_cost", "unit_revenue", "unit_price",
                      "bundle_cost", "bundle_revenue", "bundle_price",
                      "stock_cost_value", "stock_revenue_value", "stock_total_value",
                      "category", "low_stock_threshold", "status", "last_updated"],
        "defaults":  ["stock", "unit_price", "stock_total_value", "low_stock_threshold"]
    },
    "stocking": {
        "available": ["sku", "bundle_name", "stock", "unit_price",
                      "bundle_price", "stock_total_value",
                      "category", "low_stock_threshold", "status", "last_updated"],
        "defaults":  ["stock", "unit_price", "low_stock_threshold"]
    }
}


# ── GET column preferences ────────────────────────────────────────────────────
@inventory_bp.route("/api/column-preferences", methods=["GET"])
@login_required
@role_required("superadmin", "admin", "stocking")
def get_column_preferences():
    page = request.args.get("page", "inventory")
    role = current_user.role

    pref = UserColumnPreference.query.filter_by(
        user_id=current_user.user_id, page=page
    ).first()

    role_setting = RoleColumnSetting.query.filter_by(role=role, page=page).first()

    if role_setting:
        available = json.loads(role_setting.available)
        defaults  = json.loads(role_setting.defaults)
    else:
        available = ROLE_COLUMN_DEFAULTS.get(role, {}).get("available", [])
        defaults  = ROLE_COLUMN_DEFAULTS.get(role, {}).get("defaults",  [])

    if role == "superadmin":
        available = ROLE_COLUMN_DEFAULTS["superadmin"]["available"]

    if pref:
        columns = [c for c in json.loads(pref.columns) if c in available]
    else:
        columns = defaults

    return jsonify({
        "columns":   columns,
        "available": available,
        "defaults":  defaults
    })


# ── POST save column preferences ─────────────────────────────────────────────
@inventory_bp.route("/api/column-preferences", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
def save_column_preferences():
    data    = request.json or {}
    page    = data.get("page", "inventory")
    columns = data.get("columns", [])
    role    = current_user.role

    role_setting = RoleColumnSetting.query.filter_by(role=role, page=page).first()
    if role_setting:
        available = json.loads(role_setting.available)
    else:
        available = ROLE_COLUMN_DEFAULTS.get(role, {}).get("available", [])

    if role == "superadmin":
        available = ROLE_COLUMN_DEFAULTS["superadmin"]["available"]

    columns = [c for c in columns if c in available]

    pref = UserColumnPreference.query.filter_by(
        user_id=current_user.user_id, page=page
    ).first()

    if pref:
        pref.columns = json.dumps(columns)
    else:
        db.session.add(UserColumnPreference(
            user_id=current_user.user_id,
            page=page,
            columns=json.dumps(columns)
        ))

    db.session.commit()
    return jsonify({"ok": True, "columns": columns})


# ── POST inline threshold update ──────────────────────────────────────────────
@inventory_bp.route("/<string:product_id>/threshold", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def update_threshold(product_id):
    product = get_product(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    try:
        threshold = int((request.json or {}).get("threshold", -1))
        if threshold < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Threshold must be a positive whole number."}), 400

    product.low_reorder_threshold = threshold
    audit(
        action_type="UPDATE",
        module="Products",
        description=f'Threshold for "{product.product_name}" (ID: {product.product_id}) changed to {threshold}',
        reference_id=None,  # cannot use string barcode
        reference_table="Products",
        user_id=current_user.user_id
        )
    db.session.commit()
    return jsonify({"ok": True, "threshold": threshold})

@inventory_bp.route("/bulk/status-update", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def bulk_status_update():
    data        = request.json or {}
    product_ids = data.get("product_ids", [])
    new_status  = data.get("status", "")

    if not product_ids:
        return jsonify({"error": "No products selected."}), 400
    if new_status not in {"active", "archived"}:
        return jsonify({"error": "Invalid status."}), 400

    products = Product.query.filter(Product.product_id.in_(product_ids)).all()
    for p in products:
        p.status = new_status

    audit("UPDATE", "Inventory",
          f"Bulk status update to '{new_status}' for {len(products)} product(s): "
          f"IDs {product_ids}")

    db.session.commit()
    return jsonify({"ok": True, "updated": len(products)})


@inventory_bp.route("/bulk/delete", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def bulk_delete():
    from app.models.sale_detail   import SaleDetail
    from app.models.defect_detail import DefectDetail

    data        = request.json or {}
    product_ids = data.get("product_ids", [])

    if not product_ids:
        return jsonify({"error": "No products selected."}), 400

    skipped = []
    deleted = []

    for pid in product_ids:
        product = get_product(pid)
        if not product:
            continue
        if product.status != "archived":
            skipped.append(pid)
            continue

        has_sales   = SaleDetail.query.filter_by(product_id=pid).first()
        has_defects = DefectDetail.query.filter_by(product_id=pid).first()
        if has_sales or has_defects:
            skipped.append(pid)
            continue

        if product.bundle:
            db.session.delete(product.bundle)
        if product.inventory:
            db.session.delete(product.inventory)
        db.session.delete(product)
        deleted.append(pid)

    if deleted:
        audit("DELETE", "Inventory",
              f"Bulk deleted {len(deleted)} product(s): IDs {deleted}"
              + (f" — skipped {len(skipped)}: IDs {skipped}" if skipped else ""))

    db.session.commit()
    return jsonify({"ok": True, "deleted": len(deleted), "skipped": len(skipped)})


# ── POST bulk threshold update ────────────────────────────────────────────────
@inventory_bp.route("/bulk/threshold-update", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def bulk_threshold_update():
    data        = request.json or {}
    product_ids = data.get("product_ids", [])
    threshold   = data.get("threshold")

    if not product_ids:
        return jsonify({"error": "No products selected."}), 400

    try:
        threshold = int(threshold)
        if threshold < 0 or threshold > 2_147_483_647:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Threshold must be a non-negative whole number."}), 400

    products = Product.query.filter(Product.product_id.in_(product_ids)).all()
    for p in products:
        p.low_reorder_threshold = threshold
    
    if products:
        product_names = ", ".join(p.product_name.capitalize() for p in products)
        audit(
            action_type="UPDATE",
            module="Inventory",
            description=f"Bulk updated low stock threshold to {threshold} for {len(products)} product(s): {product_names}",
            reference_id=None,
            reference_table="Products",
            user_id=current_user.user_id
        )

    db.session.commit()
    return jsonify({"ok": True, "updated": len(products), "threshold": threshold})


# ── POST bulk category update ─────────────────────────────────────────────────
@inventory_bp.route("/bulk/category-update", methods=["POST"])
@login_required
@role_required("superadmin", "admin")
def bulk_category_update():
    """
    Assigns a single category to multiple products at once.
    Expects: { "product_ids": [...], "category_id": <int> }
    """
    from app.models.category import Category

    data        = request.json or {}
    product_ids = data.get("product_ids", [])
    category_id = data.get("category_id")

    if not product_ids:
        return jsonify({"error": "No products selected."}), 400

    if category_id is None:
        return jsonify({"error": "No category selected."}), 400

    try:
        category_id = int(category_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid category ID."}), 400

    category = Category.query.get(category_id)
    if not category:
        return jsonify({"error": "Category not found."}), 404

    products = Product.query.filter(Product.product_id.in_(product_ids)).all()
    for p in products:
        p.category_id = category_id

    if products:
        audit(
            action_type="UPDATE",
            module="Inventory",
            description=(
                f"Bulk updated category to '{category.category_name}' (ID: {category_id}) "
                f"for {len(products)} product(s): IDs {[p.product_id for p in products]}"
            ),
            reference_id=None,
            reference_table="Products",
            user_id=current_user.user_id
        )

    db.session.commit()
    return jsonify({
        "ok":            True,
        "updated":       len(products),
        "category_id":   category_id,
        "category_name": category.category_name,
    })


@inventory_bp.route("/adjust", methods=["GET"])
@login_required
@role_required("superadmin", "admin", "stocking")
def adjust():
    raw_ids = request.args.get("ids", "").strip()
    if not raw_ids:
        flash("No products selected.", "warning")
        return redirect(url_for("inventory.index"))

    product_ids = [i.strip() for i in raw_ids.split(",") if i.strip()]
    products    = Product.query.filter(Product.product_id.in_(product_ids)).all()

    if not products:
        flash("No valid products found.", "warning")
        return redirect(url_for("inventory.index"))

    products_data = [p.to_dict() for p in products]

    return render_template(
        "inventory/adjust.html",
        products_data = products_data,
        can_manage    = is_admin_or_coadmin(),
    )


@inventory_bp.route("/adjust/submit", methods=["POST"])
@login_required
@role_required("superadmin", "admin", "stocking")
def adjust_submit():
    data  = request.json or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "No items provided."}), 400

    is_privileged = current_user.role in ("admin", "superadmin")

    # ── PATH A: admin / superadmin — apply stock changes immediately ──────────
    if is_privileged:
        for item in items:
            product_id    = item.get("product_id")
            note          = item.get("note", "").strip() or None
            new_threshold = item.get("new_threshold")

            try:
                new_qty = int(item.get("new_qty", 0))
                if new_qty < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid quantity for '{product_id}'."}), 400

            product = Product.query.get(product_id)
            if not product or product.status == "archived":
                return jsonify({"error": f'Product "{product_id}" not found or archived.'}), 400

            if product.inventory:
                old_qty = product.inventory.quantity_available
                product.inventory.quantity_available = new_qty
                product.inventory.last_updated       = datetime.utcnow()
            else:
                old_qty = 0
                db.session.add(Inventory(
                    product_id         = product_id,
                    quantity_available = new_qty,
                    quantity_defective = 0,
                    last_updated       = datetime.utcnow(),
                ))

            delta = new_qty - old_qty
            if delta != 0:
                db.session.add(StockIn(
                    product_id        = product_id,
                    user_id           = current_user.user_id,
                    quantity_received = delta,
                    stockin_datetime  = datetime.utcnow(),
                    notes             = note,
                ))

            if new_threshold is not None:
                try:
                    threshold_val = int(new_threshold)
                    if 0 <= threshold_val <= 2_147_483_647:
                        product.low_reorder_threshold = threshold_val
                except (ValueError, TypeError):
                    pass

        try:
            audit("UPDATE", "Inventory",
                f"Direct stock adjustment for {len(items)} product(s) by {current_user.first_name}",
                reference_table="Inventory")
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Failed to save. Please try again."}), 500

        return jsonify({"success": True, "mode": "direct"})

    # ── PATH B: stocking — create pending request for stock qty ───────────────
    req = StockAdjustmentRequest(
        requested_by = current_user.user_id,
        request_type = "adjustment",
        status       = "pending",
        submitted_at = datetime.utcnow(),
    )
    db.session.add(req)
    audit("INSERT", "Stock_In",
      f"Stock adjustment request submitted for {len(items)} product(s)",
      reference_id=req.request_id, reference_table="Stock_Adjustment_Requests")
    db.session.flush()

    for item in items:
        product_id    = item.get("product_id")
        note          = item.get("note", "").strip() or None
        new_threshold = item.get("new_threshold")

        try:
            new_qty = int(item.get("new_qty", 0))
            if new_qty < 0:
                raise ValueError
        except (ValueError, TypeError):
            db.session.rollback()
            return jsonify({"error": f"Invalid quantity for '{product_id}'."}), 400

        product = Product.query.get(product_id)
        if not product or product.status == "archived":
            db.session.rollback()
            return jsonify({"error": f'Product "{product_id}" not found or archived.'}), 400

        db.session.add(StockAdjustmentDetail(
            request_id         = req.request_id,
            product_id         = product_id,
            quantity_requested = new_qty,
            quantity_approved  = None,
            status             = "pending",
            note               = note,
        ))

        if new_threshold is not None:
            try:
                threshold_val = int(new_threshold)
                if 0 <= threshold_val <= 2_147_483_647:
                    product.low_reorder_threshold = threshold_val
            except (ValueError, TypeError):
                pass

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit request. Please try again."}), 500

    return jsonify({"success": True, "mode": "pending", "request_id": req.request_id})