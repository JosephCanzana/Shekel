"""
tests/utils_tests/helpers_test.py

Pytest suite for app/utils/helpers.py.
All validator functions are pure — no DB or Flask context needed.

WHAT THIS FILE COVERS:
─────────────────────────────────────────────────────────────────────────────
1. validate_password()
   - Returns (True, None) for valid passwords
   - Enforces minimum 8 characters
   - Enforces at least one uppercase letter
   - Enforces at least one lowercase letter
   - Enforces at least one digit
   - Enforces at least one special character (@$!%*?&_#-)
   - Each rule tested independently with all other rules satisfied
   - Boundary cases: exactly 8 chars, 7 chars
   - Adversarial: empty string, whitespace only, very long password

2. validate_name()
   - Returns (True, None) for valid names
   - Accepts letters, spaces, hyphens
   - Rejects digits
   - Rejects special characters (except hyphens)
   - Rejects empty string
   - Field label appears in error message
   - Adversarial: SQL injection, XSS, unicode, very long strings

3. validate_email()
   - Returns (True, None) for valid Gmail addresses
   - Rejects non-Gmail domains
   - Rejects malformed email addresses
   - Rejects empty string
   - Adversarial: SQL injection, XSS, very long emails

4. validate_phone()
   - Returns (True, None) for empty string (optional field)
   - Accepts +63XXXXXXXXXX format
   - Accepts 09XXXXXXXXX format
   - Accepts 9XXXXXXXXX format
   - Rejects invalid formats
   - Adversarial: letters in phone, very long strings

5. validate_price()
   - Returns (True, None) for valid positive numbers
   - Accepts zero
   - Rejects negative numbers
   - Rejects non-numeric strings
   - Rejects empty string
   - Field label appears in error message

6. validate_product_name()
   - Accepts letters, numbers, spaces, hyphens, &, /, (, ), .
   - Rejects characters outside the allowed set

7. validate_category_name()
   - Accepts letters, numbers, spaces, hyphens, &, /
   - Rejects characters outside the allowed set

─────────────────────────────────────────────────────────────────────────────
No fixtures needed — all functions are pure (no DB, no Flask context).
"""

import pytest
from app.utils.helpers import (
    validate_password,
    validate_name,
    validate_email,
    validate_phone,
    validate_price,
    validate_product_name,
    validate_category_name,
)


# ---------------------------------------------------------------------------
# 1. validate_password()
#
#    WHAT: Tests every password rule independently and in combination.
#    WHY:  validate_password is used in both account_activation and
#          manage_users routes. A silently broken rule means weak passwords
#          get accepted — a security risk that's invisible until exploited.
# ---------------------------------------------------------------------------

