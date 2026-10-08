"""Opérations sur les fichiers audio/vidéo, via les exécutables ffmpeg et ffprobe."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(Exception):
    """Fichier illisible ou commande ffmpeg en échec."""


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=True,
        )
    except FileNotFoundError:
        raise MediaError(f"{args[0]} est introuvable : installez ffmpeg") from None
    except subprocess.CalledProcessError as error:
        last_lines = "\n".join(error.stderr.strip().splitlines()[-5:])
        raise MediaError(f"{args[0]} a échoué : {last_lines}") from None
    return completed.stdout


def probe(path: Path) -> MediaInfo:
    output = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    data = json.loads(output)
    # Les pochettes d'albums sont des flux vidéo « attached_pic » : on les ignore.
    kinds = {
        s["codec_type"] for s in data.get("streams", [])
        if not s.get("disposition", {}).get("attached_pic")
    }
    return MediaInfo(
        duration=float(data.get("format", {}).get("duration", 0.0)),
        has_video="video" in kinds,
        has_audio="audio" in kinds,
    )


def extract_audio(source: Path, destination: Path) -> None:
    """Extrait la piste audio en WAV mono 16 kHz, le format attendu par Whisper."""
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination),
    ])


def add_subtitle_track(video: Path, srt: Path, destination: Path, language: str = "eng") -> None:
    """Ajoute les sous-titres comme piste désactivable, sans réencoder la vidéo."""
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(srt),
        "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={language}", str(destination),
    ])


def burn_subtitles(video: Path, srt: Path, destination: Path) -> None:
    """Incruste les sous-titres dans l'image (réencodage de la vidéo)."""
    # Le filtre « subtitles » interprète mal les chemins Windows (C:\...),
    # on lance donc ffmpeg depuis le dossier du fichier SRT.
    _run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(video.resolve()),
            "-vf", f"subtitles={srt.name}", "-c:a", "copy", str(destination.resolve()),
        ],
        cwd=srt.parent,
    )
