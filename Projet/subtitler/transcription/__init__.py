"""Modèles de transcription audio vers texte."""

from subtitler.transcription.base import Segment, Transcriber
from subtitler.transcription.registry import (
    AUTO, LANGUAGES, ModelInfo, available_models, create, get_info, model_infos, register,
)

__all__ = [
    "AUTO", "LANGUAGES", "ModelInfo", "Segment", "Transcriber",
    "available_models", "create", "get_info", "model_infos", "register",
]
