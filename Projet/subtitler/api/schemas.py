"""Objets renvoyés par l'API."""

from datetime import datetime

from pydantic import BaseModel

from subtitler.jobs.models import InputKind, Job, JobStatus, OutputKind
from subtitler.users import User


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
    consent: bool
    consent_at: datetime | None
    hidden_at: datetime | None
    username: str | None = None  # propriétaire ; None pour les jobs créés avant les comptes
    text: str | None = None

    @classmethod
    def from_job(cls, job: Job, include_text: bool = False, username: str | None = None) -> "JobOut":
        fields = {name: getattr(job, name) for name in cls.model_fields if name not in ("text", "username")}
        return cls(**fields, username=username, text=job.text if include_text else None)


class Credentials(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    is_admin: bool

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(id=user.id, username=user.username, is_admin=user.is_admin)


class LoginOut(BaseModel):
    user: UserOut
    token: str  # pour les clients API (en-tête « Authorization: Bearer ») ; le navigateur utilise le cookie


class AppInfo(BaseModel):
    models: list[str]
    default_model: str
    allowed_outputs: dict[InputKind, list[OutputKind]]
    max_upload_mb: int
    max_jobs_per_user: int
    speakers_enabled: bool
    signup_enabled: bool


class KindCounts(BaseModel):
    total: int
    by_kind: dict[OutputKind, int]


class Stats(BaseModel):
    total_jobs: int
    inferences: KindCounts
    unfinished: KindCounts
    failed: KindCounts
    cancelled: KindCounts
    avg_processing_time: float | None
    avg_realtime_ratio: float | None
