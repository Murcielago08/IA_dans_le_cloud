import pytest

from subtitler.subtitles import format_timestamp, to_srt, to_text, to_vtt
from subtitler.transcription.base import Segment
from subtitler.transcription.whisper import chunks_to_segments


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00,000"),
        (3.96, "00:00:03,960"),
        (61.5, "00:01:01,500"),
        (3725.0004, "01:02:05,000"),
        (59.9996, "00:01:00,000"),  # l'arrondi des ms se reporte sur les secondes
        (-1, "00:00:00,000"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_srt_and_vtt_formats():
    segments = [Segment(0, 1.5, "Hello."), Segment(1.5, 3, "World.")]
    assert to_srt(segments) == (
        "1\n00:00:00,000 --> 00:00:01,500\nHello.\n\n"
        "2\n00:00:01,500 --> 00:00:03,000\nWorld.\n"
    )
    assert to_vtt(segments).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHello.\n")
    assert to_text(segments) == "Hello. World."


def test_speaker_label_is_added_when_present():
    segments = [Segment(0, 1.5, "Hello.", "SPEAKER_00"), Segment(1.5, 3, "World.", None)]
    assert to_text(segments) == "[SPEAKER_00] Hello. World."
    assert "[SPEAKER_00] Hello.\n" in to_srt(segments)


def test_chunks_keep_absolute_timestamps():
    chunks = [
        {"timestamp": (0.0, 4.0), "text": " First"},
        {"timestamp": (4.0, 29.0), "text": " Second"},
        {"timestamp": (31.0, 35.0), "text": " Third"},
    ]
    assert [(s.start, s.end) for s in chunks_to_segments(chunks)] == [(0, 4), (4, 29), (31, 35)]


def test_chunks_timestamps_reset_on_new_window():
    chunks = [
        {"timestamp": (0.0, 20.0), "text": " A"},
        {"timestamp": (20.0, 28.0), "text": " B"},
        {"timestamp": (0.0, 5.0), "text": " C"},  # horodatages repartis de zéro
    ]
    segments = chunks_to_segments(chunks)
    assert [s.text for s in segments] == ["A", "B", "C"]
    assert (segments[2].start, segments[2].end) == (28.0, 33.0)


def test_chunks_missing_end_and_empty_text():
    chunks = [
        {"timestamp": (0.0, 2.0), "text": "  "},
        {"timestamp": (2.0, None), "text": " Last"},
    ]
    assert chunks_to_segments(chunks) == [Segment(2.0, 4.0, "Last")]
