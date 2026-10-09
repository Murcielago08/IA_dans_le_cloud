"""Identification du locuteur (diarization) : qui parle, et quand.

La diarization est indépendante de la transcription : un modèle dédié détecte
les tours de parole à partir du signal audio (sans connaître le texte), on
recoupe ensuite ces tours avec les segments transcrits par Whisper en
choisissant, pour chaque segment, le locuteur dont le tour de parole recouvre
le plus sa période.
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from subtitler.transcription.base import Segment


@dataclass(frozen=True)
class SpeakerTurn:
    """Un tour de parole détecté dans l'audio, sans contenu textuel."""

    start: float
    end: float
    speaker: str


class Diarizer(ABC):
    """Détecte qui parle quand. Voir :mod:`subtitler.transcription.registry`
    pour le mécanisme équivalent côté transcription."""

    @abstractmethod
    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        """Renvoie les tours de parole détectés dans un fichier audio WAV."""

    def warm_up(self) -> None:
        """Charge le modèle à l'avance pour que le premier job ne l'attende pas."""


def assign_speakers(segments: list[Segment], turns: list[SpeakerTurn]) -> list[Segment]:
    """Attribue à chaque segment transcrit le locuteur le plus probable.

    Pour un segment donné, on retient le tour de parole qui chevauche le plus
    sa période ``[start, end]``. Sans chevauchement (silence mal détecté en
    bord de segment) ou sans tour fourni, le segment reste sans locuteur.
    """
    if not turns:
        return segments
    result = []
    for segment in segments:
        best = max(turns, key=lambda turn: _overlap(segment, turn))
        speaker = best.speaker if _overlap(segment, best) > 0 else None
        result.append(Segment(segment.start, segment.end, segment.text, speaker))
    return result


def _overlap(segment: Segment, turn: SpeakerTurn) -> float:
    return max(0.0, min(segment.end, turn.end) - max(segment.start, turn.start))


class PyannoteDiarizer(Diarizer):
    """Diarization via le pipeline pré-entraîné ``pyannote.audio``.

    Le modèle est soumis à conditions d'usage sur Hugging Face (gratuit, mais
    nécessite d'accepter les conditions puis de fournir un jeton d'accès via
    ``SUBTITLER_HF_TOKEN``). Comme pour Whisper, il est chargé au premier
    appel pour ne pas ralentir le démarrage quand la fonctionnalité est
    désactivée.
    """

    def __init__(self, model_id: str, device: str = "cuda:0", auth_token: str | None = None):
        self.model_id = model_id
        self.device = device
        self.auth_token = auth_token
        self._pipeline = None
        self._lock = threading.Lock()

    def _load(self):
        # Imports locaux : pyannote/torch sont lourds et inutiles tant que la
        # fonctionnalité est désactivée (comportement par défaut).
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(self.model_id, use_auth_token=self.auth_token)
        if self.device.startswith("cuda") and torch.cuda.is_available():
            pipeline.to(torch.device(self.device))
        return pipeline

    def warm_up(self) -> None:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = self._load()

    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        self.warm_up()
        # Comme le GPU Whisper, le GPU de diarization n'est pas partagé
        # entre deux traitements simultanés.
        with self._lock:
            annotation = self._pipeline(str(audio_path))
        return [
            SpeakerTurn(start=turn.start, end=turn.end, speaker=label)
            for turn, _, label in annotation.itertracks(yield_label=True)
        ]
