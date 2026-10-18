"""Create the first administrator (and, outside production, a demo operator).

Registration always creates an `operator`, so an admin has to be created
out of band. Idempotent: existing users are kept; pass --reset-password to
change an existing admin's password.

    ADMIN_PASSWORD='a-long-random-password' make seed
"""

import argparse
import os
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.infrastructure.database.session import SessionLocal
from app.models import User

MIN_PASSWORD_LENGTH = 12
DEV_ADMIN_PASSWORD = "admin-change-me-now"
DEV_OPERATOR_PASSWORD = "operator-change-me-now"


def ensure_user(db, username, email, password, role, reset_password):
    user = db.scalar(select(User).where(User.username == username))

    if user is None:
        db.add(
            User(
                username=username,
                email=email.lower(),
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
        )
        return f"created {role} '{username}'"

    user.role = role
    user.is_active = True

    if reset_password:
        user.password_hash = hash_password(password)
        return f"updated {role} '{username}' (password reset)"

    return f"kept existing {role} '{username}'"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()

    production = settings.ENVIRONMENT == "production"
    username = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
    email = os.environ.get("ADMIN_EMAIL", f"{username}@example.com")
    password = os.environ.get("ADMIN_PASSWORD")

    if not password:
        if production:
            print("ADMIN_PASSWORD is required in production", file=sys.stderr)
            return 1
        password = DEV_ADMIN_PASSWORD

    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters",
            file=sys.stderr,
        )
        return 1

    with SessionLocal.begin() as db:
        print(ensure_user(db, username, email, password, "admin", args.reset_password))

        if not production:
            print(
                ensure_user(
                    db, "operator", "operator@example.com",
                    DEV_OPERATOR_PASSWORD, "operator", False,
                )
            )

    if not production:
        print(
            f"Development logins: {username} / {password}, "
            f"operator / {DEV_OPERATOR_PASSWORD}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
