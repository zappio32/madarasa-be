import argparse
import getpass

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Admin
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset an administrator password from a trusted server shell.")
    parser.add_argument("--email", required=True, help="Email address of the existing administrator.")
    args = parser.parse_args()
    password = getpass.getpass("New administrator password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.email == args.email.strip().lower()))
        if not admin:
            raise SystemExit("Administrator account was not found.")
        admin.password_hash = hash_password(password)
        admin.must_change_password = True
        db.commit()
    print("Administrator password reset. The account must change it at the next sign-in.")


if __name__ == "__main__":
    main()
