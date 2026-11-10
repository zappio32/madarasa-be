import io

from PIL import Image

from app.models import Admin
from app.security import hash_password, verify_password


def test_password_hashing_is_one_way_and_verifiable():
    hashed = hash_password("a-long-test-password")
    assert hashed != "a-long-test-password"
    assert verify_password("a-long-test-password", hashed)
    assert not verify_password("incorrect-password", hashed)


def test_authentication_and_csrf(client):
    assert client.get("/api/admin/dashboard").status_code == 401
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong"}).status_code == 401
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "test-password-1234"})
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/admin/dashboard").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/admin/dashboard").status_code == 401


def test_initial_password_must_be_changed(client):
    with client.app.state.test_session() as db:
        admin = db.query(Admin).filter_by(email="admin@example.com").one()
        admin.must_change_password = True
        db.commit()
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "test-password-1234"})
    client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
    assert client.get("/api/admin/dashboard").status_code == 403
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": "test-password-1234", "new_password": "a-new-test-password-2026"},
    )
    assert changed.status_code == 200
    assert client.get("/api/admin/dashboard").status_code == 200


def test_post_create_publish_edit_delete_and_public_visibility(authenticated):
    payload = {
        "slug": "first-update",
        "title_en": "First update",
        "title_hi": "पहली सूचना",
        "body_en": "English information.",
        "body_hi": "हिन्दी जानकारी।",
        "status": "published",
    }
    created = authenticated.post("/api/admin/posts", json=payload)
    assert created.status_code == 201
    assert authenticated.get("/api/public/posts/first-update").json()["title_hi"] == "पहली सूचना"

    payload["title_en"] = "Updated update"
    updated = authenticated.put(f"/api/admin/posts/{created.json()['id']}", json=payload)
    assert updated.status_code == 200
    assert authenticated.get("/api/public/posts/first-update").json()["title_en"] == "Updated update"
    assert authenticated.delete(f"/api/admin/posts/{created.json()['id']}").status_code == 204
    assert authenticated.get("/api/public/posts/first-update").status_code == 404


def test_teacher_crud(authenticated):
    payload = {"name_en": "Teacher One", "name_hi": "शिक्षक एक", "subject_en": "Science", "subject_hi": "विज्ञान"}
    created = authenticated.post("/api/admin/teachers", json=payload)
    assert created.status_code == 201
    assert authenticated.get("/api/public/teachers").json()[0]["name_en"] == "Teacher One"
    payload["name_en"] = "Teacher Updated"
    assert authenticated.put(f"/api/admin/teachers/{created.json()['id']}", json=payload).status_code == 200
    assert authenticated.delete(f"/api/admin/teachers/{created.json()['id']}").status_code == 204
    assert authenticated.get("/api/public/teachers").json() == []


def test_settings_are_publicly_readable_and_admin_editable(authenticated):
    original = authenticated.get("/api/admin/settings")
    assert original.status_code == 200
    payload = {
        key: original.json()[key]
        for key in (
            "name_en", "name_hi", "address_en", "address_hi", "manager_en", "manager_hi",
            "principal_en", "principal_hi", "clerk_en", "clerk_hi", "about_en", "about_hi",
            "mission_en", "mission_hi", "vision_en", "vision_hi", "homepage_en", "homepage_hi",
            "phone", "email", "map_url", "logo_media_id", "favicon_media_id", "social_links",
            "footer_en", "footer_hi",
        )
    }
    payload["name_en"] = "Edited institution name"
    updated = authenticated.put("/api/admin/settings", json=payload)
    assert updated.status_code == 200
    assert authenticated.get("/api/public/settings").json()["name_en"] == "Edited institution name"


def test_gallery_upload_validates_image_and_serves_persisted_media(authenticated, monkeypatch, tmp_path):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "local_media_path", str(tmp_path))
    invalid = authenticated.post("/api/admin/media/upload", files={"file": ("fake.jpg", b"not an image", "image/jpeg")})
    assert invalid.status_code == 415

    image = Image.new("RGB", (80, 60), color="green")
    raw = io.BytesIO()
    image.save(raw, format="PNG")
    uploaded = authenticated.post("/api/admin/media/upload", files={"file": ("school.png", raw.getvalue(), "image/png")})
    assert uploaded.status_code == 201
    media_response = authenticated.get(f"/api/public/media/{uploaded.json()['id']}")
    assert media_response.status_code == 404
    admin_preview = authenticated.get(f"/api/admin/media/{uploaded.json()['id']}")
    assert admin_preview.status_code == 200
    assert admin_preview.headers["cache-control"] == "private, no-store"
    assert admin_preview.headers["content-type"] == "image/png"


