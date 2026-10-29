"""Consentement à la conservation et suppression de l'historique utilisateur."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from subtitler.api import create_app

from subtitler.jobs.models import OutputKind
from subtitler.jobs.store import JobStore
from tests.conftest import login, login_admin, requires_ffmpeg
from tests.test_api import submit, wait_for
from tests.test_store import make_job


@pytest.fixture
def idle_client_factory(settings, transcriber):
    # Sans « with », aucun worker ne démarre : les jobs restent en attente.
    return lambda: TestClient(create_app(settings, transcriber_factory=lambda name: transcriber))


def submit_with_consent(client, path, consent):
    with path.open("rb") as file:
        return client.post(
            "/api/jobs",
            files={"file": (path.name, file)},
            data={"output_kind": "text", "consent": "true" if consent else "false"},
        )


def test_hidden_jobs_leave_user_history_but_stay_stored(tmp_path):
    store = JobStore(tmp_path / "db.sqlite")
    for job_id in ("a", "b", "c"):
        job = make_job(job_id, OutputKind.TEXT)
        job.user_id = "alice" if job_id != "c" else "bob"
        store.add(job)

    store.hide("a")
    assert [job.id for job in store.recent(user_id="alice")] == ["b"]
    assert store.get("a").hidden_at is not None
    assert len(store.recent()) == 3  # vue administrateur : tout reste visible

    assert store.hide_all("alice") == 1
    assert store.recent(user_id="alice") == []
    assert [job.id for job in store.recent(user_id="bob")] == ["c"]
    assert store.stats()["total_jobs"] == 3


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, filename TEXT NOT NULL, input_kind TEXT NOT NULL,"
            " output_kind TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,"
            " created_at TEXT NOT NULL, media_duration REAL, started_at TEXT, finished_at TEXT,"
            " processing_time REAL, text TEXT, error TEXT)"
        )
        db.execute(
            "INSERT INTO jobs (id, filename, input_kind, output_kind, model, status, created_at)"
            " VALUES ('old', 'old.mp4', 'video', 'text', 'm', 'done', '2026-01-01T00:00:00+00:00')"
        )
    job = JobStore(path).get("old")
    assert job.consent is False and job.hidden_at is None and job.user_id is None


@requires_ffmpeg
@pytest.mark.parametrize("consent", [True, False])
def test_consent_is_recorded(client, audio_file, consent):
    response = submit_with_consent(client, audio_file, consent)
    assert response.status_code == 202
    job = wait_for(client, response.json()["id"])
    # Le traitement a lieu dans les deux cas : le consentement est facultatif.
    assert job["status"] == "done"
    assert job["consent"] is consent
    assert (job["consent_at"] is not None) is consent


@requires_ffmpeg
def test_consent_defaults_to_refused(client, audio_file):
    assert submit(client, audio_file, "text").json()["consent"] is False


@requires_ffmpeg
def test_delete_hides_job_but_keeps_files(client, settings, audio_file):
    kept = wait_for(client, submit(client, audio_file, "text").json()["id"])
    removed = wait_for(client, submit(client, audio_file, "text").json()["id"])

    assert client.delete(f"/api/jobs/{removed['id']}").status_code == 204
    assert [job["id"] for job in client.get("/api/jobs").json()] == [kept["id"]]
    assert client.get(f"/api/jobs/{removed['id']}").status_code == 404
    assert client.get(f"/api/jobs/{removed['id']}/result").status_code == 404
    assert client.delete(f"/api/jobs/{removed['id']}").status_code == 404
    assert (settings.jobs_dir / removed["id"] / "result.txt").is_file()

    login_admin(client)
    hidden = client.get(f"/api/jobs/{removed['id']}").json()
    assert hidden["hidden_at"] is not None
    assert client.get(f"/api/jobs/{removed['id']}/result").status_code == 200


@requires_ffmpeg
def test_delete_all_only_touches_own_history(client, audio_file):
    for _ in range(2):
        submit(client, audio_file, "text")
    login(client, "bob")
    bob_job = submit(client, audio_file, "text").json()["id"]

    login(client, "alice")
    assert client.delete("/api/jobs").status_code == 204
    assert client.get("/api/jobs").json() == []

    login(client, "bob")
    assert [job["id"] for job in client.get("/api/jobs").json()] == [bob_job]
    login_admin(client)
    assert len(client.get("/api/jobs?all=true").json()) == 3


@requires_ffmpeg
def test_admin_cannot_hide_someone_elses_job(client, audio_file):
    job_id = submit(client, audio_file, "text").json()["id"]
    login_admin(client)
    assert client.delete(f"/api/jobs/{job_id}").status_code == 403


def test_count_matches_history(tmp_path):
    store = JobStore(tmp_path / "db.sqlite")
    for job_id in ("a", "b", "c"):
        job = make_job(job_id, OutputKind.TEXT)
        job.user_id = "alice"
        store.add(job)
    store.hide("a")
    assert store.count("alice") == 2
    assert store.count() == 3


@requires_ffmpeg
def test_history_pagination(idle_client_factory, audio_file):
    client = idle_client_factory()
    ids = []
    for index in range(3):
        login(client, f"user{index}")  # la limite de 5 traitements en attente vaut par utilisateur
        ids += [submit(client, audio_file, "text").json()["id"] for _ in range(4)]
    login_admin(client)

    first = client.get("/api/jobs?all=true&limit=5&offset=0")
    last = client.get("/api/jobs?all=true&limit=5&offset=10")
    assert first.headers["X-Total-Count"] == "12"
    assert [job["id"] for job in first.json()] == ids[::-1][:5]  # le plus récent en premier
    assert [job["id"] for job in last.json()] == ids[::-1][10:]

    login(client, "user0")
    client.delete(f"/api/jobs/{ids[0]}")
    mine = client.get("/api/jobs?limit=2")
    assert mine.headers["X-Total-Count"] == "3"  # sans le traitement retiré
    assert len(mine.json()) == 2
