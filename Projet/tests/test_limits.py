"""Limite du nombre de traitements simultanés par utilisateur."""

import pytest
from fastapi.testclient import TestClient

from subtitler.api import create_app
from tests.conftest import login, requires_ffmpeg
from tests.test_api import submit, wait_for

pytestmark = requires_ffmpeg


@pytest.fixture
def idle_client(settings, transcriber):
    # Sans « with », aucun worker ne démarre : les jobs restent en attente.
    client = TestClient(create_app(settings, transcriber_factory=lambda name: transcriber))
    login(client)
    return client


def test_sixth_simultaneous_job_is_refused(idle_client, settings, audio_file):
    assert idle_client.get("/api/info").json()["max_jobs_per_user"] == 5
    ids = [submit(idle_client, audio_file, "text").json()["id"] for _ in range(5)]

    refused = submit(idle_client, audio_file, "text")
    assert refused.status_code == 429
    assert "5 traitements en cours" in refused.json()["detail"]
    # Le fichier refusé n'est ni enregistré ni compté.
    assert len(list(settings.jobs_dir.iterdir())) == 5
    assert len(idle_client.get("/api/jobs").json()) == 5

    # Masquer un traitement en cours ne libère pas de place : il tourne toujours.
    idle_client.delete(f"/api/jobs/{ids[0]}")
    assert submit(idle_client, audio_file, "text").status_code == 429


def test_limit_is_per_user(idle_client, audio_file):
    for _ in range(5):
        submit(idle_client, audio_file, "text")
    login(idle_client, "bob")
    assert submit(idle_client, audio_file, "text").status_code == 202


def test_finished_jobs_free_a_slot(settings, transcriber, audio_file):
    client = TestClient(create_app(settings, transcriber_factory=lambda name: transcriber))
    login(client)
    ids = [submit(client, audio_file, "text").json()["id"] for _ in range(5)]
    assert submit(client, audio_file, "text").status_code == 429

    # Redémarrage avec workers : les 5 jobs en attente sont traités.
    with TestClient(create_app(settings, transcriber_factory=lambda name: transcriber)) as client:
        login(client)
        for job_id in ids:
            wait_for(client, job_id)
        assert submit(client, audio_file, "text").status_code == 202
