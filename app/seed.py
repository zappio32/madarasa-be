import argparse
import getpass

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Admin, InstitutionSettings, Page
from app.security import hash_password


def seed_admin(email: str, password: str) -> None:
    if len(password) < 12:
        raise ValueError("Initial administrator password must contain at least 12 characters.")
    with SessionLocal() as db:
        existing = db.scalar(select(Admin).where(Admin.email == email.lower()))
        if existing:
            raise ValueError(f"An administrator with {email} already exists; refusing to replace credentials.")
        db.add(Admin(email=email.lower(), password_hash=hash_password(password), must_change_password=True))
        db.commit()


def seed_content() -> None:
    with SessionLocal() as db:
        if not db.scalar(select(InstitutionSettings).limit(1)):
            db.add(InstitutionSettings())
        initial_pages = [
            ("about", "About Us", "हमारे बारे में"),
            ("academics", "Academics", "शिक्षा"),
            ("management", "Our Management", "हमारा प्रबंधन"),
            ("teachers", "Our Teachers", "हमारे शिक्षक"),
            ("gallery", "Gallery", "गैलरी"),
            ("news", "News & Events", "समाचार और कार्यक्रम"),
        ]
        existing = {slug for (slug,) in db.execute(select(Page.slug)).all()}
        for slug, title_en, title_hi in initial_pages:
            if slug not in existing:
                db.add(Page(slug=slug, title_en=title_en, title_hi=title_hi, is_published=True))
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize bilingual content and create the first administrator.")
    parser.add_argument("--content-only", action="store_true", help="Seed institution settings and public pages only.")
    args = parser.parse_args()
    seed_content()
    if not args.content_only:
        config = get_settings()
        email = config.initial_admin_email
        password = config.initial_admin_password or getpass.getpass(f"Choose a password for {email} (12+ characters): ")
        seed_admin(email, password)
        print(f"Administrator {email} created; the first sign-in requires a password change.")


if __name__ == "__main__":
    main()

