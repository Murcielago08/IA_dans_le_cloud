"""Répartition des traitements entre utilisateurs et entre exemplaires du modèle."""

import threading
import time

from subtitler.jobs.worker import FairQueue
from subtitler.transcription.whisper import WhisperTranscriber

DELAY = 0.3


def drain(fair_queue: FairQueue, count: int) -> list[str]:
    """Traite les jobs un par un (un seul worker)."""
    order = []
    for _ in range(count):
        order.append(job_id := fair_queue.get())
        fair_queue.done(job_id)
    return order


def get_nowait(fair_queue: FairQueue, timeout: float = 0.2) -> str | None:
    """``get`` dans un thread : None si aucun job n'est disponible à temps."""
    result = []
    thread = threading.Thread(target=lambda: result.append(fair_queue.get()), daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        fair_queue.put("_unblock", "_test")  # libère le thread resté en attente
        thread.join(1)
        return None
    return result[0]


def test_users_are_served_in_turn():
    fair_queue = FairQueue()
    for job_id in ("a1", "a2", "a3", "a4", "a5"):
        fair_queue.put(job_id, "alice")
    fair_queue.put("b1", "bob")
    fair_queue.put("c1", "carol")
    fair_queue.put("b2", "bob")
    # Bob et Carol n'attendent pas la fin des 5 fichiers d'Alice.
    assert drain(fair_queue, 8) == ["a1", "b1", "c1", "a2", "b2", "a3", "a4", "a5"]


def test_one_running_job_per_user():
    fair_queue = FairQueue()
    fair_queue.put("a1", "alice")
    fair_queue.put("a2", "alice")
    fair_queue.put("b1", "bob")

    # Deux workers : Alice et Bob en parallèle, pas les deux fichiers d'Alice.
    assert fair_queue.get() == "a1"
    assert fair_queue.get() == "b1"
    # Un 3e worker libre n'a rien à prendre : a2 attend la fin de a1.
    assert get_nowait(fair_queue) is None
    fair_queue.done("a1")
    assert get_nowait(fair_queue) == "a2"


def test_waiting_worker_wakes_up_when_user_finishes():
    fair_queue = FairQueue()
    fair_queue.put("a1", "alice")
    fair_queue.put("a2", "alice")
    assert fair_queue.get() == "a1"
    timer = threading.Timer(0.1, fair_queue.done, args=("a1",))
    timer.start()
    assert get_nowait(fair_queue, timeout=2) == "a2"


def test_closed_queue_releases_waiting_workers():
    fair_queue = FairQueue()
    results = []
    thread = threading.Thread(target=lambda: results.append(fair_queue.get()))
    thread.start()
    fair_queue.close()
    thread.join(timeout=2)
    assert results == [None]


class FakePipeline:
    def __call__(self, audio_path, return_timestamps):
        time.sleep(DELAY)
        return {"chunks": [{"text": "hello", "timestamp": (0.0, 1.0)}]}


def transcribe_in_parallel(transcriber: WhisperTranscriber, count: int) -> float:
    threads = [threading.Thread(target=transcriber.transcribe, args=("audio.wav",)) for _ in range(count)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return time.perf_counter() - started


def make_transcriber(replicas: int, loads: list) -> WhisperTranscriber:
    transcriber = WhisperTranscriber("fake", device="cpu", replicas=replicas)
    transcriber._load = lambda: loads.append(1) or FakePipeline()
    return transcriber


def test_replicas_transcribe_simultaneously():
    loads = []
    elapsed = transcribe_in_parallel(make_transcriber(2, loads), 2)
    assert elapsed < DELAY * 1.6  # en série : 2 x DELAY
    assert len(loads) == 2


def test_replicas_are_capped_and_reused():
    loads = []
    transcriber = make_transcriber(2, loads)
    elapsed = transcribe_in_parallel(transcriber, 4)
    # 4 fichiers, 2 exemplaires : deux vagues, jamais plus de 2 modèles en mémoire.
    assert DELAY * 1.8 < elapsed < DELAY * 3.5
    assert len(loads) == 2
    transcribe_in_parallel(transcriber, 2)
    assert len(loads) == 2


def test_warm_up_loads_a_single_replica():
    loads = []
    transcriber = make_transcriber(3, loads)
    transcriber.warm_up()
    transcriber.warm_up()
    assert len(loads) == 1
