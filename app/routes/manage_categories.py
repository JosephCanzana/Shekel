from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required
from app.utils.decorator import role_required
from app.models.category import Category
from app.utils.helpers import validate_category_name

manage_categories_bp = Blueprint("manage_categories", __name__, url_prefix="/admin/categories")


@manage_categories_bp.route("/")
@login_required
@role_required("admin", "co-admin")
def index():
    categories      = Category.get_all()
    categories_data = [c.to_dict() for c in categories]
    return render_template("admin/categories/index.html",
                           categories=categories,
                           categories_data=categories_data)


@manage_categories_bp.route("/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin")
def add():
    if request.method == "POST":
        category_name = request.form.get("category_name", "").strip()
        description   = request.form.get("description",   "").strip()

        if not category_name:
            flash("Category name is required.", "danger")
            return redirect(url_for("manage_categories.add"))

        ok, err = validate_category_name(category_name)
        if not ok:
            flash(err, "danger")
            return redirect(url_for("manage_categories.add"))

        existing = Category.query.filter(
            Category.category_name.ilike(category_name)
        ).first()
        if existing:
            flash(f'A category named "{category_name}" already exists.', "danger")
            return redirect(url_for("manage_categories.add"))

        category = Category(
            category_name = category_name.lower(),
            description   = description or None,
            status        = "active"
        )
        category.save()

        flash(f'Category "{category_name}" has been created.', "success")
        return redirect(url_for("manage_categories.index"))

    return render_template("admin/categories/form.html")


@manage_categories_bp.route("/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "co-admin")
def edit(category_id):
    category = Category.get_by_id(category_id)
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for("manage_categories.index"))

    if request.method == "POST":
        category_name = request.form.get("category_name", "").strip()
        description   = request.form.get("description",   "").strip()
        status        = request.form.get("status",        category.status).strip()

        if not category_name:
            flash("Category name is required.", "danger")
            return redirect(url_for("manage_categories.edit", category_id=category_id))

        ok, err = validate_category_name(category_name)
        if not ok:
            flash(err, "danger")
            return redirect(url_for("manage_categories.edit", category_id=category_id))

        existing = Category.query.filter(
            Category.category_name.ilike(category_name),
            Category.category_id != category_id
        ).first()
        if existing:
            flash(f'A category named "{category_name}" already exists.', "danger")
            return redirect(url_for("manage_categories.edit", category_id=category_id))

        category.category_name = category_name.lower()
        category.description   = description or None
        category.status        = status
        category.save()

        flash(f'Category "{category_name}" has been updated.', "success")
        return redirect(url_for("manage_categories.index"))

    return render_template("admin/categories/form.html", category=category)


@manage_categories_bp.route("/<int:category_id>/status_update", methods=["POST"])
@login_required
@role_required("admin", "co-admin")
def status_update(category_id):
    category = Category.get_by_id(category_id)
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for("manage_categories.index"))

    new_status = request.form.get("status", "").strip()
    if new_status not in {"active", "inactive"}:
        flash("Invalid status.", "danger")
        return redirect(request.referrer or url_for("manage_categories.index"))

    category.status = new_status
    category.save()
    flash(f'"{category.category_name}" is now {new_status}.', "success")
    return redirect(request.referrer or url_for("manage_categories.index"))


@manage_categories_bp.route("/<int:category_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete(category_id):
    category = Category.get_by_id(category_id)
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for("manage_categories.index"))

    # TODO: uncomment once Product model is built
    # if category.products:
    #     flash("Cannot delete a category that has products.", "danger")
    #     return redirect(url_for("manage_categories.index"))

    name = category.category_name
    category.delete()
    flash(f'Category "{name}" has been permanently deleted.', "success")
    return redirect(url_for("manage_categories.index"))