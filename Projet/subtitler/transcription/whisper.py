"""Transcription avec les modèles Whisper via Hugging Face transformers."""

import logging
import queue
import threading
from pathlib import Path

from subtitler.transcription.base import Segment, Transcriber

logger = logging.getLogger(__name__)


class WhisperTranscriber(Transcriber):
    """Transcripteur Whisper. Le modèle est chargé au premier appel.

    Un exemplaire du modèle ne traite qu'un fichier à la fois : pour
    transcrire ``replicas`` fichiers en même temps, jusqu'à ``replicas``
    exemplaires sont chargés (à la demande), chacun occupant sa propre
    mémoire GPU (~1,5 Go pour medium en float16).
    """

    def __init__(self, model_id: str, device: str = "cuda:0", replicas: int = 1):
        self.model_id = model_id
        self.device = device
        self.replicas = max(1, replicas)
        self._free: queue.Queue = queue.Queue()  # exemplaires chargés et inoccupés
        self._loaded = 0
        self._lock = threading.Lock()

    def _load(self):
        # Imports locaux : torch/transformers sont lourds et inutiles
        # tant qu'aucune transcription n'est demandée (ex : tests de l'API).
        import torch
        from transformers import pipeline

        use_gpu = self.device.startswith("cuda") and torch.cuda.is_available()
        if not use_gpu:
            logger.warning("GPU indisponible, Whisper tourne sur CPU (lent)")
        logger.info("Chargement du modèle %s", self.model_id)
        return pipeline(
            "automatic-speech-recognition",
            model=self.model_id,
            dtype=torch.float16 if use_gpu else torch.float32,
            device=self.device if use_gpu else "cpu",
        )

    def _acquire(self):
        """Réserve un exemplaire libre, en charge un nouveau ou attend qu'un se libère."""
        with self._lock:
            try:
                return self._free.get_nowait()
            except queue.Empty:
                load_new = self._loaded < self.replicas
                if load_new:
                    self._loaded += 1
        if not load_new:
            return self._free.get()
        try:
            return self._load()
        except BaseException:
            with self._lock:
                self._loaded -= 1
            raise

    def warm_up(self) -> None:
        if self._loaded == 0:
            self._free.put(self._acquire())

    def transcribe(self, audio_path: Path) -> list[Segment]:
        pipeline = self._acquire()
        try:
            result = pipeline(str(audio_path), return_timestamps=True)
        finally:
            self._free.put(pipeline)
        return chunks_to_segments(result.get("chunks", []))


def chunks_to_segments(chunks: list[dict]) -> list[Segment]:
    """Convertit la sortie du pipeline en segments aux horodatages croissants.

    Selon les versions de transformers, les horodatages peuvent repartir de
    zéro à chaque fenêtre de 30 s, et le dernier morceau peut ne pas avoir
    de fin. Contrairement au prototype, aucun texte n'est jamais ignoré.
    """
    segments: list[Segment] = []
    offset = 0.0
    previous_end = 0.0
    for chunk in chunks:
        text = chunk["text"].strip()
        if not text:
            continue
        raw_start, raw_end = chunk["timestamp"]
        raw_start = raw_start or 0.0
        start = raw_start + offset
        if start < previous_end - 1.0:
            # Les horodatages sont repartis de zéro : nouvelle fenêtre.
            offset = previous_end - raw_start
            start = previous_end
        end = raw_end + offset if raw_end is not None else start + 2.0
        end = max(end, start)
        segments.append(Segment(start=start, end=end, text=text))
        previous_end = end
    return segments