def test_gallery_category_and_image_crud(authenticated, monkeypatch, tmp_path):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "local_media_path", str(tmp_path))
    image = Image.new("RGB", (40, 30), color="green")
    raw = io.BytesIO()
    image.save(raw, format="PNG")
    media = authenticated.post("/api/admin/media/upload", files={"file": ("gallery.png", raw.getvalue(), "image/png")}).json()
    category = authenticated.post(
        "/api/admin/gallery/categories",
        json={"name_en": "Learning", "name_hi": "शिक्षा", "slug": "learning"},
    )
    assert category.status_code == 201
    category_id = category.json()["id"]
    created = authenticated.post(
        "/api/admin/gallery",
        json={"media_id": media["id"], "category_id": category_id, "title_en": "Classroom", "title_hi": "कक्षा"},
    )
    assert created.status_code == 201
    public_media = authenticated.get(f"/api/public/media/{media['id']}")
    assert public_media.status_code == 200
    assert authenticated.get("/api/public/gallery?category=learning").json()[0]["title_hi"] == "कक्षा"
    edited = authenticated.put(
        f"/api/admin/gallery/{created.json()['id']}",
        json={"media_id": media["id"], "category_id": category_id, "title_en": "Updated classroom", "title_hi": "नई कक्षा"},
    )
    assert edited.status_code == 200
    assert authenticated.delete(f"/api/admin/gallery/{created.json()['id']}").status_code == 204
    assert authenticated.get("/api/public/gallery").json() == []
    assert authenticated.delete(f"/api/admin/gallery/categories/{category_id}").status_code == 204


def test_announcements_pages_and_contact_inbox(authenticated):
    announcement = authenticated.post(
        "/api/admin/announcements",
        json={"title_en": "Notice", "title_hi": "सूचना", "body_en": "Welcome.", "body_hi": "स्वागत है।", "is_published": True},
    )
    assert announcement.status_code == 201
    assert authenticated.get("/api/public/announcements").json()[0]["title_hi"] == "सूचना"
    assert authenticated.put(
        f"/api/admin/announcements/{announcement.json()['id']}",
        json={"title_en": "Updated notice", "title_hi": "नई सूचना", "is_published": True},
    ).status_code == 200
    assert authenticated.delete(f"/api/admin/announcements/{announcement.json()['id']}").status_code == 204

    page = authenticated.post(
        "/api/admin/pages",
        json={"slug": "school-values", "title_en": "Our values", "title_hi": "हमारे मूल्य", "is_published": True},
    )
    assert page.status_code == 201
    assert authenticated.get("/api/public/pages/school-values").json()["title_hi"] == "हमारे मूल्य"
    assert authenticated.delete(f"/api/admin/pages/{page.json()['id']}").status_code == 204

    sent = authenticated.post(
        "/api/public/contact",
        json={"name": "A parent", "email": "parent@example.com", "message": "Please share more information."},
    )
    assert sent.status_code == 201
    inbox_item = authenticated.get("/api/admin/contact-messages").json()["items"][0]
    assert inbox_item["name"] == "A parent"
    assert authenticated.patch(f"/api/admin/contact-messages/{inbox_item['id']}?is_read=true").status_code == 200
    assert authenticated.delete(f"/api/admin/contact-messages/{inbox_item['id']}").status_code == 204


def test_social_links_accept_only_https_urls(authenticated):
    current = authenticated.get("/api/admin/settings").json()
    payload = {
        key: current[key]
        for key in (
            "name_en", "name_hi", "address_en", "address_hi", "manager_en", "manager_hi",
            "principal_en", "principal_hi", "clerk_en", "clerk_hi", "about_en", "about_hi",
            "mission_en", "mission_hi", "vision_en", "vision_hi", "homepage_en", "homepage_hi",
            "phone", "email", "map_url", "logo_media_id", "favicon_media_id", "social_links",
            "footer_en", "footer_hi",
        )
    }
    payload["social_links"] = '{"facebook":"javascript:alert(1)"}'
    assert authenticated.put("/api/admin/settings", json=payload).status_code == 422
    payload["social_links"] = '{"facebook":"https://example.org"}'
    assert authenticated.put("/api/admin/settings", json=payload).status_code == 200


def test_profile_change_and_session_refresh(authenticated):
    response = authenticated.put("/api/auth/profile", json={"email": "new-admin@example.com"})
    assert response.status_code == 200
    assert authenticated.get("/api/auth/me").json()["email"] == "new-admin@example.com"
    refreshed = authenticated.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert authenticated.get("/api/admin/dashboard").status_code == 200
