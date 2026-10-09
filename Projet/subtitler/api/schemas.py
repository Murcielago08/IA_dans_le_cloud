"""Objets renvoyés par l'API."""

from datetime import datetime

from pydantic import BaseModel

from subtitler.jobs.models import InputKind, Job, JobStatus, OutputKind


class JobOut(BaseModel):
    id: str
    filename: str
    input_kind: InputKind
    output_kind: OutputKind
    model: str
    status: JobStatus
    created_at: datetime
    media_duration: float | None
    started_at: datetime | None
    finished_at: datetime | None
    processing_time: float | None
    error: str | None
    text: str | None = None

    @classmethod
    def from_job(cls, job: Job, include_text: bool = False) -> "JobOut":
        fields = {name: getattr(job, name) for name in cls.model_fields if name != "text"}
        return cls(**fields, text=job.text if include_text else None)


class AppInfo(BaseModel):
    models: list[str]
    default_model: str
    allowed_outputs: dict[InputKind, list[OutputKind]]
    max_upload_mb: int
    speakers_enabled: bool


class KindCounts(BaseModel):
    total: int
    by_kind: dict[OutputKind, int]


class Stats(BaseModel):
    total_jobs: int
    inferences: KindCounts
    unfinished: KindCounts
    failed: KindCounts
    avg_processing_time: float | None
    avg_realtime_ratio: float | None
