"""
tests/recovery_detail_test.py

Pytest suite for RecoveryDetail model.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. Column Constraints
   - user_id is the primary key AND a FK — one recovery row per user
   - email is required (NOT NULL)
   - phone_number is nullable — optional contact field
   - reset_token is nullable — only set during an active reset flow
   - token_expiry is nullable — only set alongside reset_token

2. Foreign Key Constraints
   - user_id must reference an existing User row
   - Invalid user_id is blocked

3. Unique Constraint (PK behavior)
   - user_id is the PK — only one RecoveryDetail row per user
   - A second row for the same user violates the PK constraint

4. Token Flow Behavior
   - reset_token can be set and cleared (active → expired reset flow)
   - token_expiry can be set and cleared alongside reset_token
   - Both token fields can coexist or be independently None
   - Simulates the full reset token lifecycle:
     no token → token set → token cleared after use

5. Update Behavior
   - email, phone_number, reset_token, token_expiry can all be updated
   - phone_number can be set to None (cleared)
   - reset_token can be set to None (token consumed or expired)

6. Relationship — User ↔ RecoveryDetail (uselist=False)
   - recovery_detail.user returns the linked User instance
   - user.recovery_detail returns single RecoveryDetail (not a list)
   - user with no recovery detail returns None

7. Delete Behavior
   - Deleting a RecoveryDetail does NOT delete the User
   - After deletion, user.recovery_detail returns None

8. Inherited BaseModel methods (save, delete, get_by_id, get_all)
   - Confirmed working with RecoveryDetail's user_id-as-PK schema
   - get_by_id() uses user_id (integer PK) — verified correct

─────────────────────────────────────────────────────────────────────────────
All base fixtures come from tests/conftest.py.
"""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models.recovery_detail import RecoveryDetail
from app.models.user import User


# ---------------------------------------------------------------------------
# Local helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data(user):
    """
    Returns a dict of all valid fields for a RecoveryDetail.
    reset_token and token_expiry are included but nullable —
    tested in all combinations below.
    """
    return dict(
        user_id=user.user_id,
        email="test@example.com",
        phone_number="09171234567",
        reset_token=None,
        token_expiry=None,
    )


# ---------------------------------------------------------------------------
# 1. Column Constraints
#
#    WHAT: Verifies that nullable=False columns are enforced and that
#          nullable columns accept None in all valid combinations.
#    WHY:  RecoveryDetail is the account recovery anchor for each user.
#          A missing email means the user cannot receive a reset link.
#          The token fields being nullable is intentional — they are only
#          populated during an active password reset flow, not permanently.
# ---------------------------------------------------------------------------

class TestColumnConstraints:
    def test_valid_recovery_detail_saves_successfully(self, app, valid_data):
        # Happy path — all required fields present, should commit cleanly
        RecoveryDetail(**valid_data).save()
        assert RecoveryDetail.query.count() == 1

    def test_user_id_is_required(self, app, valid_data):
        # user_id is both PK and FK — omitting raises an error
        valid_data.pop("user_id")
        with pytest.raises(Exception):
            RecoveryDetail(**valid_data).save()

    def test_email_is_required(self, app, valid_data):
        # email is NOT NULL — a recovery row without email is useless
        valid_data.pop("email")
        with pytest.raises(Exception):
            RecoveryDetail(**valid_data).save()

    def test_phone_number_is_optional(self, app, valid_data):
        # phone_number is nullable — not all users provide a phone number
        valid_data.pop("phone_number")
        RecoveryDetail(**valid_data).save()

        result = RecoveryDetail.query.first()
        assert result.phone_number is None

    def test_reset_token_is_optional(self, app, valid_data):
        # reset_token is nullable — only set during an active reset flow
        valid_data.pop("reset_token")
        RecoveryDetail(**valid_data).save()

        result = RecoveryDetail.query.first()
        assert result.reset_token is None

    def test_token_expiry_is_optional(self, app, valid_data):
        # token_expiry is nullable — only set alongside reset_token
        valid_data.pop("token_expiry")
        RecoveryDetail(**valid_data).save()

        result = RecoveryDetail.query.first()
        assert result.token_expiry is None

    def test_all_nullable_fields_can_be_none(self, app, user):
        # Minimum valid row: user_id + email only, everything else None
        rd = RecoveryDetail(
            user_id=user.user_id,
            email="minimal@example.com",
        )
        rd.save()

        result = RecoveryDetail.query.first()
        assert result.phone_number is None
        assert result.reset_token is None
        assert result.token_expiry is None

    def test_email_max_length(self, app, valid_data):
        # email is db.String(100) — accepts up to 100 characters
        valid_data["email"] = "a" * 90 + "@test.com"
        RecoveryDetail(**valid_data).save()

        result = RecoveryDetail.query.first()
        assert len(result.email) <= 100

    def test_phone_number_max_length(self, app, valid_data):
        # phone_number is db.String(20) — accepts up to 20 characters
        valid_data["phone_number"] = "0" * 20
        RecoveryDetail(**valid_data).save()

        result = RecoveryDetail.query.first()
        assert len(result.phone_number) == 20

    def test_reset_token_max_length(self, app, valid_data):
        # reset_token is db.String(255) — accepts long token strings
        valid_data["reset_token"] = "t" * 255
        RecoveryDetail(**valid_data).save()

        result = RecoveryDetail.query.first()
        assert len(result.reset_token) == 255


