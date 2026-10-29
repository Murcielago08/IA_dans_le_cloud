"""Application FastAPI : API REST + interface web."""

import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from subtitler import __version__, media
from subtitler import transcription
from subtitler.api.schemas import AppInfo, Credentials, JobOut, LoginOut, Stats, UserOut
from subtitler.config import Settings
from subtitler.jobs.models import (
    ALLOWED_OUTPUTS, RESULT_FILENAMES, InputKind, Job, JobStatus, OutputKind,
)
from subtitler.jobs.store import JobStore
from subtitler.jobs.worker import JobWorker
from subtitler.transcription.base import Transcriber
from subtitler.transcription.diarization import PyannoteDiarizer
from subtitler.users import User, UserError, UserStore

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
ACCEPTED_EXTENSIONS = {".mp4", ".wav"}
_COPY_CHUNK = 1024 * 1024
SESSION_COOKIE = "subtitler_session"


class _WebFiles(StaticFiles):
    """Fichiers de l'interface, que le navigateur revalide à chaque chargement.

    Sans ``Cache-Control``, le navigateur peut garder une ancienne version
    d'un script après une mise à jour (ex : nouveau HTML avec ancien JS). Avec
    ``no-cache``, il redemande le fichier à chaque fois mais le serveur répond
    « 304 inchangé » (via l'ETag) tant qu'il n'a pas changé : peu coûteux.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


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
    users = UserStore(settings.db_path, timedelta(days=settings.session_days))
    if settings.admin_username and settings.admin_password:
        users.ensure_admin(settings.admin_username, settings.admin_password)
    elif settings.admin_username:
        logger.warning("SUBTITLER_ADMIN_PASSWORD absent : compte administrateur non créé")
    models = _ModelCache(transcriber_factory)
    diarizer = (
        PyannoteDiarizer(settings.diarization_model, settings.device, settings.hf_token)
        if settings.enable_speakers
        else None
    )
    # Rend atomiques la vérification de la limite par utilisateur et l'ajout du job.
    submit_lock = threading.Lock()
    worker = JobWorker(store, settings.jobs_dir, models.get, settings.workers, diarizer)

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

    def current_user(request: Request) -> User:
        # En-tête Bearer pour les clients API, cookie pour le navigateur.
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
        else:
            token = request.cookies.get(SESSION_COOKIE)
        user = users.user_for_token(token) if token else None
        if user is None:
            raise HTTPException(401, "Connexion requise")
        return user

    def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
        if not user.is_admin:
            raise HTTPException(403, "Réservé à l'administrateur")
        return user

    CurrentUser = Annotated[User, Depends(current_user)]
    AdminUser = Annotated[User, Depends(admin_user)]

    def get_job_or_404(job_id: str, user: User) -> Job:
        job = store.get(job_id)
        # Le job d'un autre utilisateur, ou qu'il a supprimé, est traité comme inexistant.
        if job is None or (not user.is_admin and (job.user_id != user.id or job.hidden_at)):
            raise HTTPException(404, "Traitement introuvable")
        return job

    def open_session(user: User, response: Response) -> LoginOut:
        token = users.open_session(user)
        response.set_cookie(
            SESSION_COOKIE, token, max_age=settings.session_days * 86400,
            httponly=True, samesite="lax",
        )
        return LoginOut(user=UserOut.from_user(user), token=token)

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
            max_jobs_per_user=settings.max_jobs_per_user,
            speakers_enabled=settings.enable_speakers,
            signup_enabled=settings.allow_signup,
        )

    @app.post("/api/auth/register", status_code=201)
    def register(credentials: Credentials, response: Response) -> LoginOut:
        if not settings.allow_signup:
            raise HTTPException(403, "La création de compte est désactivée")
        try:
            user = users.create(credentials.username, credentials.password)
        except UserError as error:
            raise HTTPException(400, str(error)) from None
        return open_session(user, response)

    @app.post("/api/auth/login")
    def login(credentials: Credentials, response: Response) -> LoginOut:
        user = users.authenticate(credentials.username, credentials.password)
        if user is None:
            raise HTTPException(401, "Identifiant ou mot de passe incorrect")
        return open_session(user, response)

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        if token := request.cookies.get(SESSION_COOKIE):
            users.close_session(token)
        response.delete_cookie(SESSION_COOKIE)

    @app.get("/api/auth/me")
    def me(user: CurrentUser) -> UserOut:
        return UserOut.from_user(user)

    def check_job_limit(user: User) -> None:
        if store.count_unfinished(user.id) >= settings.max_jobs_per_user:
            raise HTTPException(
                429,
                f"Vous avez déjà {settings.max_jobs_per_user} traitements en cours : "
                "attendez qu'un traitement se termine avant d'en lancer un autre",
            )

    @app.post("/api/jobs", status_code=202)
    def create_job(
        user: CurrentUser,
        file: UploadFile = File(...),
        output_kind: OutputKind = Form(...),
        model: str | None = Form(None),
        consent: bool = Form(False),
    ) -> JobOut:
        model = model or settings.default_model
        if model not in transcription.available_models():
            raise HTTPException(400, f"Modèle inconnu : {model}")
        extension = Path(file.filename or "").suffix.lower()
        if extension not in ACCEPTED_EXTENSIONS:
            raise HTTPException(400, "Seuls les fichiers .mp4 et .wav sont acceptés")
        # Refus immédiat, avant d'enregistrer un fichier potentiellement lourd.
        check_job_limit(user)

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
            user_id=user.id,
            consent=consent,
            consent_at=datetime.now(timezone.utc) if consent else None,
        )
        with submit_lock:
            # Seconde vérification : des envois parallèles du même utilisateur ont
            # pu passer la première pendant l'enregistrement de celui-ci.
            try:
                check_job_limit(user)
            except HTTPException:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise
            store.add(job)
        worker.submit(job_id, user.id)
        return JobOut.from_job(job, username=user.username)

    @app.get("/api/jobs")
    def list_jobs(
        user: CurrentUser,
        response: Response,
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
        all_users: bool = Query(False, alias="all"),
    ) -> list[JobOut]:
        """Traitements de l'utilisateur connecté (``?all=true`` : tous, administrateur seulement).

        Le nombre total, pour paginer avec ``limit``/``offset``, est dans l'en-tête ``X-Total-Count``.
        """
        if all_users and not user.is_admin:
            raise HTTPException(403, "Réservé à l'administrateur")
        owner = None if all_users else user.id
        jobs = store.recent(limit, offset, owner)
        response.headers["X-Total-Count"] = str(store.count(owner))
        names = users.usernames({job.user_id for job in jobs if job.user_id})
        return [JobOut.from_job(job, include_text=True, username=names.get(job.user_id)) for job in jobs]

    @app.delete("/api/jobs", status_code=204)
    def hide_all_jobs(user: CurrentUser) -> None:
        """Vide l'historique de l'utilisateur ; les fichiers restent conservés."""
        store.hide_all(user.id)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def hide_job(job_id: str, user: CurrentUser) -> None:
        """Retire le traitement de l'historique ; les fichiers restent conservés."""
        job = get_job_or_404(job_id, user)
        if job.user_id != user.id:
            raise HTTPException(403, "Seul le propriétaire peut retirer ce traitement de son historique")
        store.hide(job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, user: CurrentUser) -> JobOut:
        """Annule un traitement en attente ou en cours (propriétaire ou administrateur)."""
        job = get_job_or_404(job_id, user)
        if not store.cancel(job_id):
            raise HTTPException(409, "Le traitement est déjà terminé")
        names = users.usernames({job.user_id} if job.user_id else set())
        return JobOut.from_job(store.get(job_id), include_text=True, username=names.get(job.user_id))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, user: CurrentUser) -> JobOut:
        job = get_job_or_404(job_id, user)
        names = users.usernames({job.user_id} if job.user_id else set())
        return JobOut.from_job(job, include_text=True, username=names.get(job.user_id))

    def done_job_file(job: Job, filename: str) -> Path:
        if job.status is not JobStatus.DONE:
            raise HTTPException(409, "Le traitement n'est pas terminé")
        path = settings.jobs_dir / job.id / filename
        if not path.is_file():
            raise HTTPException(404, "Résultat introuvable")
        return path

    @app.get("/api/jobs/{job_id}/result")
    def download_result(job_id: str, user: CurrentUser, inline: bool = False) -> FileResponse:
        job = get_job_or_404(job_id, user)
        path = done_job_file(job, RESULT_FILENAMES[job.output_kind])
        download_name = f"{Path(job.filename).stem}_{job.output_kind}{path.suffix}"
        return FileResponse(
            path,
            filename=download_name,
            content_disposition_type="inline" if inline else "attachment",
        )

    @app.get("/api/jobs/{job_id}/subtitles.vtt")
    def subtitles_vtt(job_id: str, user: CurrentUser) -> FileResponse:
        path = done_job_file(get_job_or_404(job_id, user), "subtitles.vtt")
        return FileResponse(path, media_type="text/vtt")

    @app.get("/api/stats")
    def stats(_: AdminUser) -> Stats:
        return Stats(**store.stats())

    app.mount("/", _WebFiles(directory=WEB_DIR, html=True), name="web")
    return app


def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    written = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(_COPY_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(413, f"Fichier trop volumineux (max {max_bytes // 2**20} Mo)")
            output.write(chunk)
