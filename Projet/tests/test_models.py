"""Catalogue des modèles (noms explicites) et choix de la langue."""

import pytest

from subtitler import media
from subtitler.transcription import get_info, model_infos
from subtitler.transcription.whisper import WhisperTranscriber
from tests.conftest import requires_ffmpeg
from tests.test_api import wait_for


def submit_in(client, path, language, model=None):
    data = {"output_kind": "text", "language": language}
    if model:
        data["model"] = model
    with path.open("rb") as file:
        return client.post("/api/jobs", files={"file": (path.name, file)}, data=data)


def test_catalogue_has_explicit_names():
    assert [model.label for model in model_infos()] == ["Rapide", "Rapide", "Équilibré", "Équilibré", "Précis"]
    assert all(model.description for model in model_infos())
    assert get_info("whisper-medium.en").languages == ("en",)
    assert get_info("whisper-medium").languages is None


@pytest.mark.parametrize(
    ("model", "language", "supported"),
    [("whisper-medium.en", "en", True), ("whisper-medium.en", "fr", False),
     ("whisper-medium.en", "auto", True), ("whisper-medium", "fr", True)],
)
def test_model_language_support(model, language, supported):
    assert get_info(model).supports(language) is supported


def test_info_lists_models_and_languages(client):
    info = client.get("/api/info").json()
    assert info["languages"]["fr"] == "Français"
    assert info["default_language"] == "en"
    turbo = next(model for model in info["model_details"] if model["name"] == "whisper-large-v3-turbo")
    assert turbo["label"] == "Précis" and turbo["languages"] is None


@requires_ffmpeg
def test_language_is_stored_and_passed_to_model(client, transcriber, audio_file):
    job = wait_for(client, submit_in(client, audio_file, "fr", "whisper-medium").json()["id"])
    assert job["status"] == "done"
    assert job["language"] == "fr"
    assert transcriber.languages == ["fr"]


@requires_ffmpeg
def test_auto_language_lets_model_detect(client, transcriber, audio_file):
    wait_for(client, submit_in(client, audio_file, "auto", "whisper-small").json()["id"])
    assert transcriber.languages == [None]


@requires_ffmpeg
def test_default_language(client, audio_file):
    with audio_file.open("rb") as file:
        job = client.post("/api/jobs", files={"file": ("a.wav", file)}, data={"output_kind": "text"}).json()
    assert job["language"] == "en"


@requires_ffmpeg
@pytest.mark.parametrize(
    ("language", "model", "message"),
    [("fr", "whisper-medium.en", "ne gère pas la langue « Français »"),
     ("xx", "whisper-medium", "Langue non prise en charge")],
)
def test_incompatible_language_is_refused(client, audio_file, language, model, message):
    response = submit_in(client, audio_file, language, model)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_english_only_models_ignore_language_option():
    calls = []

    class Pipeline:
        def __call__(self, audio_path, return_timestamps, **options):
            calls.append(options)
            return {"chunks": []}

    for model_id, expected in [("openai/whisper-medium.en", {}),
                               ("openai/whisper-medium", {"generate_kwargs": {"language": "fr", "task": "transcribe"}})]:
        transcriber = WhisperTranscriber(model_id, device="cpu")
        transcriber._load = Pipeline
        transcriber.transcribe("audio.wav", "fr")
        assert calls.pop() == expected


def test_subtitle_track_language_code():
    assert media.track_language("fr") == "fra"
    assert media.track_language("auto") == "und"