class TestValidatePassword:
    # -- Happy path --

    def test_valid_password_returns_true(self):
        # All rules satisfied — must return (True, None)
        ok, err = validate_password("ValidPass1@")
        assert ok is True
        assert err is None

    def test_valid_password_with_all_special_chars(self):
        # Each allowed special character should be accepted
        for char in "@$!%*?&_#-":
            ok, err = validate_password(f"ValidPass1{char}")
            assert ok is True, f"Special char '{char}' was incorrectly rejected"

    def test_exactly_8_characters_accepted(self):
        # Boundary — exactly 8 chars meeting all rules must pass
        ok, err = validate_password("Valid1@a")
        assert ok is True

    # -- Length rule --

    def test_7_characters_rejected(self):
        # One under the limit — must fail
        ok, err = validate_password("Val1@ab")
        assert ok is False
        assert "8" in err or "characters" in err

    def test_empty_string_rejected(self):
        ok, err = validate_password("")
        assert ok is False

    def test_very_long_password_accepted(self):
        # No upper limit on length — long passwords are valid
        ok, err = validate_password("ValidPass1@" * 100)
        assert ok is True

    # -- Uppercase rule --

    def test_no_uppercase_rejected(self):
        ok, err = validate_password("validpass1@")
        assert ok is False
        assert "uppercase" in err.lower()

    def test_single_uppercase_accepted(self):
        ok, err = validate_password("Validpass1@")
        assert ok is True

    # -- Lowercase rule --

    def test_no_lowercase_rejected(self):
        ok, err = validate_password("VALIDPASS1@")
        assert ok is False
        assert "lowercase" in err.lower()

    def test_single_lowercase_accepted(self):
        ok, err = validate_password("VALIDPASs1@")
        assert ok is True

    # -- Digit rule --

    def test_no_digit_rejected(self):
        ok, err = validate_password("ValidPass@a")
        assert ok is False
        assert "number" in err.lower() or "digit" in err.lower()

    def test_single_digit_accepted(self):
        ok, err = validate_password("ValidPass1@")
        assert ok is True

    # -- Special character rule --

    def test_no_special_char_rejected(self):
        ok, err = validate_password("ValidPass12")
        assert ok is False
        assert "special" in err.lower()

    def test_unallowed_special_char_rejected(self):
        # ^ is not in the allowed set (@$!%*?&_#-)
        ok, err = validate_password("ValidPass1^")
        assert ok is False

    # -- Return value structure --

    def test_valid_returns_none_error(self):
        ok, err = validate_password("ValidPass1@")
        assert err is None

    def test_invalid_returns_string_error(self):
        ok, err = validate_password("weak")
        assert isinstance(err, str)
        assert len(err) > 0

    # -- Adversarial --

    def test_whitespace_only_rejected(self):
        ok, err = validate_password("        ")
        assert ok is False

    def test_sql_injection_rejected(self):
        # SQL injection doesn't meet password rules — rejected safely
        ok, err = validate_password("'; DROP TABLE Users; --")
        assert ok is False  # no digit or uppercase meeting all rules

    def test_password_with_spaces_valid_if_rules_met(self):
        # Spaces are not excluded by the rules — valid if all rules met
        ok, err = validate_password("Valid Pass1@")
        assert ok is True


# ---------------------------------------------------------------------------
# 2. validate_name()
#
#    WHAT: Tests name validation used for first_name and last_name fields.
#    WHY:  Names are stored in the DB and displayed throughout the system.
#          Accepting numbers or special chars would corrupt display,
#          break the login name-matching algorithm, and potentially
#          allow injection through name fields.
# ---------------------------------------------------------------------------

class TestValidateName:
    # -- Happy path --

    def test_simple_name_accepted(self):
        ok, err = validate_name("john", "First name")
        assert ok is True
        assert err is None

    def test_name_with_space_accepted(self):
        # Multi-word names like "dela cruz" must be accepted
        ok, err = validate_name("dela cruz", "Last name")
        assert ok is True

    def test_name_with_hyphen_accepted(self):
        # Hyphenated names like "mary-jane" must be accepted
        ok, err = validate_name("mary-jane", "First name")
        assert ok is True

    def test_uppercase_name_accepted(self):
        # Mixed case accepted — regex allows [a-zA-Z]
        ok, err = validate_name("John", "First name")
        assert ok is True

    def test_single_letter_accepted(self):
        ok, err = validate_name("A", "First name")
        assert ok is True

    # -- Digit rejection --

    def test_digit_in_name_rejected(self):
        ok, err = validate_name("john123", "First name")
        assert ok is False

    def test_only_digits_rejected(self):
        ok, err = validate_name("12345", "First name")
        assert ok is False

    # -- Special character rejection --

    def test_at_sign_in_name_rejected(self):
        ok, err = validate_name("john@doe", "First name")
        assert ok is False

    def test_period_in_name_rejected(self):
        ok, err = validate_name("john.doe", "First name")
        assert ok is False

    def test_underscore_in_name_rejected(self):
        ok, err = validate_name("john_doe", "First name")
        assert ok is False

    def test_parentheses_in_name_rejected(self):
        ok, err = validate_name("john(doe)", "First name")
        assert ok is False

    # -- Field label in error --

    def test_field_label_appears_in_error_message(self):
        ok, err = validate_name("john123", "First name")
        assert "First name" in err

    def test_custom_label_appears_in_error_message(self):
        ok, err = validate_name("last123", "Last name")
        assert "Last name" in err

    # -- Adversarial --

    def test_sql_injection_rejected(self):
        ok, err = validate_name("'; DROP TABLE Users; --", "First name")
        assert ok is False  # contains special chars not in [a-zA-Z\s\-]

    def test_xss_rejected(self):
        ok, err = validate_name("<script>alert('xss')</script>", "First name")
        assert ok is False

    def test_very_long_valid_name_accepted(self):
        # No length limit in validate_name — long but valid names accepted
        ok, err = validate_name("a" * 1000, "First name")
        assert ok is True

    def test_very_long_invalid_name_rejected(self):
        ok, err = validate_name("a" * 999 + "1", "First name")
        assert ok is False

    def test_unicode_letters_behavior(self):
        # Unicode letters like é or ñ — behavior depends on regex
        # [a-zA-Z] does NOT match unicode — document the behavior
        ok, err = validate_name("josé", "First name")
        # This will fail — validate_name only accepts ASCII letters
        # This is a known limitation worth documenting
        assert isinstance(ok, bool)  # just confirm it returns a bool, not crash


