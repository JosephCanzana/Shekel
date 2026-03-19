"""
tests/audit_log_test.py

Pytest suite for AuditLog model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - All nullable=False columns individually tested
   - reference_id and reference_table are nullable (optional context fields)
   - action_datetime auto-populated via server_default
   - log_id autoincrements
   - Multiple audit logs allowed per user

2. Enum Constraints — action_type
   - All 5 valid values accepted: INSERT, UPDATE, DELETE, LOGIN, LOGOUT
   - Invalid values rejected (requires validate_strings=True in model)

3. Enum Constraints — module
   - All 6 valid values accepted
   - Invalid values rejected (requires validate_strings=True in model)

4. Foreign Key Constraints
   - user_id must reference an existing User row
   - Invalid user_id is blocked

5. Optional Fields Behavior
   - reference_id is nullable — logs without a reference_id save cleanly
   - reference_table is nullable — logs without a reference_table save cleanly
   - Both optional fields can be set and cleared independently

6. Update Behavior
   - description, reference_id, reference_table can be updated and persisted
   - NOTE: Audit logs are typically immutable — but model allows updates,
     so behavior is documented here

7. Relationship — User ↔ AuditLog
   - audit_log.user returns the linked User instance
   - user.audit_logs returns list of all logs for the user
   - Traversal to user fields works (used in audit log display routes)

8. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with AuditLog's specific schema

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.

NOTE: Add validate_strings=True inside db.Enum() in audit_log.py:
    action_type = db.Column(db.Enum("INSERT","UPDATE","DELETE","LOGIN","LOGOUT",
                                     validate_strings=True), nullable=False)
    module      = db.Column(db.Enum("products","inventory","sales","defects",
                                     "users","stock_in", validate_strings=True),
                             nullable=False)
"""

