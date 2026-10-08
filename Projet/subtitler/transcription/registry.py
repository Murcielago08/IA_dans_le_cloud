"""Catalogue des modèles de transcription disponibles.

Pour ajouter un modèle (data scientist) : écrire une sous-classe de
:class:`~subtitler.transcription.base.Transcriber` puis appeler
:func:`register` avec un nom et une fonction qui la construit.
"""

from collections.abc import Callable

from subtitler.config import Settings
from subtitler.transcription.base import Transcriber
from subtitler.transcription.whisper import WhisperTranscriber

TranscriberFactory = Callable[[Settings], Transcriber]

_factories: dict[str, TranscriberFactory] = {}


def register(name: str, factory: TranscriberFactory) -> None:
    _factories[name] = factory


def available_models() -> list[str]:
    return sorted(_factories)


def create(name: str, settings: Settings) -> Transcriber:
    try:
        factory = _factories[name]
    except KeyError:
        raise ValueError(f"Modèle inconnu : {name}") from None
    return factory(settings)


def _whisper(model_id: str) -> TranscriberFactory:
    return lambda settings: WhisperTranscriber(model_id, settings.device)


register("whisper-small.en", _whisper("openai/whisper-small.en"))
register("whisper-medium.en", _whisper("openai/whisper-medium.en"))
register("whisper-large-v3-turbo", _whisper("openai/whisper-large-v3-turbo"))
