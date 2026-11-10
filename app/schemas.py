import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class AdminView(BaseModel):
    id: int
    email: EmailStr
    must_change_password: bool


class ContentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileUpdate(ContentBase):
    email: EmailStr


class SettingsUpdate(ContentBase):
    name_en: str = Field(min_length=1, max_length=200)
    name_hi: str = Field(min_length=1, max_length=200)
    address_en: str = Field(min_length=1, max_length=1000)
    address_hi: str = Field(min_length=1, max_length=1000)
    manager_en: str = Field(min_length=1, max_length=160)
    manager_hi: str = Field(min_length=1, max_length=160)
    principal_en: str = Field(min_length=1, max_length=160)
    principal_hi: str = Field(min_length=1, max_length=160)
    clerk_en: str = Field(min_length=1, max_length=160)
    clerk_hi: str = Field(min_length=1, max_length=160)
    about_en: str = ""
    about_hi: str = ""
    mission_en: str = ""
    mission_hi: str = ""
    vision_en: str = ""
    vision_hi: str = ""
    homepage_en: str = ""
    homepage_hi: str = ""
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    map_url: HttpUrl | None = None
    logo_media_id: int | None = None
    favicon_media_id: int | None = None
    social_links: str = "{}"
    footer_en: str = ""
    footer_hi: str = ""

    @field_validator("social_links")
    @classmethod
    def validate_social_links(cls, value: str) -> str:
        if len(value) > 4000:
            raise ValueError("Social links configuration is too large.")
        try:
            links = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Social links must be a JSON object of HTTPS URLs.") from exc
        if not isinstance(links, dict) or any(
            not isinstance(name, str)
            or not isinstance(url, str)
            or not url.startswith("https://")
            for name, url in links.items()
        ):
            raise ValueError("Social links must be a JSON object of HTTPS URLs.")
        return json.dumps(links, ensure_ascii=False)


class PostInput(ContentBase):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=180)
    title_en: str = Field(min_length=1, max_length=250)
    title_hi: str = Field(min_length=1, max_length=250)
    body_en: str = ""
    body_hi: str = ""
    featured_media_id: int | None = None
    seo_title_en: str | None = Field(default=None, max_length=250)
    seo_title_hi: str | None = Field(default=None, max_length=250)
    meta_description_en: str | None = Field(default=None, max_length=320)
    meta_description_hi: str | None = Field(default=None, max_length=320)
    status: Literal["draft", "published"] = "draft"


class TeacherInput(ContentBase):
    name_en: str = Field(min_length=1, max_length=160)
    name_hi: str = Field(min_length=1, max_length=160)
    qualification_en: str = Field(default="", max_length=250)
    qualification_hi: str = Field(default="", max_length=250)
    subject_en: str = Field(default="", max_length=250)
    subject_hi: str = Field(default="", max_length=250)
    bio_en: str = ""
    bio_hi: str = ""
    photo_media_id: int | None = None
    display_order: int = 0
    is_published: bool = True


class GalleryCategoryInput(ContentBase):
    name_en: str = Field(min_length=1, max_length=100)
    name_hi: str = Field(min_length=1, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)


class GalleryInput(ContentBase):
    media_id: int
    category_id: int | None = None
    title_en: str = Field(default="", max_length=200)
    title_hi: str = Field(default="", max_length=200)
    description_en: str = ""
    description_hi: str = ""
    display_order: int = 0
    is_published: bool = True


class AnnouncementInput(ContentBase):
    title_en: str = Field(min_length=1, max_length=250)
    title_hi: str = Field(min_length=1, max_length=250)
    body_en: str = ""
    body_hi: str = ""
    is_published: bool = False


class PageInput(ContentBase):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=180)
    title_en: str = Field(min_length=1, max_length=250)
    title_hi: str = Field(min_length=1, max_length=250)
    content_en: str = ""
    content_hi: str = ""
    seo_title_en: str | None = Field(default=None, max_length=250)
    seo_title_hi: str | None = Field(default=None, max_length=250)
    meta_description_en: str | None = Field(default=None, max_length=320)
    meta_description_hi: str | None = Field(default=None, max_length=320)
    is_published: bool = True


class ContactInput(ContentBase):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    message: str = Field(min_length=10, max_length=5000)
    website: str = Field(default="", max_length=200)


class PageQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ApiList(BaseModel):
    items: list[dict]
    page: int
    page_size: int
    total: int
