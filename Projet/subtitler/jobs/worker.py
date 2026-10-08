"""Exécution des jobs en arrière-plan, dans une file d'attente."""

import logging
import queue
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

from subtitler import media
from subtitler import subtitles
from subtitler.jobs.models import RESULT_FILENAMES, OutputKind
from subtitler.jobs.store import JobStore
from subtitler.transcription.base import Transcriber

logger = logging.getLogger(__name__)

_STOP = object()


def find_input(job_dir: Path) -> Path:
    return next(job_dir.glob("input.*"))


class JobWorker:
    """Traite les jobs un par un (par thread) dans l'ordre d'arrivée.

    Avec un seul GPU, un seul thread suffit : les demandes simultanées
    attendent leur tour dans la file au lieu de saturer la mémoire du GPU.
    """

    def __init__(
        self,
        store: JobStore,
        jobs_dir: Path,
        get_transcriber: Callable[[str], Transcriber],
        threads: int = 1,
    ):
        self.store = store
        self.jobs_dir = jobs_dir
        self.get_transcriber = get_transcriber
        self.thread_count = threads
        self._queue: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        # Reprend les jobs interrompus par un arrêt ou un crash.
        for job_id in self.store.unfinished_ids():
            self.store.mark_pending(job_id)
            self._queue.put(job_id)
        for index in range(self.thread_count):
            thread = threading.Thread(target=self._loop, name=f"worker-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        for _ in self._threads:
            self._queue.put(_STOP)
        for thread in self._threads:
            thread.join()
        self._threads.clear()

    def submit(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _loop(self) -> None:
        while (job_id := self._queue.get()) is not _STOP:
            self.process(job_id)

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        self.store.mark_running(job_id)
        started = time.perf_counter()
        try:
            text = self._run(job_id, job.output_kind, job.model)
        except Exception as error:
            logger.exception("Le job %s a échoué", job_id)
            self.store.mark_failed(job_id, str(error) or type(error).__name__)
        else:
            self.store.mark_done(job_id, text, time.perf_counter() - started)

    def _run(self, job_id: str, output_kind: OutputKind, model: str) -> str:
        job_dir = self.jobs_dir / job_id
        source = find_input(job_dir)
        audio = job_dir / "audio.wav"
        srt = job_dir / "subtitles.srt"
        result = job_dir / RESULT_FILENAMES[output_kind]

        media.extract_audio(source, audio)
        segments = self.get_transcriber(model).transcribe(audio)
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