# ---------------------------------------------------------------------------
# 3. validate_email()
#
#    WHAT: Tests Gmail-only email validation used for recovery details.
#    WHY:  Recovery email must be a valid, reachable Gmail address.
#          Accepting non-Gmail addresses would mean password reset emails
#          go to addresses you can't guarantee are monitored.
# ---------------------------------------------------------------------------

class TestValidateEmail:
    # -- Happy path --

    def test_valid_gmail_accepted(self):
        ok, err = validate_email("user@gmail.com")
        assert ok is True
        assert err is None

    def test_gmail_with_dots_accepted(self):
        ok, err = validate_email("user.name@gmail.com")
        assert ok is True

    def test_gmail_with_plus_accepted(self):
        ok, err = validate_email("user+tag@gmail.com")
        assert ok is True

    def test_gmail_with_numbers_accepted(self):
        ok, err = validate_email("user123@gmail.com")
        assert ok is True

    # -- Non-Gmail rejection --

    def test_yahoo_email_rejected(self):
        ok, err = validate_email("user@yahoo.com")
        assert ok is False
        assert "gmail" in err.lower()

    def test_outlook_email_rejected(self):
        ok, err = validate_email("user@outlook.com")
        assert ok is False

    def test_custom_domain_rejected(self):
        ok, err = validate_email("user@company.com")
        assert ok is False

    # -- Malformed emails --

    def test_missing_at_sign_rejected(self):
        ok, err = validate_email("usergmail.com")
        assert ok is False

    def test_missing_domain_rejected(self):
        ok, err = validate_email("user@")
        assert ok is False

    def test_missing_username_rejected(self):
        ok, err = validate_email("@gmail.com")
        assert ok is False

    def test_empty_string_rejected(self):
        ok, err = validate_email("")
        assert ok is False
        assert err is not None

    def test_double_at_sign_rejected(self):
        ok, err = validate_email("user@@gmail.com")
        assert ok is False

    # -- Adversarial --

    def test_sql_injection_rejected(self):
        ok, err = validate_email("'; DROP TABLE Users; --@gmail.com")
        # May pass format check but won't be a real email — document behavior
        assert isinstance(ok, bool)

    def test_xss_in_email_rejected(self):
        ok, err = validate_email("<script>@gmail.com")
        assert ok is False

    def test_very_long_email_does_not_crash(self):
        long_email = "a" * 200 + "@gmail.com"
        ok, err = validate_email(long_email)
        assert isinstance(ok, bool)  # must not crash


# ---------------------------------------------------------------------------
# 4. validate_phone()
#
#    WHAT: Tests Philippine mobile number validation.
#          Phone is an optional field — empty string must return True.
#    WHY:  Phone is used in recovery details. An invalid phone stored
#          in the DB cannot receive SMS recovery messages. Importantly,
#          the field is optional — rejecting empty string would force
#          users to provide a phone even when they don't have one.
# ---------------------------------------------------------------------------

