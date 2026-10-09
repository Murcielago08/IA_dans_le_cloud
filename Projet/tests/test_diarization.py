from subtitler.transcription.base import Segment
from subtitler.transcription.diarization import SpeakerTurn, assign_speakers


def test_assign_speakers_picks_most_overlapping_turn():
    segments = [Segment(0, 2, "Bonjour"), Segment(2, 5, "Comment allez-vous")]
    turns = [SpeakerTurn(0, 2.2, "SPEAKER_00"), SpeakerTurn(2.2, 6, "SPEAKER_01")]

    result = assign_speakers(segments, turns)

    assert [s.speaker for s in result] == ["SPEAKER_00", "SPEAKER_01"]
    # le texte et les horodatages ne sont pas modifiés, seul le locuteur est ajouté
    assert [(s.start, s.end, s.text) for s in result] == [(0, 2, "Bonjour"), (2, 5, "Comment allez-vous")]


def test_assign_speakers_without_turns_is_a_noop():
    segments = [Segment(0, 2, "Bonjour")]
    assert assign_speakers(segments, []) == segments


def test_assign_speakers_leaves_non_overlapping_segment_unlabeled():
    # Le tour de parole ne couvre pas du tout ce segment (ex : silence mal détecté).
    segments = [Segment(10, 12, "Au revoir")]
    turns = [SpeakerTurn(0, 2, "SPEAKER_00")]

    result = assign_speakers(segments, turns)

    assert result[0].speaker is None
