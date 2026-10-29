"""Exécution des jobs en arrière-plan, dans une file d'attente."""

import logging
import shutil
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from subtitler import media
from subtitler import subtitles
from subtitler.jobs.models import RESULT_FILENAMES, OutputKind
from subtitler.jobs.store import JobStore
from subtitler.transcription.base import Transcriber
from subtitler.transcription.diarization import Diarizer, assign_speakers

logger = logging.getLogger(__name__)



_NOBODY = object()  # aucun utilisateur ne peut passer pour l'instant


class JobCancelled(Exception):
    """Le job a été annulé pendant son traitement."""


def find_input(job_dir: Path) -> Path:
    return next(job_dir.glob("input.*"))


class FairQueue:
    """File d'attente qui fait passer les utilisateurs en parallèle, pas leurs fichiers.

    Un utilisateur n'a qu'un traitement actif à la fois : ses autres fichiers
    attendent que le précédent soit fini. Les workers libres servent donc
    d'autres utilisateurs, à tour de rôle : deux utilisateurs qui envoient un
    fichier en même temps sont traités en parallèle, même si l'un d'eux a
    déjà 5 fichiers en attente.
    """

    def __init__(self):
        self._jobs: dict[str | None, deque[str]] = {}  # jobs en attente, par utilisateur
        self._turns: deque[str | None] = deque()  # utilisateurs en attente, dans l'ordre de passage
        self._running: dict[str, str | None] = {}  # job en cours -> son utilisateur
        self._condition = threading.Condition()
        self._closed = False

    def put(self, job_id: str, user_id: str | None) -> None:
        with self._condition:
            if user_id not in self._jobs:
                self._jobs[user_id] = deque()
                self._turns.append(user_id)
            self._jobs[user_id].append(job_id)
            self._condition.notify_all()

    def _next_user(self) -> str | None:
        busy = set(self._running.values())
        return next((user for user in self._turns if user not in busy), _NOBODY)

    def get(self) -> str | None:
        """Prochain job à traiter, ou None une fois la file fermée.

        Appeler :meth:`done` une fois le job fini, pour que l'utilisateur
        puisse passer au suivant.
        """
        with self._condition:
            while not self._closed and (user_id := self._next_user()) is _NOBODY:
                self._condition.wait()
            if self._closed:
                return None
            self._turns.remove(user_id)
            jobs = self._jobs[user_id]
            job_id = jobs.popleft()
            if jobs:
                self._turns.append(user_id)  # repasse en fin de tour
            else:
                del self._jobs[user_id]
            self._running[job_id] = user_id
            return job_id

    def done(self, job_id: str) -> None:
        with self._condition:
            self._running.pop(job_id, None)
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class JobWorker:
    """Traite les jobs sur ``threads`` threads, un utilisateur par thread.

    Chaque thread traite un job à la fois ; le nombre de threads fixe donc le
    nombre d'utilisateurs servis simultanément (et d'exemplaires du modèle en
    mémoire GPU, voir :class:`~subtitler.transcription.whisper.WhisperTranscriber`).
    """

    def __init__(
        self,
        store: JobStore,
        jobs_dir: Path,
        get_transcriber: Callable[[str], Transcriber],
        threads: int = 1,
        diarizer: Diarizer | None = None,
    ):
        self.store = store
        self.jobs_dir = jobs_dir
        self.get_transcriber = get_transcriber
        self.thread_count = threads
        self.diarizer = diarizer
        self._queue = FairQueue()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        # Reprend les jobs interrompus par un arrêt ou un crash.
        for job_id in self.store.unfinished_ids():
            self.store.mark_pending(job_id)
            self._queue.put(job_id, self.store.get(job_id).user_id)
        for index in range(self.thread_count):
            thread = threading.Thread(target=self._loop, name=f"worker-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        # Les jobs en cours se terminent ; ceux en attente reprendront au redémarrage.
        self._queue.close()
        for thread in self._threads:
            thread.join()
        self._threads.clear()

    def submit(self, job_id: str, user_id: str | None = None) -> None:
        self._queue.put(job_id, user_id)

    def _loop(self) -> None:
        while (job_id := self._queue.get()) is not None:
            try:
                self.process(job_id)
            finally:
                self._queue.done(job_id)

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        # Un job annulé pendant son attente n'est pas démarré.
        if job is None or not self.store.mark_running(job_id):
            return
        started = time.perf_counter()
        try:
            text = self._run(job_id, job.output_kind, job.model)
        except JobCancelled:
            logger.info("Le job %s a été annulé", job_id)
            (self.jobs_dir / job_id / "audio.wav").unlink(missing_ok=True)
        except Exception as error:
            logger.exception("Le job %s a échoué", job_id)
            self.store.mark_failed(job_id, str(error) or type(error).__name__)
        else:
            self.store.mark_done(job_id, text, time.perf_counter() - started)

    def _check_cancelled(self, job_id: str) -> None:
        # Une étape en cours (transcription, ffmpeg) ne peut pas être
        # interrompue : l'annulation est prise en compte entre deux étapes.
        if self.store.is_cancelled(job_id):
            raise JobCancelled

    def _run(self, job_id: str, output_kind: OutputKind, model: str) -> str:
        job_dir = self.jobs_dir / job_id
        source = find_input(job_dir)
        audio = job_dir / "audio.wav"
        srt = job_dir / "subtitles.srt"
        result = job_dir / RESULT_FILENAMES[output_kind]

        media.extract_audio(source, audio)
        self._check_cancelled(job_id)
        segments = self.get_transcriber(model).transcribe(audio)
        self._check_cancelled(job_id)
        if self.diarizer is not None:
            segments = assign_speakers(segments, self.diarizer.diarize(audio))
            self._check_cancelled(job_id)
        text = subtitles.to_text(segments)
        srt.write_text(subtitles.to_srt(segments), encoding="utf-8", newline="")
        (job_dir / "subtitles.vtt").write_text(subtitles.to_vtt(segments), encoding="utf-8", newline="")

        if output_kind is OutputKind.VIDEO_EMBEDDED:
            media.burn_subtitles(source, srt, result)
        elif output_kind is OutputKind.VIDEO_TRACK:
            media.add_subtitle_track(source, srt, result)
        elif output_kind is OutputKind.SUBTITLES:
            shutil.copyfile(srt, result)
        else:
            result.write_text(text, encoding="utf-8", newline="")

        audio.unlink(missing_ok=True)
        return text
