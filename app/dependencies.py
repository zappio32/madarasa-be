from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.security import decode_access_token


def require_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    token = request.cookies.get("access_token")
    admin_id = decode_access_token(token) if token else None
    admin = db.get(Admin, admin_id) if admin_id is not None else None
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if admin.must_change_password and request.url.path not in {
        "/api/auth/me",
        "/api/auth/change-password",
        "/api/auth/logout",
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Change the initial password before continuing.")
    return admin


def require_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or not secrets_compare(cookie, header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token is missing or invalid.")


def secrets_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
