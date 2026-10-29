"""Configuration de l'application, lue depuis les variables d'environnement."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Paramètres de l'application.

    Chaque champ peut être surchargé par une variable d'environnement
    préfixée par ``SUBTITLER_`` (ex : ``SUBTITLER_DATA_DIR``).
    """

    data_dir: Path = Path("data")
    default_model: str = "whisper-medium.en"
    device: str = "cuda:0"
    workers: int = 2
    max_upload_mb: int = 500
    max_jobs_per_user: int = 5
    enable_speakers: bool = False
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    hf_token: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None
    allow_signup: bool = True
    session_days: int = 7

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "subtitler.db"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            data_dir=Path(env.get("SUBTITLER_DATA_DIR", cls.data_dir)),
            default_model=env.get("SUBTITLER_DEFAULT_MODEL", cls.default_model),
            device=env.get("SUBTITLER_DEVICE", cls.device),
            workers=int(env.get("SUBTITLER_WORKERS", cls.workers)),
            max_upload_mb=int(env.get("SUBTITLER_MAX_UPLOAD_MB", cls.max_upload_mb)),
            max_jobs_per_user=int(env.get("SUBTITLER_MAX_JOBS_PER_USER", cls.max_jobs_per_user)),
            enable_speakers=env.get("SUBTITLER_ENABLE_SPEAKERS", "").lower() in ("1", "true", "yes"),
            diarization_model=env.get("SUBTITLER_DIARIZATION_MODEL", cls.diarization_model),
            hf_token=env.get("SUBTITLER_HF_TOKEN", cls.hf_token),
            admin_username=env.get("SUBTITLER_ADMIN_USERNAME", cls.admin_username),
            admin_password=env.get("SUBTITLER_ADMIN_PASSWORD", cls.admin_password),
            allow_signup=env.get("SUBTITLER_ALLOW_SIGNUP", "true").lower() in ("1", "true", "yes"),
            session_days=int(env.get("SUBTITLER_SESSION_DAYS", cls.session_days)),
        )
