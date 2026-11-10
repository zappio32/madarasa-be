from datetime import datetime, timezone
import secrets

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_admin, require_csrf
from app.models import (
    ActivityLog, Admin, Announcement, ContactMessage, GalleryCategory, GalleryImage,
    InstitutionSettings, MediaFile, Page, Post, Teacher,
)
from app.schemas import (
    AdminView, AnnouncementInput, ContactInput, GalleryCategoryInput, GalleryInput,
    LoginRequest, PageInput, PasswordChange, PostInput, ProfileUpdate, SettingsUpdate, TeacherInput,
)
from app.security import create_access_token, hash_password, verify_password
from app.storage import delete_image, read_image, store_image

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Madarasa Islamiya Faizee API", version="1.0.0", description="Independent bilingual institution website API.")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def log_action(db: Session, admin_id: int | None, action: str, entity: str = "", entity_id: int | None = None) -> None:
    db.add(ActivityLog(admin_id=admin_id, action=action, entity_type=entity, entity_id=entity_id))


def paginated(db: Session, model: type, page: int, page_size: int, *conditions):
    total = db.scalar(select(func.count()).select_from(model).where(*conditions)) if conditions else db.scalar(select(func.count()).select_from(model))
    query = select(model).where(*conditions) if conditions else select(model)
    items = db.scalars(query.order_by(model.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total or 0}


def save(db: Session, item):
    try:
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A record with the same unique value already exists.") from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=AdminView)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    admin = db.scalar(select(Admin).where(Admin.email == payload.email.lower()))
    if not admin or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    admin.last_login_at = datetime.now(timezone.utc)
    token = create_access_token(admin.id)
    csrf_token = secrets.token_urlsafe(32)
    secure = settings.environment == "production"
    same_site = "none" if secure else "lax"
    response.set_cookie("access_token", token, httponly=True, secure=secure, samesite=same_site, max_age=settings.jwt_access_token_minutes * 60, path="/")
    response.set_cookie("csrf_token", csrf_token, httponly=False, secure=secure, samesite=same_site, max_age=settings.jwt_access_token_minutes * 60, path="/")
    log_action(db, admin.id, "login", "admin", admin.id)
    db.commit()
    return admin


@app.post("/api/auth/logout", dependencies=[Depends(require_csrf)])
def logout(response: Response, admin: Admin = Depends(require_admin)):
    same_site = "none" if settings.environment == "production" else "lax"
    response.delete_cookie("access_token", path="/", httponly=True, secure=settings.environment == "production", samesite=same_site)
    response.delete_cookie("csrf_token", path="/", secure=settings.environment == "production", samesite=same_site)
    return {"message": "Logged out."}


@app.get("/api/auth/me", response_model=AdminView)
def me(admin: Admin = Depends(require_admin)):
    return admin


@app.post("/api/auth/refresh", dependencies=[Depends(require_csrf)])
def refresh_token(response: Response, admin: Admin = Depends(require_admin)):
    same_site = "none" if settings.environment == "production" else "lax"
    secure = settings.environment == "production"
    response.set_cookie("access_token", create_access_token(admin.id), httponly=True, secure=secure, samesite=same_site, max_age=settings.jwt_access_token_minutes * 60, path="/")
    response.set_cookie("csrf_token", secrets.token_urlsafe(32), httponly=False, secure=secure, samesite=same_site, max_age=settings.jwt_access_token_minutes * 60, path="/")
    return {"message": "Session refreshed."}


@app.post("/api/auth/change-password", dependencies=[Depends(require_csrf)])
def change_password(payload: PasswordChange, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if verify_password(payload.new_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Choose a new password different from your current password.")
    admin.password_hash = hash_password(payload.new_password)
    admin.must_change_password = False
    log_action(db, admin.id, "change_password", "admin", admin.id)
    db.commit()
    return {"message": "Password changed."}


@app.put("/api/auth/profile", dependencies=[Depends(require_csrf)])
def update_profile(payload: ProfileUpdate, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    normalized_email = str(payload.email).lower()
    duplicate = db.scalar(select(Admin).where(Admin.email == normalized_email, Admin.id != admin.id))
    if duplicate:
        raise HTTPException(status_code=409, detail="That email address is already in use.")
    admin.email = normalized_email
    log_action(db, admin.id, "update_profile", "admin", admin.id)
    db.commit()
    return {"id": admin.id, "email": admin.email}


@app.get("/api/admin/login-history")
def login_history(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return paginated(db, ActivityLog, page, page_size, ActivityLog.admin_id == admin.id, ActivityLog.action == "login")


@app.get("/api/public/settings")
def public_settings(db: Session = Depends(get_db)):
    item = db.scalar(select(InstitutionSettings).order_by(InstitutionSettings.id))
    if not item:
        raise HTTPException(status_code=404, detail="Website settings have not been initialized.")
    return item


@app.get("/api/public/home")
def public_home(db: Session = Depends(get_db)):
    return {
        "settings": db.scalar(select(InstitutionSettings).order_by(InstitutionSettings.id)),
        "posts": db.scalars(select(Post).where(Post.status == "published").order_by(Post.published_at.desc()).limit(3)).all(),
        "teachers": db.scalars(select(Teacher).where(Teacher.is_published.is_(True)).order_by(Teacher.display_order).limit(6)).all(),
        "gallery": db.scalars(select(GalleryImage).where(GalleryImage.is_published.is_(True)).order_by(GalleryImage.display_order).limit(6)).all(),
        "announcements": db.scalars(select(Announcement).where(Announcement.is_published.is_(True)).order_by(Announcement.published_at.desc()).limit(5)).all(),
    }


@app.get("/api/public/pages")
def public_pages(db: Session = Depends(get_db)):
    return db.scalars(select(Page).where(Page.is_published.is_(True)).order_by(Page.slug)).all()


@app.get("/api/public/pages/{slug}")
def public_page(slug: str, db: Session = Depends(get_db)):
    page = db.scalar(select(Page).where(Page.slug == slug, Page.is_published.is_(True)))
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    return page


@app.get("/api/public/posts")
def public_posts(page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100), search: str | None = None, db: Session = Depends(get_db)):
    conditions = [Post.status == "published"]
    if search:
        term = f"%{search[:100]}%"
        conditions.append(or_(Post.title_en.ilike(term), Post.title_hi.ilike(term), Post.body_en.ilike(term), Post.body_hi.ilike(term)))
    return paginated(db, Post, page, page_size, *conditions)


@app.get("/api/public/posts/{slug}")
def public_post(slug: str, db: Session = Depends(get_db)):
    item = db.scalar(select(Post).where(Post.slug == slug, Post.status == "published"))
    if not item:
        raise HTTPException(status_code=404, detail="Post not found.")
    return item


@app.get("/api/public/teachers")
def public_teachers(db: Session = Depends(get_db)):
    return db.scalars(select(Teacher).where(Teacher.is_published.is_(True)).order_by(Teacher.display_order)).all()


@app.get("/api/public/gallery")
def public_gallery(category: str | None = None, db: Session = Depends(get_db)):
    query = select(GalleryImage).where(GalleryImage.is_published.is_(True))
    if category:
        query = query.join(GalleryCategory).where(GalleryCategory.slug == category)
    return db.scalars(query.order_by(GalleryImage.display_order, GalleryImage.id.desc())).all()


@app.get("/api/public/announcements")
def public_announcements(db: Session = Depends(get_db)):
    return db.scalars(select(Announcement).where(Announcement.is_published.is_(True)).order_by(Announcement.published_at.desc())).all()


@app.post("/api/public/contact", status_code=201)
@limiter.limit("5/hour")
def contact(request: Request, payload: ContactInput, db: Session = Depends(get_db)):
    if payload.website:
        return {"message": "Thank you for your message."}
    item = ContactMessage(name=payload.name.strip(), email=payload.email.lower(), message=payload.message.strip())
    db.add(item)
    db.commit()
    return {"message": "Thank you for your message."}


@app.get("/api/admin/dashboard")
def dashboard(admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "published_posts": db.scalar(select(func.count()).select_from(Post).where(Post.status == "published")) or 0,
        "draft_posts": db.scalar(select(func.count()).select_from(Post).where(Post.status == "draft")) or 0,
        "teachers": db.scalar(select(func.count()).select_from(Teacher)) or 0,
        "gallery_images": db.scalar(select(func.count()).select_from(GalleryImage)) or 0,
        "recent_activity": db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(10)).all(),
    }


@app.get("/api/admin/activity-logs")
def activity_logs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return paginated(db, ActivityLog, page, page_size)


@app.get("/api/admin/settings")
def admin_settings(admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.scalar(select(InstitutionSettings).order_by(InstitutionSettings.id))
    if not item:
        item = save(db, InstitutionSettings())
    return item


@app.put("/api/admin/settings", dependencies=[Depends(require_csrf)])
def update_settings(payload: SettingsUpdate, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.scalar(select(InstitutionSettings).order_by(InstitutionSettings.id))
    if not item:
        item = InstitutionSettings()
    for key, value in payload.model_dump().items():
        setattr(item, key, str(value) if key == "map_url" and value else value)
    result = save(db, item)
    log_action(db, admin.id, "update_settings", "settings", result.id)
    db.commit()
    return result


@app.get("/api/admin/posts")
def admin_posts(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), search: str | None = None, status_filter: str | None = Query(None, alias="status"), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    conditions = []
    if status_filter in {"draft", "published"}:
        conditions.append(Post.status == status_filter)
    if search:
        conditions.append(or_(Post.title_en.ilike(f"%{search[:100]}%"), Post.title_hi.ilike(f"%{search[:100]}%")))
    return paginated(db, Post, page, page_size, *conditions)


@app.post("/api/admin/posts", status_code=201, dependencies=[Depends(require_csrf)])
def create_post(payload: PostInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data["featured_media_id"] and not db.get(MediaFile, data["featured_media_id"]):
        raise HTTPException(422, "Featured image was not found.")
    data.update(author_id=admin.id, published_at=datetime.now(timezone.utc) if payload.status == "published" else None)
    item = save(db, Post(**data))
    log_action(db, admin.id, "create", "post", item.id)
    db.commit()
    return item


@app.put("/api/admin/posts/{item_id}", dependencies=[Depends(require_csrf)])
def update_post(item_id: int, payload: PostInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Post, item_id)
    if not item:
        raise HTTPException(404, "Post not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    if item.status == "published" and item.published_at is None:
        item.published_at = datetime.now(timezone.utc)
    log_action(db, admin.id, "update", "post", item.id)
    return save(db, item)


@app.delete("/api/admin/posts/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_post(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Post, item_id)
    if not item:
        raise HTTPException(404, "Post not found.")
    log_action(db, admin.id, "delete", "post", item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/admin/teachers")
def admin_teachers(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return paginated(db, Teacher, page, page_size)


@app.post("/api/admin/teachers", status_code=201, dependencies=[Depends(require_csrf)])
def create_teacher(payload: TeacherInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = save(db, Teacher(**payload.model_dump()))
    log_action(db, admin.id, "create", "teacher", item.id)
    db.commit()
    return item


@app.put("/api/admin/teachers/{item_id}", dependencies=[Depends(require_csrf)])
def update_teacher(item_id: int, payload: TeacherInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Teacher, item_id)
    if not item:
        raise HTTPException(404, "Teacher not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    log_action(db, admin.id, "update", "teacher", item.id)
    return save(db, item)


@app.delete("/api/admin/teachers/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_teacher(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Teacher, item_id)
    if not item:
        raise HTTPException(404, "Teacher not found.")
    log_action(db, admin.id, "delete", "teacher", item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/admin/gallery")
def admin_gallery(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return paginated(db, GalleryImage, page, page_size)


@app.get("/api/public/gallery/categories")
def public_gallery_categories(db: Session = Depends(get_db)):
    return db.scalars(select(GalleryCategory).order_by(GalleryCategory.name_en)).all()


@app.get("/api/admin/gallery/categories")
def admin_gallery_categories(admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(GalleryCategory).order_by(GalleryCategory.name_en)).all()


@app.post("/api/admin/gallery/categories", status_code=201, dependencies=[Depends(require_csrf)])
def create_gallery_category(payload: GalleryCategoryInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = save(db, GalleryCategory(**payload.model_dump()))
    log_action(db, admin.id, "create", "gallery_category", item.id)
    db.commit()
    return item


@app.post("/api/admin/gallery", status_code=201, dependencies=[Depends(require_csrf)])
def create_gallery_image(payload: GalleryInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    if not db.get(MediaFile, payload.media_id):
        raise HTTPException(422, "Image was not found.")
    item = save(db, GalleryImage(**payload.model_dump()))
    log_action(db, admin.id, "create", "gallery_image", item.id)
    db.commit()
    return item


@app.put("/api/admin/gallery/{item_id}", dependencies=[Depends(require_csrf)])
def update_gallery_image(item_id: int, payload: GalleryInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(GalleryImage, item_id)
    if not item:
        raise HTTPException(404, "Gallery image not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    result = save(db, item)
    log_action(db, admin.id, "update", "gallery_image", result.id)
    db.commit()
    return result


@app.delete("/api/admin/gallery/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_gallery_image(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(GalleryImage, item_id)
    if not item:
        raise HTTPException(404, "Gallery image not found.")
    media_id = item.media_id
    log_action(db, admin.id, "delete", "gallery_image", item.id)
    db.delete(item)
    db.commit()
    media = db.get(MediaFile, media_id)
    if media:
        used_elsewhere = any(
            db.scalar(select(model.id).where(column == media.id).limit(1))
            for model, column in (
                (InstitutionSettings, InstitutionSettings.logo_media_id),
                (InstitutionSettings, InstitutionSettings.favicon_media_id),
                (Post, Post.featured_media_id),
                (Teacher, Teacher.photo_media_id),
                (GalleryImage, GalleryImage.media_id),
            )
        )
        if not used_elsewhere:
            db.delete(media)
            db.commit()
            delete_image(media.storage_key)
    return Response(status_code=204)


@app.put("/api/admin/gallery/categories/{item_id}", dependencies=[Depends(require_csrf)])
def update_gallery_category(item_id: int, payload: GalleryCategoryInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(GalleryCategory, item_id)
    if not item:
        raise HTTPException(404, "Gallery category not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    result = save(db, item)
    log_action(db, admin.id, "update", "gallery_category", result.id)
    db.commit()
    return result


@app.delete("/api/admin/gallery/categories/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_gallery_category(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(GalleryCategory, item_id)
    if not item:
        raise HTTPException(404, "Gallery category not found.")
    log_action(db, admin.id, "delete", "gallery_category", item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/admin/contact-messages")
def contact_messages(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return paginated(db, ContactMessage, page, page_size)


@app.patch("/api/admin/contact-messages/{item_id}", dependencies=[Depends(require_csrf)])
def mark_contact_message(item_id: int, is_read: bool = Query(True), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(ContactMessage, item_id)
    if not item:
        raise HTTPException(404, "Contact message not found.")
    item.is_read = is_read
    result = save(db, item)
    log_action(db, admin.id, "mark_contact_message", "contact_message", result.id)
    db.commit()
    return result


@app.delete("/api/admin/contact-messages/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_contact_message(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(ContactMessage, item_id)
    if not item:
        raise HTTPException(404, "Contact message not found.")
    log_action(db, admin.id, "delete", "contact_message", item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/admin/announcements")
def admin_announcements(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return paginated(db, Announcement, page, page_size)


@app.post("/api/admin/announcements", status_code=201, dependencies=[Depends(require_csrf)])
def create_announcement(payload: AnnouncementInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = Announcement(**payload.model_dump(), author_id=admin.id)
    if item.is_published:
        item.published_at = datetime.now(timezone.utc)
    result = save(db, item)
    log_action(db, admin.id, "create", "announcement", result.id)
    db.commit()
    return result


@app.put("/api/admin/announcements/{item_id}", dependencies=[Depends(require_csrf)])
def update_announcement(item_id: int, payload: AnnouncementInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Announcement, item_id)
    if not item:
        raise HTTPException(404, "Announcement not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    if item.is_published and item.published_at is None:
        item.published_at = datetime.now(timezone.utc)
    log_action(db, admin.id, "update", "announcement", item.id)
    return save(db, item)


@app.delete("/api/admin/announcements/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_announcement(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Announcement, item_id)
    if not item:
        raise HTTPException(404, "Announcement not found.")
    log_action(db, admin.id, "delete", "announcement", item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/admin/pages")
def admin_pages(admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(Page).order_by(Page.slug)).all()


@app.post("/api/admin/pages", status_code=201, dependencies=[Depends(require_csrf)])
def create_page(payload: PageInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = save(db, Page(**payload.model_dump()))
    log_action(db, admin.id, "create", "page", item.id)
    db.commit()
    return item


@app.put("/api/admin/pages/{item_id}", dependencies=[Depends(require_csrf)])
def update_page(item_id: int, payload: PageInput, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Page, item_id)
    if not item:
        raise HTTPException(404, "Page not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    result = save(db, item)
    log_action(db, admin.id, "update", "page", result.id)
    db.commit()
    return result


@app.delete("/api/admin/pages/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_page(item_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Page, item_id)
    if not item:
        raise HTTPException(404, "Page not found.")
    log_action(db, admin.id, "delete", "page", item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.post("/api/admin/media/upload", status_code=201, dependencies=[Depends(require_csrf)])
async def upload_media(file: UploadFile = File(...), admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    key, mime_type, content = await store_image(file)
    item = MediaFile(storage_key=key, mime_type=mime_type, file_size=len(content), original_name=(file.filename or "image")[:255])
    saved = save(db, item)
    log_action(db, admin.id, "upload", "media", saved.id)
    db.commit()
    return {"id": saved.id, "url": f"/api/admin/media/{saved.id}", "mime_type": mime_type, "file_size": len(content)}


def media_response(item: MediaFile, cache_control: str):
    try:
        content, mime_type = read_image(item.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Image not found.") from exc
    return StreamingResponse(
        iter([content]),
        media_type=mime_type,
        headers={"Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/admin/media/{media_id}")
def get_admin_media(media_id: int, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(MediaFile, media_id)
    if not item:
        raise HTTPException(404, "Image not found.")
    return media_response(item, "private, no-store")


@app.get("/api/public/media/{key}")
def get_public_media(key: str, db: Session = Depends(get_db)):
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(404, "Image not found.")
    item = db.get(MediaFile, int(key)) if key.isdecimal() else db.scalar(select(MediaFile).where(MediaFile.storage_key == key))
    if not item:
        raise HTTPException(404, "Image not found.")
    media_id = item.id
    publicly_referenced = any(
        db.scalar(select(model.id).where(*conditions).limit(1))
        for model, conditions in (
            (InstitutionSettings, (or_(InstitutionSettings.logo_media_id == media_id, InstitutionSettings.favicon_media_id == media_id),)),
            (Post, (Post.featured_media_id == media_id, Post.status == "published")),
            (Teacher, (Teacher.photo_media_id == media_id, Teacher.is_published.is_(True))),
            (GalleryImage, (GalleryImage.media_id == media_id, GalleryImage.is_published.is_(True))),
        )
    )
    if not publicly_referenced:
        raise HTTPException(404, "Image not found.")
    return media_response(item, "public, max-age=86400")


@app.get("/api/public/meta/sitemap")
def sitemap_entries(db: Session = Depends(get_db)):
    return {"pages": db.scalars(select(Page.slug).where(Page.is_published.is_(True))).all(),
            "posts": db.scalars(select(Post.slug).where(Post.status == "published")).all()}
