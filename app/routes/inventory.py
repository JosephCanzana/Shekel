import re
from datetime import datetime
from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorator import role_required
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.inventory import Inventory
from app.extensions import db
from app.utils.helpers import get_product, get_active_categories, is_admin_or_coadmin, validate_product_name, validate_price

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

        # bundle fields (all optional, but all-or-nothing)
        bundle_id    = request.form.get("bundle_id",    "").strip()
        bundle_name  = request.form.get("bundle_name",  "").strip()
        bundle_count = request.form.get("bundle_count", "").strip()

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

        if Product.query.get(product_id):
            flash(f'Product ID "{product_id}" is already in use.', "danger")
            return redirect(url_for("inventory.add"))

        if Product.query.filter(Product.product_name.ilike(product_name)).first():
            flash(f'A product named "{product_name}" already exists.', "danger")
            return redirect(url_for("inventory.add"))

        unit_price    = float(unit_price)
        revenue_price = float(revenue_price)
        product_price = round(unit_price + revenue_price, 2)
        category_id   = int(category_id) if category_id else None

        # ── validate bundle if any bundle field is provided
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
            if ProductBundle.query.get(bundle_id):
                flash(f'Bundle ID "{bundle_id}" is already in use.', "danger")
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

    return render_template("inventory/form.html", categories=categories)


@inventory_bp.route("/<string:product_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin")
def edit(product_id):
    product    = get_product(product_id)
    categories = get_active_categories()

    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("inventory.index"))

    if request.method == "POST":
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

        # ── handle bundle
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
                if ProductBundle.query.get(bundle_id):
                    flash(f'Bundle ID "{bundle_id}" is already in use.', "danger")
                    return redirect(url_for("inventory.edit", product_id=product_id))
                db.session.add(ProductBundle(
                    bundle_id    = bundle_id,
                    product_id   = product_id,
                    bundle_name  = bundle_name,
                    bundle_count = bundle_count
                ))
        else:
            # clear bundle if all fields emptied
            if product.bundle:
                db.session.delete(product.bundle)

        db.session.commit()
        flash(f'Product "{product_name}" has been updated.', "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/form.html",
                           product=product,
                           categories=categories)


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