"""Modèle de données d'un traitement (job)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InputKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


class OutputKind(StrEnum):
    VIDEO_EMBEDDED = "video_embedded"  # sous-titres incrustés dans l'image
    VIDEO_TRACK = "video_track"  # sous-titres en piste dans les métadonnées
    SUBTITLES = "subtitles"  # fichier .srt seul
    TEXT = "text"  # texte sans horodatage


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


ALLOWED_OUTPUTS: dict[InputKind, tuple[OutputKind, ...]] = {
    InputKind.VIDEO: tuple(OutputKind),
    InputKind.AUDIO: (OutputKind.SUBTITLES, OutputKind.TEXT),
}

RESULT_FILENAMES: dict[OutputKind, str] = {
    OutputKind.VIDEO_EMBEDDED: "result.mp4",
    OutputKind.VIDEO_TRACK: "result.mp4",
    OutputKind.SUBTITLES: "result.srt",
    OutputKind.TEXT: "result.txt",
}


@dataclass
class Job:
    id: str
    filename: str
    input_kind: InputKind
    output_kind: OutputKind
    model: str
    status: JobStatus
    created_at: datetime
    media_duration: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    processing_time: float | None = None
    text: str | None = None
    error: str | None = None