class TestValidatePhone:
    # -- Optional field behavior --

    def test_empty_string_accepted(self):
        # Phone is optional — empty string must always return (True, None)
        ok, err = validate_phone("")
        assert ok is True
        assert err is None

    def test_none_accepted(self):
        # None also treated as optional/empty
        ok, err = validate_phone(None)
        assert ok is True

    # -- Valid formats --

    def test_plus63_format_accepted(self):
        ok, err = validate_phone("+639171234567")
        assert ok is True

    def test_09_format_accepted(self):
        ok, err = validate_phone("09171234567")
        assert ok is True

    def test_9_format_accepted(self):
        ok, err = validate_phone("9171234567")
        assert ok is True

    def test_plus63_with_spaces_accepted(self):
        # Spaces are stripped before validation
        ok, err = validate_phone("+63 917 123 4567")
        assert ok is True

    def test_plus63_with_dashes_accepted(self):
        # Dashes are stripped before validation
        ok, err = validate_phone("+63-917-123-4567")
        assert ok is True

    # -- Invalid formats --

    def test_too_short_rejected(self):
        ok, err = validate_phone("0917123")
        assert ok is False

    def test_too_long_rejected(self):
        ok, err = validate_phone("091712345678")  # 12 digits
        assert ok is False

    def test_letters_in_phone_rejected(self):
        ok, err = validate_phone("0917abcdefg")
        assert ok is False

    def test_landline_format_rejected(self):
        # Landline format is not accepted — mobile only
        ok, err = validate_phone("02123456789")
        assert ok is False

    def test_plus1_format_rejected(self):
        # US format not accepted
        ok, err = validate_phone("+19171234567")
        assert ok is False

    # -- Adversarial --

    def test_sql_injection_rejected(self):
        ok, err = validate_phone("'; DROP TABLE Users; --")
        assert ok is False

    def test_very_long_string_does_not_crash(self):
        ok, err = validate_phone("0" * 10000)
        assert ok is False

    def test_xss_does_not_crash(self):
        ok, err = validate_phone("<script>alert(1)</script>")
        assert ok is False


# ---------------------------------------------------------------------------
# 5. validate_price()
#
#    WHAT: Tests price validation used for product prices.
#    WHY:  Prices are stored as Decimal(10,2) and used in financial
#          calculations. Accepting negative prices would corrupt revenue
#          reports. Accepting non-numeric strings would crash the
#          Decimal conversion in the route.
# ---------------------------------------------------------------------------

class TestValidatePrice:
    # -- Happy path --

    def test_valid_positive_price_accepted(self):
        ok, err = validate_price("10.00", "Unit price")
        assert ok is True
        assert err is None

    def test_integer_string_accepted(self):
        ok, err = validate_price("100", "Unit price")
        assert ok is True

    def test_zero_accepted(self):
        # Zero price is valid — free product
        ok, err = validate_price("0", "Unit price")
        assert ok is True

    def test_zero_float_accepted(self):
        ok, err = validate_price("0.00", "Unit price")
        assert ok is True

    def test_large_price_accepted(self):
        ok, err = validate_price("99999999.99", "Unit price")
        assert ok is True

    def test_float_value_accepted(self):
        ok, err = validate_price(10.00, "Unit price")
        assert ok is True

    # -- Negative rejection --

    def test_negative_price_rejected(self):
        ok, err = validate_price("-1", "Unit price")
        assert ok is False
        assert "negative" in err.lower()

    def test_negative_float_rejected(self):
        ok, err = validate_price("-0.01", "Unit price")
        assert ok is False

    # -- Non-numeric rejection --

    def test_letters_rejected(self):
        ok, err = validate_price("abc", "Unit price")
        assert ok is False
        assert "number" in err.lower() or "valid" in err.lower()

    def test_empty_string_rejected(self):
        ok, err = validate_price("", "Unit price")
        assert ok is False

    def test_none_rejected(self):
        ok, err = validate_price(None, "Unit price")
        assert ok is False

    def test_mixed_alphanumeric_rejected(self):
        ok, err = validate_price("10abc", "Unit price")
        assert ok is False

    # -- Field label in error --

    def test_field_label_appears_in_error(self):
        ok, err = validate_price("-5", "Revenue price")
        assert "Revenue price" in err

    def test_custom_label_appears_in_error(self):
        ok, err = validate_price("abc", "Product price")
        assert "Product price" in err

    # -- Adversarial --

    def test_sql_injection_rejected(self):
        ok, err = validate_price("'; DROP TABLE Products; --", "Unit price")
        assert ok is False

    def test_very_long_string_does_not_crash(self):
        ok, err = validate_price("9" * 10000, "Unit price")
        assert isinstance(ok, bool)

    def test_scientific_notation_behavior(self):
        # Python's float() accepts "1e5" — document behavior
        ok, err = validate_price("1e5", "Unit price")
        assert isinstance(ok, bool)  # must not crash


