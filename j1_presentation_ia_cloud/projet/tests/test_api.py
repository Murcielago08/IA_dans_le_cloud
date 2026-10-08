import time

import pytest
from fastapi.testclient import TestClient

from subtitler import media
from subtitler.api import create_app
from tests.conftest import FakeTranscriber, requires_ffmpeg

pytestmark = requires_ffmpeg


def submit(client, path, output_kind, filename=None):
    with path.open("rb") as file:
        return client.post(
            "/api/jobs",
            files={"file": (filename or path.name, file)},
            data={"output_kind": output_kind},
        )


def wait_for(client, job_id, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("le traitement ne s'est pas terminé à temps")


def test_health_and_info(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    info = client.get("/api/info").json()
    assert "whisper-medium.en" in info["models"]
    assert info["allowed_outputs"]["audio"] == ["subtitles", "text"]


def test_web_interface_is_served(client):
    assert "Subtitler" in client.get("/").text
    assert client.get("/admin.html").status_code == 200


def test_text_from_audio(client, audio_file):
    response = submit(client, audio_file, "text")
    assert response.status_code == 202
    created = response.json()
    assert created["input_kind"] == "audio"
    assert created["media_duration"] == pytest.approx(2.0, abs=0.1)

    job = wait_for(client, created["id"])
    assert job["status"] == "done"
    assert job["text"] == "Hello world. Second sentence."

    result = client.get(f"/api/jobs/{job['id']}/result")
    assert result.text == "Hello world. Second sentence."
    assert "attachment" in result.headers["content-disposition"]
    assert "voice_text.txt" in result.headers["content-disposition"]


def test_subtitles_from_video(client, video_file):
    job = wait_for(client, submit(client, video_file, "subtitles").json()["id"])
    result = client.get(f"/api/jobs/{job['id']}/result?inline=true")
    assert result.text.startswith("1\n00:00:00,000 --> 00:00:00,800\nHello world.\n")
    assert "inline" in result.headers["content-disposition"]
    vtt = client.get(f"/api/jobs/{job['id']}/subtitles.vtt")
    assert vtt.text.startswith("WEBVTT")


def test_video_with_subtitle_track(client, video_file, tmp_path):
    job = wait_for(client, submit(client, video_file, "video_track").json()["id"])
    assert job["status"] == "done", job["error"]
    output = tmp_path / "out.mp4"
    output.write_bytes(client.get(f"/api/jobs/{job['id']}/result").content)
    probe = media.probe(output)
    assert probe.has_video and probe.has_audio


def test_video_with_embedded_subtitles(client, video_file, tmp_path):
    job = wait_for(client, submit(client, video_file, "video_embedded").json()["id"])
    assert job["status"] == "done", job["error"]
    output = tmp_path / "out.mp4"
    output.write_bytes(client.get(f"/api/jobs/{job['id']}/result").content)
    assert media.probe(output).has_video


@pytest.mark.parametrize(
    ("fixture", "filename", "output_kind", "message"),
    [
        ("audio_file", None, "video_embedded", "n'est pas possible pour un fichier audio"),
        ("audio_file", "voice.mp3", "text", "Seuls les fichiers .mp4 et .wav"),
    ],
)
def test_rejected_uploads(client, request, fixture, filename, output_kind, message):
    response = submit(client, request.getfixturevalue(fixture), output_kind, filename)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_corrupted_file_is_rejected(client, tmp_path):
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video")
    response = submit(client, fake, "text")
    assert response.status_code == 400
    assert client.get("/api/stats").json()["total_jobs"] == 0


def test_unknown_model_is_rejected(client, audio_file):
    with audio_file.open("rb") as file:
        response = client.post(
            "/api/jobs", files={"file": ("a.wav", file)},
            data={"output_kind": "text", "model": "nope"},
        )
    assert response.status_code == 400


def test_failed_job_is_reported(settings, audio_file):
    failing = FakeTranscriber(error=RuntimeError("CUDA out of memory"))
    with TestClient(create_app(settings, transcriber_factory=lambda name: failing)) as client:
        job = wait_for(client, submit(client, audio_file, "text").json()["id"])
        assert job["status"] == "failed"
        assert job["error"] == "CUDA out of memory"
        assert client.get(f"/api/jobs/{job['id']}/result").status_code == 409
        stats = client.get("/api/stats").json()
        assert stats["failed"]["by_kind"]["text"] == 1


def test_unknown_job(client):
    assert client.get("/api/jobs/unknown").status_code == 404
    assert client.get("/api/jobs/unknown/result").status_code == 404


def test_stats_after_jobs(client, audio_file):
    for kind in ("text", "subtitles"):
        wait_for(client, submit(client, audio_file, kind).json()["id"])
    stats = client.get("/api/stats").json()
    assert stats["inferences"]["total"] == 2
    assert stats["inferences"]["by_kind"]["text"] == 1
    assert stats["unfinished"]["total"] == 0
    assert stats["avg_realtime_ratio"] < 1
    assert len(client.get("/api/jobs").json()) == 2


def test_unfinished_jobs_resume_after_restart(settings, audio_file, transcriber):
    # Sans « with », le lifespan ne s'exécute pas : aucun worker, comme après un crash.
    client = TestClient(create_app(settings, transcriber_factory=lambda name: transcriber))
    job_id = submit(client, audio_file, "text").json()["id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "pending"

    # Redémarrage : le job est repris automatiquement.
    with TestClient(create_app(settings, transcriber_factory=lambda name: transcriber)) as client:
        assert wait_for(client, job_id)["status"] == "done"