import pytest
from datetime import datetime
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.user import User


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(user):
    """
    Returns a dict of all valid fields for an AuditLog entry.
    reference_id and reference_table are included but nullable —
    tested both ways below.
    """
    return dict(
        user_id=user.user_id,
        action_type="INSERT",
        module="products",
        description="Created a new product entry",
        reference_id=1,
        reference_table="Products",
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are enforced by the DB
#          and that nullable columns (reference_id, reference_table)
#          accept None cleanly.
#    WHY:  Audit logs are the system's accountability trail. A log entry
#          saved without an action_type, module, or description would be
#          meaningless and untraceable. Missing user_id breaks the ability
#          to attribute actions to staff members.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_audit_log_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should commit cleanly
        AuditLog(**valid_data).save()
        assert AuditLog.query.count() == 1

    def test_user_id_is_required(self, app, valid_data):
        # user_id is FK and NOT NULL — every log must be attributed to a user
        valid_data.pop("user_id")
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()

    def test_action_type_is_required(self, app, valid_data):
        # action_type is NOT NULL — what kind of action was performed
        valid_data.pop("action_type")
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()

    def test_module_is_required(self, app, valid_data):
        # module is NOT NULL — which area of the system was affected
        valid_data.pop("module")
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()

    def test_description_is_required(self, app, valid_data):
        # description is NOT NULL — human-readable explanation of the action
        valid_data.pop("description")
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()

    def test_reference_id_is_optional(self, app, valid_data):
        # reference_id is nullable — not all actions reference a specific row
        # e.g. LOGIN and LOGOUT have no meaningful reference_id
        valid_data.pop("reference_id")
        AuditLog(**valid_data).save()

        result = AuditLog.query.first()
        assert result.reference_id is None

    def test_reference_table_is_optional(self, app, valid_data):
        # reference_table is nullable — same reasoning as reference_id
        valid_data.pop("reference_table")
        AuditLog(**valid_data).save()

        result = AuditLog.query.first()
        assert result.reference_table is None

    def test_both_reference_fields_can_be_omitted(self, app, valid_data):
        # Both optional fields can be omitted together — e.g. for LOGIN logs
        valid_data.pop("reference_id")
        valid_data.pop("reference_table")
        AuditLog(**valid_data).save()

        result = AuditLog.query.first()
        assert result.reference_id is None
        assert result.reference_table is None

    def test_log_id_autoincrements(self, app, valid_data):
        # Each new AuditLog gets a higher log_id automatically
        log1 = AuditLog(**valid_data).save()
        log2 = AuditLog(**{**valid_data}).save()

        assert log2.log_id > log1.log_id

    def test_action_datetime_is_set_automatically(self, app, audit_log):
        # action_datetime uses server_default=db.func.now() —
        # it should be populated without being set manually
        result = AuditLog.get_by_id(audit_log.log_id)
        assert result.action_datetime is not None
        assert isinstance(result.action_datetime, datetime)

    def test_multiple_logs_allowed_per_user(self, app, valid_data):
        # A user can have many audit log entries — no unique constraint
        AuditLog(**valid_data).save()
        AuditLog(**{**valid_data}).save()
        AuditLog(**{**valid_data}).save()

        assert AuditLog.query.count() == 3

    def test_description_accepts_long_text(self, app, valid_data):
        # description is db.Text — should accept long strings without truncation
        long_desc = "Performed action. " * 100
        valid_data["description"] = long_desc
        AuditLog(**valid_data).save()

        result = AuditLog.query.first()
        assert result.description == long_desc

    def test_reference_table_max_length(self, app, valid_data):
        # reference_table is db.String(50) — accepts up to 50 characters
        valid_data["reference_table"] = "T" * 50
        AuditLog(**valid_data).save()

        result = AuditLog.query.first()
        assert len(result.reference_table) == 50


# ---------------------------------------------------------------------------
# 2. Enum Constraints — action_type
#
#    WHAT: Verifies only valid action_type values are accepted.
#    WHY:  action_type drives filtering and display in audit log reports.
#          An invalid action_type like "EDIT" or "VIEW" would silently
#          slip into the DB and corrupt report groupings. validate_strings=True
#          catches this at the SQLAlchemy level before hitting the DB.
# ---------------------------------------------------------------------------

class TestActionTypeEnum:
    @pytest.mark.parametrize("valid_action", [
        "INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT"
    ])
    def test_valid_action_type_values_accepted(self, app, valid_data, valid_action):
        # Each valid action_type enum value saves without error
        valid_data["action_type"] = valid_action
        AuditLog(**valid_data).save()
        assert AuditLog.query.filter_by(action_type=valid_action).count() == 1

    @pytest.mark.parametrize("invalid_action", [
        "EDIT", "VIEW", "CREATE", "REMOVE", "", "insert", "Insert"
    ])
    def test_invalid_action_type_values_rejected(self, app, valid_data, invalid_action):
        # Invalid action_type values outside the enum should raise an error
        # Requires validate_strings=True in model for SQLite enforcement
        valid_data["action_type"] = invalid_action
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()


# ---------------------------------------------------------------------------
# 3. Enum Constraints — module
#
#    WHAT: Verifies only valid module values are accepted.
#    WHY:  module is used to filter audit logs by system area in the
#          admin dashboard. An invalid module like "settings" or "reports"
#          would create ungroupable log entries that break the filter UI.
# ---------------------------------------------------------------------------

class TestModuleEnum:
    @pytest.mark.parametrize("valid_module", [
        "products", "inventory", "sales", "defects", "users", "stock_in"
    ])
    def test_valid_module_values_accepted(self, app, valid_data, valid_module):
        # Each valid module enum value saves without error
        valid_data["module"] = valid_module
        AuditLog(**valid_data).save()
        assert AuditLog.query.filter_by(module=valid_module).count() == 1

    @pytest.mark.parametrize("invalid_module", [
        "settings", "reports", "audit", "", "Products", "SALES"
    ])
    def test_invalid_module_values_rejected(self, app, valid_data, invalid_module):
        # Invalid module values outside the enum should raise an error
        valid_data["module"] = invalid_module
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()


# ---------------------------------------------------------------------------
# 4. Foreign Key Constraints
#
#    WHAT: Verifies that user_id must reference a real User row.
#    WHY:  Every audit log must be attributable to a real staff member.
#          An orphan log with a nonexistent user_id breaks the audit trail
#          and causes any route that accesses audit_log.user to crash or
#          return None silently.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_user_id_raises(self, app, valid_data):
        # Nonexistent user_id should be blocked by FK constraint
        valid_data["user_id"] = 99999999
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()

    def test_valid_user_id_saves(self, app, valid_data):
        # Confirm FK with a real user_id saves cleanly
        AuditLog(**valid_data).save()
        assert AuditLog.query.count() == 1

    def test_log_blocked_after_user_deleted(self, app, valid_data, user):
        # After the referenced user is deleted, inserting a new log
        # with that user_id should be blocked by FK constraint
        user.delete()
        with pytest.raises(Exception):
            AuditLog(**valid_data).save()


# ---------------------------------------------------------------------------
# 5. Optional Fields Behavior
#
#    WHAT: Verifies reference_id and reference_table behave correctly
#          in all combinations — set, unset, and mixed.
#    WHY:  Different action types warrant different reference usage:
#          INSERT/UPDATE/DELETE → reference_id + reference_table set
#          LOGIN/LOGOUT         → both None (no DB record being changed)
#          Ensuring both combinations work prevents silent data loss
#          when logging actions without a target record.
# ---------------------------------------------------------------------------

class TestOptionalFields:
    def test_log_with_all_optional_fields_set(self, app, valid_data):
        # Both reference fields can be set — typical for CRUD actions
        AuditLog(**valid_data).save()
        result = AuditLog.query.first()

        assert result.reference_id == 1
        assert result.reference_table == "Products"

    def test_log_with_only_reference_id_set(self, app, valid_data):
        # reference_table can be None while reference_id is set
        valid_data.pop("reference_table")
        AuditLog(**valid_data).save()
        result = AuditLog.query.first()

        assert result.reference_id == 1
        assert result.reference_table is None

    def test_log_with_only_reference_table_set(self, app, valid_data):
        # reference_id can be None while reference_table is set
        valid_data.pop("reference_id")
        AuditLog(**valid_data).save()
        result = AuditLog.query.first()

        assert result.reference_id is None
        assert result.reference_table == "Products"

    def test_login_log_with_no_reference_fields(self, app, user):
        # LOGIN action has no target record — both reference fields are None
        log = AuditLog(
            user_id=user.user_id,
            action_type="LOGIN",
            module="users",
            description="User logged in",
        )
        log.save()

        result = AuditLog.query.first()
        assert result.action_type == "LOGIN"
        assert result.reference_id is None
        assert result.reference_table is None

    def test_logout_log_with_no_reference_fields(self, app, user):
        # LOGOUT action similarly needs no reference fields
        log = AuditLog(
            user_id=user.user_id,
            action_type="LOGOUT",
            module="users",
            description="User logged out",
        )
        log.save()

        result = AuditLog.query.first()
        assert result.action_type == "LOGOUT"
        assert result.reference_id is None
        assert result.reference_table is None


# ---------------------------------------------------------------------------
# 6. Update Behavior
#
#    WHAT: Verifies that description, reference_id, and reference_table
#          can be changed after the fact.
#    WHY:  Audit logs are ideally immutable, but the model does not enforce
#          immutability at the DB level. These tests document that updates
#          ARE possible — a future developer can add immutability constraints
#          if needed, and these tests will catch that change.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_description(self, app, audit_log):
        # Description can be corrected after initial save
        audit_log.description = "Updated description after correction"
        audit_log.save()

        result = AuditLog.get_by_id(audit_log.log_id)
        assert result.description == "Updated description after correction"

    def test_update_reference_id(self, app, audit_log):
        # reference_id can be corrected if wrong record was referenced
        audit_log.reference_id = 999
        audit_log.save()

        result = AuditLog.get_by_id(audit_log.log_id)
        assert result.reference_id == 999

    def test_update_reference_table(self, app, audit_log):
        # reference_table can be corrected
        audit_log.reference_table = "Categories"
        audit_log.save()

        result = AuditLog.get_by_id(audit_log.log_id)
        assert result.reference_table == "Categories"

    def test_clear_reference_id_to_none(self, app, audit_log):
        # reference_id can be cleared — it is nullable
        audit_log.reference_id = None
        audit_log.save()

        result = AuditLog.get_by_id(audit_log.log_id)
        assert result.reference_id is None

    def test_clear_reference_table_to_none(self, app, audit_log):
        # reference_table can be cleared — it is nullable
        audit_log.reference_table = None
        audit_log.save()

        result = AuditLog.get_by_id(audit_log.log_id)
        assert result.reference_table is None


# ---------------------------------------------------------------------------
# 7. Relationship — User ↔ AuditLog
#
#    WHAT: Verifies both sides of the AuditLog ↔ User relationship.
#    WHY:  audit_log.user is used in the admin audit log view to display
#          which staff member performed each action. user.audit_logs is
#          used to pull the full activity history for a given user.
#          A broken relationship silently returns None, making logs
#          render without usernames — a critical accountability failure.
# ---------------------------------------------------------------------------

class TestUserRelationship:
    def test_audit_log_user_returns_linked_user(self, app, audit_log, user):
        # audit_log.user should return the User who performed the action
        db.session.refresh(audit_log)
        assert audit_log.user is not None
        assert audit_log.user.user_id == user.user_id

    def test_user_audit_logs_returns_list(self, app, audit_log, user):
        # user.audit_logs should return a list containing the log entry
        db.session.refresh(user)
        assert len(user.audit_logs) == 1
        assert user.audit_logs[0].log_id == audit_log.log_id

    def test_user_multiple_audit_logs(self, app, user, valid_data):
        # A user can accumulate many audit log entries over time
        AuditLog(**valid_data).save()
        AuditLog(**{**valid_data, "action_type": "UPDATE"}).save()
        AuditLog(**{**valid_data, "action_type": "DELETE"}).save()

        db.session.refresh(user)
        assert len(user.audit_logs) == 3

    def test_audit_log_user_full_name_accessible(self, app, audit_log, user):
        # Confirms traversal through relationship to read user fields
        # This is the pattern used in audit log display routes
        db.session.refresh(audit_log)
        assert audit_log.user.full_name == user.full_name

    def test_audit_log_user_role_accessible(self, app, audit_log, user):
        # Role is displayed alongside actions in audit log reports
        db.session.refresh(audit_log)
        assert audit_log.user.role == user.role

    def test_user_with_no_logs_returns_empty_list(self, app, user):
        # A user who has not performed any logged actions returns empty list
        db.session.refresh(user)
        assert user.audit_logs == []

    def test_different_users_logs_are_isolated(self, app, user,
                                                cashier_user, valid_data):
        # Each user's audit_logs only contains their own entries
        AuditLog(**valid_data).save()  # logged by `user`
        AuditLog(**{**valid_data,
                    "user_id": cashier_user.user_id}).save()  # logged by cashier

        db.session.refresh(user)
        db.session.refresh(cashier_user)

        assert len(user.audit_logs) == 1
        assert len(cashier_user.audit_logs) == 1


# ---------------------------------------------------------------------------
# 8. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with AuditLog's specific schema.
#    WHY:  BaseModel is abstract and tested in isolation via DummyModel.
#          These checks confirm AuditLog's server_default datetime,
#          dual Enum columns, and nullable reference fields don't break
#          anything inherited from BaseModel.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_audit_log(self, app, valid_data):
        # save() should commit the AuditLog row to the DB
        AuditLog(**valid_data).save()
        assert AuditLog.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        log = AuditLog(**valid_data)
        returned = log.save()
        assert returned is log

    def test_delete_removes_audit_log(self, app, audit_log):
        # delete() should remove the AuditLog row from the DB
        audit_log.delete()
        assert AuditLog.query.count() == 0

    def test_delete_does_not_remove_user(self, app, audit_log, user):
        # Deleting an AuditLog should NOT cascade to the referenced User
        audit_log.delete()
        assert User.query.count() == 1

    def test_get_by_id_returns_correct_record(self, app, audit_log):
        # get_by_id() should return the AuditLog with the matching PK
        result = AuditLog.get_by_id(audit_log.log_id)

        assert result is not None
        assert result.log_id == audit_log.log_id
        assert result.action_type == audit_log.action_type
        assert result.module == audit_log.module

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent log_id should return None, not raise
        result = AuditLog.get_by_id(99999)
        assert result is None

    def test_get_all_returns_all_logs(self, app, valid_data):
        # get_all() returns every row in the Audit_Log table
        AuditLog(**valid_data).save()
        AuditLog(**{**valid_data}).save()

        result = AuditLog.get_all()
        assert len(result) == 2

    def test_get_all_can_be_filtered_by_action_type(self, app, user, valid_data):
        # Confirms get_all() results can be filtered in Python —
        # common pattern in audit log route queries
        AuditLog(**{**valid_data, "action_type": "INSERT"}).save()
        AuditLog(**{**valid_data, "action_type": "UPDATE"}).save()
        AuditLog(**{**valid_data, "action_type": "LOGIN"}).save()

        all_logs = AuditLog.get_all()
        insert_logs = [l for l in all_logs if l.action_type == "INSERT"]
        login_logs = [l for l in all_logs if l.action_type == "LOGIN"]

        assert len(insert_logs) == 1
        assert len(login_logs) == 1

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = AuditLog.get_all()
        assert result == []