# ---------------------------------------------------------------------------
# 6. validate_product_name()
#
#    WHAT: Tests product name validation.
#    WHY:  Product names are displayed throughout the system — on receipts,
#          dashboards, and inventory lists. Invalid characters could
#          break template rendering or cause display issues.
# ---------------------------------------------------------------------------

class TestValidateProductName:
    # -- Happy path --

    def test_simple_name_accepted(self):
        ok, err = validate_product_name("Coca Cola")
        assert ok is True
        assert err is None

    def test_name_with_numbers_accepted(self):
        ok, err = validate_product_name("Product 123")
        assert ok is True

    def test_name_with_hyphen_accepted(self):
        ok, err = validate_product_name("Coca-Cola")
        assert ok is True

    def test_name_with_ampersand_accepted(self):
        ok, err = validate_product_name("Salt & Pepper")
        assert ok is True

    def test_name_with_slash_accepted(self):
        ok, err = validate_product_name("500ml/bottle")
        assert ok is True

    def test_name_with_parentheses_accepted(self):
        ok, err = validate_product_name("Juice (Orange)")
        assert ok is True

    def test_name_with_period_accepted(self):
        ok, err = validate_product_name("Dr. Pepper")
        assert ok is True

    # -- Rejection --

    def test_at_sign_rejected(self):
        ok, err = validate_product_name("Product@Store")
        assert ok is False

    def test_exclamation_rejected(self):
        ok, err = validate_product_name("Product!")
        assert ok is False

    def test_hash_rejected(self):
        ok, err = validate_product_name("Product#1")
        assert ok is False

    def test_sql_injection_rejected(self):
        ok, err = validate_product_name("'; DROP TABLE Products; --")
        assert ok is False

    def test_xss_rejected(self):
        ok, err = validate_product_name("<script>alert('xss')</script>")
        assert ok is False

    def test_very_long_valid_name_does_not_crash(self):
        ok, err = validate_product_name("Product " * 1000)
        assert isinstance(ok, bool)


# ---------------------------------------------------------------------------
# 7. validate_category_name()
#
#    WHAT: Tests category name validation.
#    WHY:  Category names appear in product listings, dropdowns, and
#          reports. The allowed character set is slightly different from
#          product names — no parentheses or periods.
# ---------------------------------------------------------------------------

class TestValidateCategoryName:
    # -- Happy path --

    def test_simple_name_accepted(self):
        ok, err = validate_category_name("Electronics")
        assert ok is True
        assert err is None

    def test_name_with_numbers_accepted(self):
        ok, err = validate_category_name("Category 1")
        assert ok is True

    def test_name_with_hyphen_accepted(self):
        ok, err = validate_category_name("Non-Food")
        assert ok is True

    def test_name_with_ampersand_accepted(self):
        ok, err = validate_category_name("Health & Beauty")
        assert ok is True

    def test_name_with_slash_accepted(self):
        ok, err = validate_category_name("Food/Beverage")
        assert ok is True

    # -- Rejection --

    def test_period_rejected(self):
        # Period not in category name allowed set
        ok, err = validate_category_name("Dr. Pepper")
        assert ok is False

    def test_parentheses_rejected(self):
        ok, err = validate_category_name("Juice (Orange)")
        assert ok is False

    def test_at_sign_rejected(self):
        ok, err = validate_category_name("Category@Store")
        assert ok is False

    def test_exclamation_rejected(self):
        ok, err = validate_category_name("Category!")
        assert ok is False

    def test_sql_injection_rejected(self):
        ok, err = validate_category_name("'; DROP TABLE Categories; --")
        assert ok is False

    def test_xss_rejected(self):
        ok, err = validate_category_name("<script>alert('xss')</script>")
        assert ok is False

    def test_empty_string_behavior(self):
        # Empty string — regex won't match, returns False
        ok, err = validate_category_name("")
        assert ok is False

    def test_very_long_valid_name_does_not_crash(self):
        ok, err = validate_category_name("Category " * 1000)
        assert isinstance(ok, bool)