# ---------------------------------------------------------------------------
# 2. Foreign Key Constraints
#
#    WHAT: Verifies that user_id must reference a real User row.
#    WHY:  RecoveryDetail is meaningless without a real user. An orphan
#          recovery row with an invalid user_id would cause any reset
#          flow that looks up the user via this table to crash or return
#          None silently — a security-critical failure.
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    def test_invalid_user_id_raises(self, app, valid_data):
        # Nonexistent user_id should be blocked by FK constraint
        valid_data["user_id"] = 99999999
        with pytest.raises(Exception):
            RecoveryDetail(**valid_data).save()

    def test_valid_user_id_saves(self, app, valid_data):
        # Confirm FK with a real user_id saves cleanly
        RecoveryDetail(**valid_data).save()
        assert RecoveryDetail.query.count() == 1

    def test_recovery_detail_blocked_after_user_deleted(self, app, valid_data, user):
        # After the referenced user is deleted, a new RecoveryDetail
        # with that user_id should be blocked by FK constraint
        user.delete()
        with pytest.raises(Exception):
            RecoveryDetail(**valid_data).save()


# ---------------------------------------------------------------------------
# 3. Unique Constraint (PK behavior)
#
#    WHAT: Verifies that user_id as PK enforces one row per user.
#    WHY:  user.recovery_detail is uselist=False — it expects exactly one
#          RecoveryDetail per user. A second row for the same user would
#          cause the relationship to behave unpredictably and break the
#          reset token flow which assumes a single canonical row per user.
# ---------------------------------------------------------------------------

class TestUniqueConstraint:
    def test_duplicate_user_id_raises(self, app, valid_data):
        # First RecoveryDetail saves fine
        RecoveryDetail(**valid_data).save()

        # Second row for the same user violates the PK constraint
        with pytest.raises(Exception):
            RecoveryDetail(**{**valid_data,
                              "email": "other@example.com"}).save()

    def test_different_users_can_each_have_recovery_detail(self, app,
                                                            user, cashier_user):
        # Each user can have their own RecoveryDetail — uniqueness is per user
        RecoveryDetail(
            user_id=user.user_id,
            email="admin@example.com",
        ).save()
        RecoveryDetail(
            user_id=cashier_user.user_id,
            email="cashier@example.com",
        ).save()

        assert RecoveryDetail.query.count() == 2


# ---------------------------------------------------------------------------
# 4. Token Flow Behavior
#
#    WHAT: Verifies the full lifecycle of the reset_token and token_expiry
#          fields — from no token, to token set, to token consumed/cleared.
#    WHY:  These two fields drive the password reset flow. If setting or
#          clearing them silently fails, users will either be unable to
#          reset their password (token not saved) or have a permanently
#          active reset token (token not cleared after use) — a security
#          vulnerability.
# ---------------------------------------------------------------------------

