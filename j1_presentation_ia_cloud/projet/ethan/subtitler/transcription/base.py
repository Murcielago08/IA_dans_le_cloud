"""Interface commune à tous les modèles de transcription."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    """Un morceau de transcription horodaté (en secondes)."""

    start: float
    end: float
    text: str


class Transcriber(ABC):
    """Un modèle capable de transformer un fichier audio en segments horodatés.

    Pour ajouter un modèle, il suffit d'hériter de cette classe et de
    l'enregistrer dans :mod:`subtitler.transcription.registry`.
    """

    @abstractmethod
    def transcribe(self, audio_path: Path) -> list[Segment]:
        """Transcrit un fichier audio WAV mono 16 kHz."""

    def warm_up(self) -> None:
        """Charge le modèle à l'avance pour que la première demande ne l'attende pas."""
