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
    workers: int = 1
    max_upload_mb: int = 500

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
        )