class TestTokenFlowBehavior:
    def test_set_reset_token(self, app, recovery_detail):
        # Simulates initiating a password reset — token is generated and saved
        token = "secure-random-token-abc123"
        expiry = datetime.utcnow() + timedelta(hours=1)

        recovery_detail.reset_token = token
        recovery_detail.token_expiry = expiry
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.reset_token == token
        assert result.token_expiry is not None

    def test_clear_reset_token_after_use(self, app, recovery_detail):
        # Simulates consuming a reset token — cleared after successful reset
        recovery_detail.reset_token = "used-token"
        recovery_detail.token_expiry = datetime.utcnow() + timedelta(hours=1)
        recovery_detail.save()

        # Token consumed — clear both fields
        recovery_detail.reset_token = None
        recovery_detail.token_expiry = None
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.reset_token is None
        assert result.token_expiry is None

    def test_token_expiry_stores_datetime(self, app, recovery_detail):
        # token_expiry is db.DateTime — must be stored and retrieved
        # as a datetime object, not a string
        expiry = datetime.utcnow() + timedelta(hours=24)
        recovery_detail.token_expiry = expiry
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert isinstance(result.token_expiry, datetime)

    def test_token_expiry_future_datetime_accepted(self, app, recovery_detail):
        # A future expiry time is the normal case for a fresh reset token
        future = datetime.utcnow() + timedelta(hours=1)
        recovery_detail.token_expiry = future
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.token_expiry > datetime.utcnow()

    def test_token_expiry_past_datetime_accepted(self, app, recovery_detail):
        # A past expiry is valid at the DB level — expiry checking is
        # done in application logic, not enforced by the schema
        past = datetime.utcnow() - timedelta(hours=1)
        recovery_detail.token_expiry = past
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.token_expiry < datetime.utcnow()

    def test_reset_token_without_expiry_is_accepted(self, app, recovery_detail):
        # token can be set without expiry — DB does not enforce pairing
        # Application logic is responsible for requiring both
        recovery_detail.reset_token = "token-without-expiry"
        recovery_detail.token_expiry = None
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.reset_token == "token-without-expiry"
        assert result.token_expiry is None

    def test_replace_existing_token_with_new_one(self, app, recovery_detail):
        # A second reset request replaces the old token with a new one
        recovery_detail.reset_token = "first-token"
        recovery_detail.token_expiry = datetime.utcnow() + timedelta(hours=1)
        recovery_detail.save()

        recovery_detail.reset_token = "second-token"
        recovery_detail.token_expiry = datetime.utcnow() + timedelta(hours=2)
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.reset_token == "second-token"


# ---------------------------------------------------------------------------
# 5. Update Behavior
#
#    WHAT: Verifies that all mutable fields can be updated and persisted.
#    WHY:  email and phone_number can change if a user updates their
#          recovery contact info. reset_token and token_expiry change
#          every time a password reset is initiated or completed.
#          Silent update failures would break the entire recovery flow.
# ---------------------------------------------------------------------------

class TestUpdateBehavior:
    def test_update_email(self, app, recovery_detail):
        # User updates their recovery email address
        recovery_detail.email = "newemail@example.com"
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.email == "newemail@example.com"

    def test_update_phone_number(self, app, recovery_detail):
        # User updates their recovery phone number
        recovery_detail.phone_number = "09189876543"
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.phone_number == "09189876543"

    def test_clear_phone_number_to_none(self, app, recovery_detail):
        # User removes their phone number — it is nullable so None is valid
        recovery_detail.phone_number = None
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.phone_number is None

    def test_update_preserves_other_fields(self, app, recovery_detail):
        # Updating one field should not accidentally wipe other fields
        original_email = recovery_detail.email
        recovery_detail.phone_number = "09111111111"
        recovery_detail.save()

        result = RecoveryDetail.get_by_id(recovery_detail.user_id)
        assert result.email == original_email
        assert result.phone_number == "09111111111"


# ---------------------------------------------------------------------------
# 6. Relationship — User ↔ RecoveryDetail (uselist=False)
#
#    WHAT: Verifies both sides of the bidirectional relationship and that
#          uselist=False returns a single object, not a list.
#    WHY:  user.recovery_detail is used in the password reset flow to
#          look up the user's token and email. recovery_detail.user is
#          used to retrieve the full user object from a token lookup.
#          A broken relationship would silently prevent password resets
#          from working at all — without raising an obvious error.
# ---------------------------------------------------------------------------

class TestRelationship:
    def test_recovery_detail_user_returns_linked_user(self, app,
                                                       recovery_detail, user):
        # recovery_detail.user should return the linked User instance
        db.session.refresh(recovery_detail)
        assert recovery_detail.user is not None
        assert recovery_detail.user.user_id == user.user_id

    def test_user_recovery_detail_returns_single_object(self, app,
                                                         recovery_detail, user):
        # uselist=False — must be a single object, not a list
        db.session.refresh(user)
        assert not isinstance(user.recovery_detail, list)
        assert user.recovery_detail is not None

    def test_user_recovery_detail_returns_correct_row(self, app,
                                                       recovery_detail, user):
        # user.recovery_detail should return the correct RecoveryDetail
        db.session.refresh(user)
        assert user.recovery_detail.user_id == recovery_detail.user_id
        assert user.recovery_detail.email == recovery_detail.email

    def test_user_with_no_recovery_detail_returns_none(self, app, user):
        # A user with no RecoveryDetail row — relationship returns None
        db.session.refresh(user)
        assert user.recovery_detail is None

    def test_recovery_detail_user_name_accessible(self, app,
                                                   recovery_detail, user):
        # Confirms traversal through the relationship to read user fields
        # Used in reset flows that need to display the user's name
        db.session.refresh(recovery_detail)
        assert recovery_detail.user.full_name == user.full_name

    def test_different_users_have_independent_recovery_details(self,
                                                                app, user,
                                                                cashier_user):
        # Each user's recovery_detail is independent and correctly scoped
        RecoveryDetail(user_id=user.user_id,
                       email="admin@example.com").save()
        RecoveryDetail(user_id=cashier_user.user_id,
                       email="cashier@example.com").save()

        db.session.refresh(user)
        db.session.refresh(cashier_user)

        assert user.recovery_detail.email == "admin@example.com"
        assert cashier_user.recovery_detail.email == "cashier@example.com"


