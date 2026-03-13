import re
from datetime import datetime
from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.models.category import Category
from app.extensions import db
from app.utils.helpers import validate_product_name, validate_price, get_active_categories, get_product, is_admin_or_coadmin, barcode_in_use

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")

@inventory_bp.route("/")
@login_required
@role_required("admin", "co-admin", "stocking")
def index():
    products      = Product.query.order_by(Product.created_at.desc()).all()
    products_data = [p.to_dict() for p in products]
    return render_template("inventory/index.html",
                           products=products,
                           products_data=products_data,
                           can_manage=is_admin_or_coadmin())


@inventory_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin")
def add():
    categories = get_active_categories()

    if request.method == "POST":
        product_id    = request.form.get("product_id",    "").strip()
        product_name  = request.form.get("product_name",  "").strip()
        category_id   = request.form.get("category_id",   "").strip()
        unit_price    = request.form.get("unit_price",    "").strip()
        revenue_price = request.form.get("revenue_price", "").strip()
        low_reorder   = request.form.get("low_reorder_threshold", "").strip()
        bundle_id     = request.form.get("bundle_id",    "").strip()
        bundle_name   = request.form.get("bundle_name",  "").strip()
        bundle_count  = request.form.get("bundle_count", "").strip()

        if not all([product_id, product_name, unit_price, revenue_price, low_reorder]):
            flash("Product ID, name, prices, and low stock threshold are required.", "danger")
            return redirect(url_for("inventory.add"))

        ok, err = validate_product_name(product_name)
        if not ok:
            flash(err, "danger")
            return redirect(url_for("inventory.add"))

        ok, err = validate_price(unit_price, "Unit price")
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

        unit_price    = float(unit_price)
        revenue_price = float(revenue_price)
        product_price = round(unit_price + revenue_price, 2)
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
            unit_price            = unit_price,
            revenue_price         = revenue_price,
            product_price         = product_price,
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

        db.session.commit()
        flash(f'Product "{product_name}" has been created.', "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/form.html",
                           categories=categories,
                           can_manage=True)


@inventory_bp.route("/<string:product_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin", "stocking")   # ← stocking allowed
def edit(product_id):
    product    = get_product(product_id)
    categories = get_active_categories()
    can_manage = is_admin_or_coadmin()

    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("inventory.index"))

    if request.method == "POST":
        new_stock        = request.form.get("quantity_available", "").strip()
        adjustment_notes = request.form.get("adjustment_notes",   "").strip()

        # ── stocking: stock adjustment only ──────────────────────────────────
        if not can_manage:
            if product.inventory and new_stock != "":
                try:
                    new_stock_val = int(new_stock)
                    if new_stock_val < 0:
                        raise ValueError
                    product.inventory.quantity_available = new_stock_val
                    product.inventory.last_updated       = datetime.utcnow()
                    db.session.commit()
                    flash(f'Stock for "{product.product_name}" has been updated.', "success")
                except ValueError:
                    flash("Stock must be a non-negative whole number.", "danger")
            else:
                flash("No stock changes were made.", "info")
            return redirect(url_for("inventory.index"))

        # ── admin / co-admin: full edit ───────────────────────────────────────
        product_name  = request.form.get("product_name",  "").strip()
        category_id   = request.form.get("category_id",   "").strip()
        unit_price    = request.form.get("unit_price",    "").strip()
        revenue_price = request.form.get("revenue_price", "").strip()
        low_reorder   = request.form.get("low_reorder_threshold", "").strip()
        status        = request.form.get("status", product.status).strip()
        bundle_id     = request.form.get("bundle_id",    "").strip()
        bundle_name   = request.form.get("bundle_name",  "").strip()
        bundle_count  = request.form.get("bundle_count", "").strip()

        if not all([product_name, unit_price, revenue_price, low_reorder]):
            flash("Name, prices, and low stock threshold are required.", "danger")
            return redirect(url_for("inventory.edit", product_id=product_id))

        ok, err = validate_product_name(product_name)
        if not ok:
            flash(err, "danger")
            return redirect(url_for("inventory.edit", product_id=product_id))

        ok, err = validate_price(unit_price, "Unit price")
        if not ok:
            flash(err, "danger")
            return redirect(url_for("inventory.edit", product_id=product_id))

        ok, err = validate_price(revenue_price, "Revenue price")
        if not ok:
            flash(err, "danger")
            return redirect(url_for("inventory.edit", product_id=product_id))

        try:
            low_reorder = int(low_reorder)
            if low_reorder < 0:
                raise ValueError
        except ValueError:
            flash("Low stock threshold must be a positive whole number.", "danger")
            return redirect(url_for("inventory.edit", product_id=product_id))

        existing = Product.query.filter(
            Product.product_name.ilike(product_name),
            Product.product_id != product_id
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

        unit_price    = float(unit_price)
        revenue_price = float(revenue_price)
        product_price = round(unit_price + revenue_price, 2)

        product.product_name          = product_name.lower()
        product.category_id           = int(category_id) if category_id else None
        product.unit_price            = unit_price
        product.revenue_price         = revenue_price
        product.product_price         = product_price
        product.low_reorder_threshold = low_reorder
        product.status                = status

        # stock adjustment (admin can also adjust)
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

        # handle bundle
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
                    product_id   = product_id,
                    bundle_name  = bundle_name,
                    bundle_count = bundle_count
                ))
        else:
            if product.bundle:
                db.session.delete(product.bundle)

        db.session.commit()
        flash(f'Product "{product_name}" has been updated.', "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/form.html",
                           product=product,
                           categories=categories,
                           can_manage=can_manage)


@inventory_bp.route("/<string:product_id>/status_update", methods=["POST"])
@login_required
@role_required("admin", "co-admin")
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
    product.save()
    flash(f'"{product.product_name}" is now {new_status}.', "success")
    return redirect(request.referrer or url_for("inventory.index"))


@inventory_bp.route("/<string:product_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete(product_id):
    product = get_product(product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("inventory.index"))

    if product.status != "archived":
        flash("Only archived products can be deleted.", "danger")
        return redirect(url_for("inventory.index"))

    name = product.product_name
    if product.bundle:
        db.session.delete(product.bundle)
    if product.inventory:
        db.session.delete(product.inventory)
    db.session.delete(product)
    db.session.commit()

    flash(f'Product "{name}" has been permanently deleted.', "success")
    return redirect(url_for("inventory.index"))