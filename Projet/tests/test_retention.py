"""Purge des données au-delà de la durée de conservation (6 mois)."""

import dataclasses
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from subtitler.api import create_app
from subtitler.jobs.models import OutputKind
from subtitler.jobs.retention import RetentionTask, purge_expired
from subtitler.jobs.store import JobStore
from tests.conftest import login, login_admin, requires_ffmpeg
from tests.test_api import submit, wait_for
from tests.test_store import make_job

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def add_job(store, jobs_dir, job_id, age_days, finish=True):
    job = make_job(job_id, OutputKind.TEXT)
    job.created_at = NOW - timedelta(days=age_days)
    store.add(job)
    (jobs_dir / job_id).mkdir(parents=True)
    (jobs_dir / job_id / "input.wav").write_bytes(b"audio")
    if finish:
        store.mark_running(job_id)
        store.mark_done(job_id, "texte", processing_time=1.0)


def test_only_finished_jobs_older_than_retention_are_purged(tmp_path):
    store, jobs_dir = JobStore(tmp_path / "db.sqlite"), tmp_path / "jobs"
    add_job(store, jobs_dir, "old", age_days=200)
    add_job(store, jobs_dir, "recent", age_days=10)
    add_job(store, jobs_dir, "limit", age_days=182)
    add_job(store, jobs_dir, "old-pending", age_days=200, finish=False)  # jamais purgé tant qu'il n'est pas fini
    add_job(store, jobs_dir, "old-hidden", age_days=300)
    store.hide("old-hidden")
    add_job(store, jobs_dir, "old-cancelled", age_days=300, finish=False)
    store.cancel("old-cancelled")

    assert purge_expired(store, jobs_dir, retention_days=183, now=NOW) == 3

    remaining = {job.id for job in store.recent()}
    assert remaining == {"recent", "limit", "old-pending"}
    assert sorted(path.name for path in jobs_dir.iterdir()) == ["limit", "old-pending", "recent"]
    assert purge_expired(store, jobs_dir, retention_days=183, now=NOW) == 0


def test_job_without_files_is_still_purged(tmp_path):
    store, jobs_dir = JobStore(tmp_path / "db.sqlite"), tmp_path / "jobs"
    add_job(store, jobs_dir, "old", age_days=200)
    (jobs_dir / "old" / "input.wav").unlink()
    (jobs_dir / "old").rmdir()
    assert purge_expired(store, jobs_dir, retention_days=183, now=NOW) == 1


def test_background_task_purges_at_startup(tmp_path):
    store, jobs_dir = JobStore(tmp_path / "db.sqlite"), tmp_path / "jobs"
    add_job(store, jobs_dir, "old", age_days=400)
    task = RetentionTask(store, jobs_dir, retention_days=183, interval=60)
    task.start()
    task.stop()  # attend la fin du premier passage
    assert store.get("old") is None


def test_purge_endpoint_is_admin_only(client):
    assert client.post("/api/admin/purge").status_code == 403
    assert client.get("/api/info").json()["retention_days"] == 183


@requires_ffmpeg
def test_admin_can_trigger_purge(settings, transcriber, audio_file):
    # Durée de conservation nulle : tout traitement terminé est déjà expiré.
    settings = dataclasses.replace(settings, retention_days=0)
    with TestClient(create_app(settings, transcriber_factory=lambda name: transcriber)) as client:
        login(client)
        job_id = wait_for(client, submit(client, audio_file, "text").json()["id"])["id"]
        login_admin(client)
        assert client.post("/api/admin/purge").json() == {"deleted": 1}
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert not (settings.jobs_dir / job_id).exists()