# ---------------------------------------------------------------------------
# 7. Delete Behavior
#
#    WHAT: Verifies what happens when a RecoveryDetail is deleted and
#          confirms the correct impact on the User relationship.
#    WHY:  Deleting a RecoveryDetail should never affect the User —
#          the dependency is one-way. After deletion, user.recovery_detail
#          should return None cleanly, not crash.
# ---------------------------------------------------------------------------

class TestDeleteBehavior:
    def test_deleting_recovery_detail_does_not_delete_user(self, app,
                                                            recovery_detail,
                                                            user):
        # Deleting the recovery row should leave the User intact
        recovery_detail.delete()

        assert User.query.count() == 1
        assert RecoveryDetail.query.count() == 0

    def test_after_deletion_user_recovery_detail_is_none(self, app,
                                                          recovery_detail,
                                                          user):
        # After its recovery row is deleted, user.recovery_detail is None
        recovery_detail.delete()

        db.session.refresh(user)
        assert user.recovery_detail is None

    def test_after_deletion_new_recovery_detail_can_be_created(self, app,
                                                                recovery_detail,
                                                                user):
        # After deletion, a new RecoveryDetail can be created for the same user
        # (PK slot is freed after deletion)
        recovery_detail.delete()

        new_rd = RecoveryDetail(
            user_id=user.user_id,
            email="new@example.com",
        )
        new_rd.save()

        assert RecoveryDetail.query.count() == 1
        db.session.refresh(user)
        assert user.recovery_detail.email == "new@example.com"


# ---------------------------------------------------------------------------
# 8. Inherited BaseModel methods
#
#    WHAT: Spot-checks save(), delete(), get_by_id(), get_all() work
#          correctly with RecoveryDetail's user_id-as-PK schema.
#    WHY:  BaseModel's get_by_id() uses the PK to look up records.
#          RecoveryDetail uses user_id as its PK (not a separate
#          autoincrement id) — this confirms get_by_id(user_id) works
#          correctly with a non-autoincrement integer PK.
# ---------------------------------------------------------------------------

class TestInheritedBaseModelMethods:
    def test_save_persists_recovery_detail(self, app, valid_data):
        # save() should commit the RecoveryDetail row to the DB
        RecoveryDetail(**valid_data).save()
        assert RecoveryDetail.query.count() == 1

    def test_save_returns_self(self, app, valid_data):
        # save() returns the instance — allows method chaining
        rd = RecoveryDetail(**valid_data)
        returned = rd.save()
        assert returned is rd

    def test_delete_removes_recovery_detail(self, app, recovery_detail):
        # delete() should remove the RecoveryDetail row from the DB
        recovery_detail.delete()
        assert RecoveryDetail.query.count() == 0

    def test_get_by_id_uses_user_id_as_pk(self, app, recovery_detail, user):
        # get_by_id() must work with user_id as the PK —
        # not a separate autoincrement id column
        result = RecoveryDetail.get_by_id(user.user_id)

        assert result is not None
        assert result.user_id == user.user_id
        assert result.email == recovery_detail.email

    def test_get_by_id_returns_none_for_missing(self, app):
        # Nonexistent user_id should return None, not raise
        result = RecoveryDetail.get_by_id(99999999)
        assert result is None

    def test_get_all_returns_all_recovery_details(self, app, user, cashier_user):
        # get_all() returns every row in the Recovery_Details table
        RecoveryDetail(user_id=user.user_id,
                       email="a@example.com").save()
        RecoveryDetail(user_id=cashier_user.user_id,
                       email="b@example.com").save()

        result = RecoveryDetail.get_all()
        assert len(result) == 2

    def test_get_all_empty_returns_empty_list(self, app):
        # Empty table should return [] not None
        result = RecoveryDetail.get_all()
        assert result == []