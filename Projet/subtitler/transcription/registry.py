"""Catalogue des modèles de transcription disponibles.

Pour ajouter un modèle (data scientist) : écrire une sous-classe de
:class:`~subtitler.transcription.base.Transcriber` puis appeler
:func:`register` avec un nom, une fonction qui la construit et, pour
l'interface, un nom lisible, une description et les langues gérées.
"""

from collections.abc import Callable
from dataclasses import dataclass

from subtitler.config import Settings
from subtitler.transcription.base import Transcriber
from subtitler.transcription.whisper import WhisperTranscriber

TranscriberFactory = Callable[[Settings], Transcriber]

AUTO = "auto"  # détection automatique de la langue par le modèle

# Langues proposées dans l'interface (code ISO 639-1 -> nom affiché).
LANGUAGES: dict[str, str] = {
    AUTO: "Détection automatique",
    "fr": "Français",
    "en": "Anglais",
    "es": "Espagnol",
    "de": "Allemand",
    "it": "Italien",
    "pt": "Portugais",
    "nl": "Néerlandais",
    "ar": "Arabe",
    "zh": "Chinois",
    "ja": "Japonais",
}


@dataclass(frozen=True)
class ModelInfo:
    name: str
    label: str  # nom affiché à l'utilisateur
    description: str
    languages: tuple[str, ...] | None  # None : toutes les langues de LANGUAGES

    def supports(self, language: str) -> bool:
        # « auto » est toujours accepté : un modèle monolingue suppose sa langue.
        return language == AUTO or self.languages is None or language in self.languages


_factories: dict[str, TranscriberFactory] = {}
_infos: dict[str, ModelInfo] = {}


def register(
    name: str,
    factory: TranscriberFactory,
    label: str | None = None,
    description: str = "",
    languages: tuple[str, ...] | None = None,
) -> None:
    _factories[name] = factory
    _infos[name] = ModelInfo(name, label or name, description, languages)


def available_models() -> list[str]:
    return list(_factories)


def model_infos() -> list[ModelInfo]:
    """Modèles dans l'ordre d'enregistrement (du plus rapide au plus précis)."""
    return list(_infos.values())


def get_info(name: str) -> ModelInfo:
    try:
        return _infos[name]
    except KeyError:
        raise ValueError(f"Modèle inconnu : {name}") from None


def create(name: str, settings: Settings) -> Transcriber:
    try:
        factory = _factories[name]
    except KeyError:
        raise ValueError(f"Modèle inconnu : {name}") from None
    return factory(settings)


def _whisper(model_id: str) -> TranscriberFactory:
    # Un exemplaire du modèle par worker : les traitements simultanés ne s'attendent pas.
    return lambda settings: WhisperTranscriber(model_id, settings.device, replicas=settings.workers)


# Pour l'anglais, les variantes « .en » sont plus précises à taille égale ;
# les autres langues utilisent les variantes multilingues.
register(
    "whisper-small.en", _whisper("openai/whisper-small.en"), "Rapide",
    "Le plus rapide, idéal pour un premier jet. Anglais uniquement.", ("en",),
)
register(
    "whisper-small", _whisper("openai/whisper-small"), "Rapide",
    "Le plus rapide, idéal pour un premier jet.",
)
register(
    "whisper-medium.en", _whisper("openai/whisper-medium.en"), "Équilibré",
    "Bon compromis entre vitesse et précision. Anglais uniquement.", ("en",),
)
register(
    "whisper-medium", _whisper("openai/whisper-medium"), "Équilibré",
    "Bon compromis entre vitesse et précision.",
)
register(
    "whisper-large-v3-turbo", _whisper("openai/whisper-large-v3-turbo"), "Précis",
    "Le plus précis, notamment sur l'audio difficile (bruit, accents), mais plus lent.",
)
