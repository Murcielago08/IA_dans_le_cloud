"""Mise en forme des segments : SRT, WebVTT et texte brut."""

from subtitler.transcription.base import Segment


def format_timestamp(seconds: float, separator: str = ",") -> str:
    """Formate un temps en ``HH:MM:SS,mmm`` (SRT) ou ``HH:MM:SS.mmm`` (VTT)."""
    total_ms = round(max(seconds, 0.0) * 1000)
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{ms:03d}"


def _label(segment: Segment) -> str:
    """Préfixe le texte par le locuteur quand la diarization est activée."""
    return f"[{segment.speaker}] {segment.text}" if segment.speaker else segment.text


def to_srt(segments: list[Segment]) -> str:
    blocks = [
        f"{index}\n{format_timestamp(s.start)} --> {format_timestamp(s.end)}\n{_label(s)}\n"
        for index, s in enumerate(segments, start=1)
    ]
    return "\n".join(blocks)


def to_vtt(segments: list[Segment]) -> str:
    blocks = [
        f"{format_timestamp(s.start, '.')} --> {format_timestamp(s.end, '.')}\n{_label(s)}\n"
        for s in segments
    ]
    return "WEBVTT\n\n" + "\n".join(blocks)


def to_text(segments: list[Segment]) -> str:
    return " ".join(_label(s) for s in segments)
