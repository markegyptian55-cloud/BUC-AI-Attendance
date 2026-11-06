"""Provision application users and seed the standard local accounts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
project_root = backend_dir.parent
for p in [str(project_root), str(backend_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app.db import engine, SessionLocal, Base
    from backend.app.models import User
    from backend.app.auth import hash_password, verify_password
except ModuleNotFoundError:
    from app.db import engine, SessionLocal, Base
    from app.models import User
    from app.auth import hash_password, verify_password

DEFAULT_USERS = (
    ("admin", "admin123", "System Administrator", "admin"),
    ("lecturer1", "teach123", "Dr. Ahmed Mansour", "lecturer"),
)


def create_user(db, username: str, password: str, full_name: str, role: str) -> bool:
    """Create one user, safely handling duplicate usernames from concurrent runs."""
    existing = db.query(User).filter(User.username == username).first()
    if existing is not None:
        print(f"User '{username}' already exists. Skipping or updating.")
        return False

    db.add(
        User(
            username=username,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
        )
    )
    try:
        db.commit()
        print(f"Created {role} user '{username}'.")
        return True
    except Exception:
        db.rollback()
        # The unique username constraint is the final authority if two seeders
        # check at once. Report the concurrent winner without hiding other DB errors.
        existing = db.query(User).filter(User.username == username).first()
        if existing is not None:
            print(f"User '{username}' already exists. Skipping or updating.")
            return False
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create users or seed default accounts.")
    parser.add_argument("--username", help="Username for a single user")
    parser.add_argument("--password", help="Plaintext password for a single user")
    parser.add_argument("--full-name", help="Display name for a single user")
    parser.add_argument("--role", choices=("admin", "lecturer"), help="User role")
    parser.add_argument(
        "--seed-defaults", action="store_true", help="Seed the standard admin and lecturer accounts"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.seed_defaults:
        missing = [
            option
            for option, value in (
                ("--username", args.username),
                ("--password", args.password),
                ("--full-name", args.full_name),
                ("--role", args.role),
            )
            if value is None
        ]
        if missing:
            parser.error("single user creation requires " + ", ".join(missing))

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.seed_defaults:
            users = DEFAULT_USERS
        else:
            users = ((args.username, args.password, args.full_name, args.role),)

        for username, password, full_name, role in users:
            create_user(db, username, password, full_name, role)
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Error creating user(s): {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
