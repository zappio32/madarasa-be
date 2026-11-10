from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstitutionSettings(TimestampMixin, Base):
    __tablename__ = "institution_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_en: Mapped[str] = mapped_column(String(200), default="Madarasa Islamiya Faizee - aam")
    name_hi: Mapped[str] = mapped_column(String(200), default="मदरसा इस्लामिया फैज़ ए आम")
    address_en: Mapped[str] = mapped_column(Text, default="Patera Buzurg, Post Balkuriya, Kushinagar, Uttar Pradesh - 274304, India.")
    address_hi: Mapped[str] = mapped_column(Text, default="पटेरा बुज़ुर्ग, पोस्ट बलकुरिया, कुशीनगर, उत्तर प्रदेश - 274304, भारत।")
    manager_en: Mapped[str] = mapped_column(String(160), default="Mohd. Nashrullah")
    manager_hi: Mapped[str] = mapped_column(String(160), default="मोहम्मद नश्रुल्लाह")
    principal_en: Mapped[str] = mapped_column(String(160), default="Azizurrahman")
    principal_hi: Mapped[str] = mapped_column(String(160), default="अज़ीज़ुर्रहमान")
    clerk_en: Mapped[str] = mapped_column(String(160), default="Iliyas Ahmad Ansari")
    clerk_hi: Mapped[str] = mapped_column(String(160), default="इलियास अहमद अंसारी")
    about_en: Mapped[str] = mapped_column(Text, default="")
    about_hi: Mapped[str] = mapped_column(Text, default="")
    mission_en: Mapped[str] = mapped_column(Text, default="")
    mission_hi: Mapped[str] = mapped_column(Text, default="")
    vision_en: Mapped[str] = mapped_column(Text, default="")
    vision_hi: Mapped[str] = mapped_column(Text, default="")
    homepage_en: Mapped[str] = mapped_column(Text, default="")
    homepage_hi: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    map_url: Mapped[str | None] = mapped_column(String(1000))
    logo_media_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))
    favicon_media_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))
    social_links: Mapped[str] = mapped_column(Text, default="{}")
    footer_en: Mapped[str] = mapped_column(Text, default="")
    footer_hi: Mapped[str] = mapped_column(Text, default="")


class Page(TimestampMixin, Base):
    __tablename__ = "pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    title_en: Mapped[str] = mapped_column(String(250))
    title_hi: Mapped[str] = mapped_column(String(250))
    content_en: Mapped[str] = mapped_column(Text, default="")
    content_hi: Mapped[str] = mapped_column(Text, default="")
    seo_title_en: Mapped[str | None] = mapped_column(String(250))
    seo_title_hi: Mapped[str | None] = mapped_column(String(250))
    meta_description_en: Mapped[str | None] = mapped_column(String(320))
    meta_description_hi: Mapped[str | None] = mapped_column(String(320))
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Post(TimestampMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (Index("ix_posts_status_published_at", "status", "published_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    title_en: Mapped[str] = mapped_column(String(250))
    title_hi: Mapped[str] = mapped_column(String(250))
    body_en: Mapped[str] = mapped_column(Text, default="")
    body_hi: Mapped[str] = mapped_column(Text, default="")
    featured_media_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))
    seo_title_en: Mapped[str | None] = mapped_column(String(250))
    seo_title_hi: Mapped[str | None] = mapped_column(String(250))
    meta_description_en: Mapped[str | None] = mapped_column(String(320))
    meta_description_hi: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"))
    author: Mapped[Admin | None] = relationship()


class Teacher(TimestampMixin, Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_en: Mapped[str] = mapped_column(String(160))
    name_hi: Mapped[str] = mapped_column(String(160))
    qualification_en: Mapped[str] = mapped_column(String(250), default="")
    qualification_hi: Mapped[str] = mapped_column(String(250), default="")
    subject_en: Mapped[str] = mapped_column(String(250), default="")
    subject_hi: Mapped[str] = mapped_column(String(250), default="")
    bio_en: Mapped[str] = mapped_column(Text, default="")
    bio_hi: Mapped[str] = mapped_column(Text, default="")
    photo_media_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class GalleryCategory(TimestampMixin, Base):
    __tablename__ = "gallery_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_en: Mapped[str] = mapped_column(String(100))
    name_hi: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    images: Mapped[list["GalleryImage"]] = relationship(back_populates="category")


class GalleryImage(TimestampMixin, Base):
    __tablename__ = "gallery_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_files.id", ondelete="CASCADE"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("gallery_categories.id", ondelete="SET NULL"))
    title_en: Mapped[str] = mapped_column(String(200), default="")
    title_hi: Mapped[str] = mapped_column(String(200), default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_hi: Mapped[str] = mapped_column(Text, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    category: Mapped[GalleryCategory | None] = relationship(back_populates="images")


class Announcement(TimestampMixin, Base):
    __tablename__ = "announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    title_en: Mapped[str] = mapped_column(String(250))
    title_hi: Mapped[str] = mapped_column(String(250))
    body_en: Mapped[str] = mapped_column(Text, default="")
    body_hi: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"))


class ContactMessage(TimestampMixin, Base):
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MediaFile(TimestampMixin, Base):
    __tablename__ = "media_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    original_name: Mapped[str] = mapped_column(String(255))
    alt_en: Mapped[str] = mapped_column(String(250), default="")
    alt_hi: Mapped[str] = mapped_column(String(250), default="")


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
