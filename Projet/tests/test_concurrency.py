"""Preuve structurelle que la file de jobs parallélise bien le traitement.

Ce test ne mesure pas une vraie performance GPU (impossible sans GPU dans la
CI) : il vérifie que l'architecture (file d'attente + pool de threads,
`SUBTITLER_WORKERS`) traite bien N jobs en parallèle plutôt qu'en série, avec
un faux transcripteur à délai fixe. Pour un vrai banc de perf sur matériel
réel, voir ``scripts/load_test.py``.
"""

import time

import pytest
from fastapi.testclient import TestClient

from subtitler.api import create_app
from subtitler.config import Settings
from subtitler.transcription.base import Transcriber
from tests.conftest import FAKE_SEGMENTS, requires_ffmpeg
from tests.test_api import submit, wait_for

pytestmark = requires_ffmpeg

DELAY = 0.3
WORKERS = 5


class SlowTranscriber(Transcriber):
    """Simule un temps de traitement GPU fixe, pour mesurer le parallélisme."""

    def transcribe(self, audio_path):
        time.sleep(DELAY)
        return FAKE_SEGMENTS


@pytest.fixture
def slow_settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", device="cpu", workers=WORKERS)


def test_workers_process_jobs_in_parallel_not_serially(slow_settings, audio_file):
    app = create_app(slow_settings, transcriber_factory=lambda name: SlowTranscriber())
    with TestClient(app) as client:
        started = time.perf_counter()
        job_ids = [submit(client, audio_file, "text").json()["id"] for _ in range(WORKERS)]
        jobs = [wait_for(client, job_id, timeout=DELAY * WORKERS + 5) for job_id in job_ids]
        elapsed = time.perf_counter() - started

    assert all(job["status"] == "done" for job in jobs)
    # En série : WORKERS * DELAY. Avec WORKERS threads en parallèle : ~DELAY.
    # Seuil à 60 % du temps série : marge confortable pour l'overhead de test.
    assert elapsed < DELAY * WORKERS * 0.6, (
        f"{elapsed:.2f}s pour {WORKERS} jobs : le traitement semble sériel, "
        "pas réparti sur les threads du worker pool"
    )
