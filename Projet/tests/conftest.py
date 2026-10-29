import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from subtitler.api import create_app
from subtitler.config import Settings
from subtitler.transcription.base import Segment, Transcriber

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")

ADMIN = ("admin", "admin-password")
PASSWORD = "user-password"

FAKE_SEGMENTS = [
    Segment(0.0, 0.8, "Hello world."),
    Segment(0.8, 1.6, "Second sentence."),
]


class FakeTranscriber(Transcriber):
    """Remplace Whisper : réponse instantanée et sans GPU."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[Path] = []

    def transcribe(self, audio_path: Path) -> list[Segment]:
        self.calls.append(audio_path)
        if self.error:
            raise self.error
        return FAKE_SEGMENTS


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def video_file(media_dir) -> Path:
    path = media_dir / "clip.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    )
    return path


@pytest.fixture(scope="session")
def audio_file(media_dir) -> Path:
    path = media_dir / "voice.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(path))
    return path


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data", default_model="whisper-small.en", device="cpu",
        admin_username=ADMIN[0], admin_password=ADMIN[1],
    )


def login(client, username: str = "alice", password: str = PASSWORD) -> dict:
    """Connecte ``client`` (cookie de session), en créant le compte au besoin."""
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code == 401:
        response = client.post("/api/auth/register", json={"username": username, "password": password})
    response.raise_for_status()
    return response.json()


def login_admin(client) -> dict:
    return login(client, *ADMIN)


@pytest.fixture
def transcriber() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture
def client(settings, transcriber):
    app = create_app(settings, transcriber_factory=lambda name: transcriber)
    with TestClient(app) as test_client:
        login(test_client)
        yield test_client
