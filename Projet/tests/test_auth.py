from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from subtitler.api import create_app
from subtitler.config import Settings
from subtitler.users import UserError, UserStore
from tests.conftest import PASSWORD, login, login_admin, requires_ffmpeg
from tests.test_api import submit, wait_for


@pytest.fixture
def anonymous(settings, transcriber):
    with TestClient(create_app(settings, transcriber_factory=lambda name: transcriber)) as client:
        yield client


def test_password_is_hashed(tmp_path):
    store = UserStore(tmp_path / "db.sqlite")
    store.create("alice", PASSWORD)
    assert PASSWORD.encode() not in (tmp_path / "db.sqlite").read_bytes()
    assert store.authenticate("alice", PASSWORD).username == "alice"
    assert store.authenticate("ALICE", PASSWORD) is not None  # identifiant insensible à la casse
    assert store.authenticate("alice", "wrong-password") is None
    assert store.authenticate("bob", PASSWORD) is None


@pytest.mark.parametrize(
    ("username", "password", "message"),
    [("al", PASSWORD, "Identifiant invalide"), ("al ice", PASSWORD, "Identifiant invalide"),
     ("alice", "short", "trop court")],
)
def test_invalid_accounts_are_refused(tmp_path, username, password, message):
    with pytest.raises(UserError, match=message):
        UserStore(tmp_path / "db.sqlite").create(username, password)


def test_duplicate_username(tmp_path):
    store = UserStore(tmp_path / "db.sqlite")
    store.create("alice", PASSWORD)
    with pytest.raises(UserError, match="déjà utilisé"):
        store.create("Alice", PASSWORD)


def test_expired_session(tmp_path):
    store = UserStore(tmp_path / "db.sqlite", session_lifetime=timedelta(seconds=-1))
    token = store.open_session(store.create("alice", PASSWORD))
    assert store.user_for_token(token) is None


def test_api_requires_login(anonymous):
    assert anonymous.get("/api/health").status_code == 200
    assert anonymous.get("/api/info").status_code == 200
    for path in ("/api/jobs", "/api/jobs/x", "/api/jobs/x/result", "/api/stats", "/api/auth/me"):
        assert anonymous.get(path).status_code == 401, path
    assert anonymous.post("/api/jobs", data={"output_kind": "text"}).status_code == 401


def test_register_login_logout(anonymous):
    created = anonymous.post("/api/auth/register", json={"username": "alice", "password": PASSWORD})
    assert created.status_code == 201
    assert anonymous.get("/api/auth/me").json()["username"] == "alice"

    assert anonymous.post("/api/auth/logout").status_code == 204
    assert anonymous.get("/api/auth/me").status_code == 401

    wrong = anonymous.post("/api/auth/login", json={"username": "alice", "password": "nope-nope"})
    assert wrong.status_code == 401
    token = anonymous.post("/api/auth/login", json={"username": "alice", "password": PASSWORD}).json()["token"]
    # Clients API : le jeton suffit, sans cookie.
    anonymous.cookies.clear()
    me = anonymous.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json() == {"id": created.json()["user"]["id"], "username": "alice", "is_admin": False}


def test_signup_can_be_disabled(tmp_path, transcriber):
    settings = Settings(data_dir=tmp_path / "data", device="cpu", allow_signup=False)
    with TestClient(create_app(settings, transcriber_factory=lambda name: transcriber)) as client:
        assert client.get("/api/info").json()["signup_enabled"] is False
        response = client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD})
        assert response.status_code == 403


def test_admin_account_from_settings(anonymous):
    assert login_admin(anonymous)["user"]["is_admin"] is True
    assert anonymous.get("/api/stats").status_code == 200


def test_stats_are_admin_only(client):
    assert client.get("/api/stats").status_code == 403
    assert client.get("/api/jobs?all=true").status_code == 403


@requires_ffmpeg
def test_users_only_see_their_own_jobs(anonymous, audio_file):
    login(anonymous, "alice")
    job_id = wait_for(anonymous, submit(anonymous, audio_file, "text").json()["id"])["id"]

    login(anonymous, "bob")
    assert anonymous.get("/api/jobs").json() == []
    for path in (f"/api/jobs/{job_id}", f"/api/jobs/{job_id}/result", f"/api/jobs/{job_id}/subtitles.vtt"):
        assert anonymous.get(path).status_code == 404, path

    login_admin(anonymous)
    assert anonymous.get("/api/jobs").json() == []
    jobs = anonymous.get("/api/jobs?all=true").json()
    assert [(job["id"], job["username"]) for job in jobs] == [(job_id, "alice")]
    assert anonymous.get(f"/api/jobs/{job_id}/result").status_code == 200
