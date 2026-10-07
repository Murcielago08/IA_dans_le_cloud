"""Application FastAPI : API REST + interface web."""

import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from subtitler import __version__, media, transcription
from subtitler.api.schemas import AppInfo, JobOut, Stats
from subtitler.config import Settings
from subtitler.jobs.models import (
    ALLOWED_OUTPUTS, RESULT_FILENAMES, InputKind, Job, JobStatus, OutputKind,
)
from subtitler.jobs.store import JobStore
from subtitler.jobs.worker import JobWorker
from subtitler.transcription.base import Transcriber

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
ACCEPTED_EXTENSIONS = {".mp4", ".wav"}
_COPY_CHUNK = 1024 * 1024


class _ModelCache:
    """Charge chaque modèle une seule fois et le garde en mémoire."""

    def __init__(self, factory: Callable[[str], Transcriber]):
        self._factory = factory
        self._models: dict[str, Transcriber] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> Transcriber:
        with self._lock:
            if name not in self._models:
                self._models[name] = self._factory(name)
            return self._models[name]


def create_app(
    settings: Settings | None = None,
    transcriber_factory: Callable[[str], Transcriber] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if transcriber_factory is None:
        def transcriber_factory(name: str) -> Transcriber:
            return transcription.create(name, settings)

    store = JobStore(settings.db_path)
    models = _ModelCache(transcriber_factory)
    worker = JobWorker(store, settings.jobs_dir, models.get, settings.workers)

    def warm_up_default_model() -> None:
        try:
            models.get(settings.default_model).warm_up()
        except Exception:
            logger.exception("Impossible de précharger le modèle %s", settings.default_model)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        # En arrière-plan : le serveur répond pendant le chargement du modèle.
        threading.Thread(target=warm_up_default_model, daemon=True).start()
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Subtitler", version=__version__, lifespan=lifespan)

    def get_job_or_404(job_id: str) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "Traitement introuvable")
        return job

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/info")
    def info() -> AppInfo:
        return AppInfo(
            models=transcription.available_models(),
            default_model=settings.default_model,
            allowed_outputs={kind: list(outputs) for kind, outputs in ALLOWED_OUTPUTS.items()},
            max_upload_mb=settings.max_upload_mb,
        )

    @app.post("/api/jobs", status_code=202)
    def create_job(
        file: UploadFile = File(...),
        output_kind: OutputKind = Form(...),
        model: str | None = Form(None),
    ) -> JobOut:
        model = model or settings.default_model
        if model not in transcription.available_models():
            raise HTTPException(400, f"Modèle inconnu : {model}")
        extension = Path(file.filename or "").suffix.lower()
        if extension not in ACCEPTED_EXTENSIONS:
            raise HTTPException(400, "Seuls les fichiers .mp4 et .wav sont acceptés")

        job_id = uuid.uuid4().hex
        job_dir = settings.jobs_dir / job_id
        job_dir.mkdir(parents=True)
        try:
            source = job_dir / f"input{extension}"
            _save_upload(file, source, settings.max_upload_mb * 1024 * 1024)
            try:
                info = media.probe(source)
            except media.MediaError:
                raise HTTPException(400, "Fichier illisible ou corrompu") from None
            if not info.has_audio:
                raise HTTPException(400, "Le fichier ne contient pas de piste audio")
            input_kind = InputKind.VIDEO if info.has_video else InputKind.AUDIO
            if output_kind not in ALLOWED_OUTPUTS[input_kind]:
                raise HTTPException(
                    400, f"Le résultat « {output_kind} » n'est pas possible pour un fichier audio",
                )
        except BaseException:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise

        job = Job(
            id=job_id,
            filename=Path(file.filename).name,
            input_kind=input_kind,
            output_kind=output_kind,
            model=model,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            media_duration=info.duration,
        )
        store.add(job)
        worker.submit(job_id)
        return JobOut.from_job(job)

    @app.get("/api/jobs")
    def list_jobs(
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    ) -> list[JobOut]:
        return [JobOut.from_job(job, include_text=True) for job in store.recent(limit, offset)]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> JobOut:
        return JobOut.from_job(get_job_or_404(job_id), include_text=True)

    def done_job_file(job_id: str, filename: str) -> tuple[Job, Path]:
        job = get_job_or_404(job_id)
        if job.status is not JobStatus.DONE:
            raise HTTPException(409, "Le traitement n'est pas terminé")
        path = settings.jobs_dir / job_id / filename
        if not path.is_file():
            raise HTTPException(404, "Résultat introuvable")
        return job, path

    @app.get("/api/jobs/{job_id}/result")
    def download_result(job_id: str, inline: bool = False) -> FileResponse:
        job = get_job_or_404(job_id)
        _, path = done_job_file(job_id, RESULT_FILENAMES[job.output_kind])
        download_name = f"{Path(job.filename).stem}_{job.output_kind}{path.suffix}"
        return FileResponse(
            path,
            filename=download_name,
            content_disposition_type="inline" if inline else "attachment",
        )

    @app.get("/api/jobs/{job_id}/subtitles.vtt")
    def subtitles_vtt(job_id: str) -> FileResponse:
        _, path = done_job_file(job_id, "subtitles.vtt")
        return FileResponse(path, media_type="text/vtt")

    @app.get("/api/stats")
    def stats() -> Stats:
        return Stats(**store.stats())

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    written = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(_COPY_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(413, f"Fichier trop volumineux (max {max_bytes // 2**20} Mo)")
            output.write(chunk)
