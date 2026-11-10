import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app, limiter
from app.models import Admin
from app.security import hash_password


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    app.state.test_session = TestingSession
    with TestingSession() as db:
        db.add(Admin(email="admin@example.com", password_hash=hash_password("test-password-1234"), must_change_password=False))
        db.commit()

    def override_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.enabled = True
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def authenticated(client):
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "test-password-1234"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
    return client
