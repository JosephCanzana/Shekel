#!/usr/bin/env python3
"""
hash_cli.py — A CLI tool for generating and checking Werkzeug password hashes.

Usage:
  python hash_cli.py generate <password> [--method METHOD] [--salt-length N]
  python hash_cli.py check <password> <hash>
  python hash_cli.py batch-generate <password1> <password2> ... [--method METHOD]
  python hash_cli.py methods
"""

import argparse
import sys
from werkzeug.security import check_password_hash, generate_password_hash

# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args   = parser.parse_args()
    args.func(args)

# ─── ANSI colours ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

SUPPORTED_METHODS = ["pbkdf2:sha256", "pbkdf2:sha512", "scrypt"]

# ─── Handlers ────────────────────────────────────────────────────────────────

def cmd_generate(args):
    method      = args.method
    salt_length = args.salt_length

    hashed = generate_password_hash(
        args.password,
        method=method,
        salt_length=salt_length,
    )

    print(f"\n{BOLD}Password  :{RESET} {args.password}")
    print(f"{BOLD}Method    :{RESET} {method}")
    print(f"{BOLD}Salt len  :{RESET} {salt_length}")
    print(f"{BOLD}Hash      :{RESET} {CYAN}{hashed}{RESET}\n")


def cmd_check(args):
    ok = check_password_hash(args.hash, args.password)

    if ok:
        print(f"\n{GREEN}{BOLD}✔  Match!{RESET}  The password matches the hash.\n")
    else:
        print(f"\n{RED}{BOLD}✘  No match.{RESET}  The password does NOT match the hash.\n")

    sys.exit(0 if ok else 1)


def cmd_batch_generate(args):
    method      = args.method
    salt_length = args.salt_length

    print()
    for pw in args.passwords:
        hashed = generate_password_hash(pw, method=method, salt_length=salt_length)
        print(f"{BOLD}{pw!r:<30}{RESET} → {CYAN}{hashed}{RESET}")
    print()


def cmd_methods(_args):
    print(f"\n{BOLD}Supported hashing methods:{RESET}")
    for m in SUPPORTED_METHODS:
        print(f"  {YELLOW}•{RESET} {m}")
    print(f"\n{BOLD}Default:{RESET} pbkdf2:sha256\n")


# ─── CLI definition ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hash_cli",
        description="Generate and verify Werkzeug password hashes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hash_cli.py generate mysecret
  python hash_cli.py generate mysecret --method scrypt --salt-length 16
  python hash_cli.py check mysecret pbkdf2:sha256$...
  python hash_cli.py batch-generate pass1 pass2 pass3
  python hash_cli.py methods
""",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── generate ──────────────────────────────────────────────────────────────
    gen = sub.add_parser("generate", aliases=["gen", "g"],
                         help="Hash a single password")
    gen.add_argument("password", help="Plain-text password to hash")
    gen.add_argument(
        "--method", "-m",
        default="pbkdf2:sha256",
        choices=SUPPORTED_METHODS,
        help="Hashing algorithm (default: pbkdf2:sha256)",
    )
    gen.add_argument(
        "--salt-length", "-s",
        type=int,
        default=16,
        metavar="N",
        help="Salt length in bytes (default: 16)",
    )
    gen.set_defaults(func=cmd_generate)

    # ── check ─────────────────────────────────────────────────────────────────
    chk = sub.add_parser("check", aliases=["verify", "v"],
                          help="Verify a password against a hash")
    chk.add_argument("password", help="Plain-text password to test")
    chk.add_argument("hash",     help="Werkzeug hash string to verify against")
    chk.set_defaults(func=cmd_check)

    # ── batch-generate ────────────────────────────────────────────────────────
    batch = sub.add_parser("batch-generate", aliases=["batch", "b"],
                            help="Hash multiple passwords at once")
    batch.add_argument("passwords", nargs="+", help="One or more passwords")
    batch.add_argument(
        "--method", "-m",
        default="pbkdf2:sha256",
        choices=SUPPORTED_METHODS,
        help="Hashing algorithm (default: pbkdf2:sha256)",
    )
    batch.add_argument(
        "--salt-length", "-s",
        type=int,
        default=16,
        metavar="N",
        help="Salt length in bytes (default: 16)",
    )
    batch.set_defaults(func=cmd_batch_generate)

    # ── methods ───────────────────────────────────────────────────────────────
    mth = sub.add_parser("methods", help="List available hashing methods")
    mth.set_defaults(func=cmd_methods)

    return parser


if __name__ == "__main__":
    main()