"""Transcription avec les modèles Whisper via Hugging Face transformers."""

import logging
import threading
from pathlib import Path

from subtitler.transcription.base import Segment, Transcriber

logger = logging.getLogger(__name__)


class WhisperTranscriber(Transcriber):
    """Transcripteur Whisper. Le modèle est chargé au premier appel."""

    def __init__(self, model_id: str, device: str = "cuda:0"):
        self.model_id = model_id
        self.device = device
        self._pipeline = None
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

    def warm_up(self) -> None:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = self._load()

    def transcribe(self, audio_path: Path) -> list[Segment]:
        self.warm_up()
        # Le GPU n'est pas partagé entre deux transcriptions simultanées.
        with self._lock:
            result = self._pipeline(str(audio_path), return_timestamps=True)
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
