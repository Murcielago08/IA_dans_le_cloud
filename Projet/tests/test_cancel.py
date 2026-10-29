"""Annulation d'un traitement en attente ou en cours."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from subtitler.api import create_app
from subtitler.jobs.models import JobStatus, OutputKind
from subtitler.jobs.store import JobStore
from subtitler.transcription.base import Transcriber
from tests.conftest import FAKE_SEGMENTS, login, login_admin, requires_ffmpeg
from tests.test_api import submit, wait_for
from tests.test_store import make_job


def test_cancelled_job_cannot_change_state(tmp_path):
    store = JobStore(tmp_path / "db.sqlite")
    store.add(make_job("a", OutputKind.TEXT))
    assert store.cancel("a")
    assert not store.mark_running("a")  # annulé en attente : jamais démarré
    assert not store.cancel("a")
    assert store.unfinished_ids() == []

    store.add(make_job("b", OutputKind.TEXT))
    store.mark_running("b")
    store.cancel("b")
    store.mark_done("b", "trop tard", processing_time=1.0)  # le résultat arrivé après est ignoré
    assert store.get("b").status is JobStatus.CANCELLED

    store.add(make_job("c", OutputKind.TEXT))
    store.mark_running("c")
    store.mark_done("c", "ok", processing_time=1.0)
    assert not store.cancel("c")

    stats = store.stats()
    assert stats["cancelled"]["by_kind"]["text"] == 2
    assert stats["unfinished"]["total"] == 0


@pytest.fixture
def idle_client(settings, transcriber):
    # Sans « with », aucun worker ne démarre : les jobs restent en attente.
    client = TestClient(create_app(settings, transcriber_factory=lambda name: transcriber))
    login(client)
    return client


@requires_ffmpeg
def test_cancel_pending_job_frees_a_slot(idle_client, audio_file):
    ids = [submit(idle_client, audio_file, "text").json()["id"] for _ in range(5)]
    assert submit(idle_client, audio_file, "text").status_code == 429

    response = idle_client.post(f"/api/jobs/{ids[0]}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert idle_client.post(f"/api/jobs/{ids[0]}/cancel").status_code == 409
    assert idle_client.get(f"/api/jobs/{ids[0]}/result").status_code == 409
    assert submit(idle_client, audio_file, "text").status_code == 202


@requires_ffmpeg
def test_only_owner_or_admin_can_cancel(idle_client, audio_file):
    alice_job, other_job = (submit(idle_client, audio_file, "text").json()["id"] for _ in range(2))
    login(idle_client, "bob")
    assert idle_client.post(f"/api/jobs/{alice_job}/cancel").status_code == 404
    login_admin(idle_client)
    assert idle_client.post(f"/api/jobs/{other_job}/cancel").status_code == 200


class BlockingTranscriber(Transcriber):
    """Reste « en cours de transcription » jusqu'à ce que le test le libère."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio_path):
        self.started.set()
        self.release.wait(timeout=10)
        return FAKE_SEGMENTS


@requires_ffmpeg
def test_cancel_running_job(settings, audio_file):
    blocking = BlockingTranscriber()
    with TestClient(create_app(settings, transcriber_factory=lambda name: blocking)) as client:
        login(client)
        job_id = submit(client, audio_file, "text").json()["id"]
        assert blocking.started.wait(timeout=10)
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "running"

        assert client.post(f"/api/jobs/{job_id}/cancel").json()["status"] == "cancelled"
        blocking.release.set()
        time.sleep(0.3)  # laisse le worker finir son étape et constater l'annulation

        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "cancelled"
        assert job["text"] is None
        assert not (settings.jobs_dir / job_id / "result.txt").exists()

        # Le worker est libre pour la suite.
        assert wait_for(client, submit(client, audio_file, "text").json()["id"])["status"] == "done"
