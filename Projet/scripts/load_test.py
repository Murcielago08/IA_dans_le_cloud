"""Test de charge : vérifie que la solution tient la performance demandée
(temps de traitement < durée de l'échantillon) jusqu'à N utilisateurs en
parallèle, contre une instance réellement démarrée (GPU réel, pas de mock).

Contrairement à ``tests/test_concurrency.py`` (qui prouve juste que
l'architecture parallélise, avec un faux modèle instantané), ce script mesure
un vrai temps de traitement GPU : à lancer à la main sur le matériel cible.

Usage :
    python -m subtitler &                    # démarrer l'instance à tester
    python scripts/load_test.py poc/input.mp4 --concurrency 10
"""

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx


def submit_and_wait(base_url: str, file_path: Path, output_kind: str, timeout: float) -> dict:
    with file_path.open("rb") as file:
        response = httpx.post(
            f"{base_url}/api/jobs",
            files={"file": (file_path.name, file)},
            data={"output_kind": output_kind},
            timeout=60,
        )
    response.raise_for_status()
    job_id = response.json()["id"]

    started = time.perf_counter()
    deadline = started + timeout
    while time.perf_counter() < deadline:
        job = httpx.get(f"{base_url}/api/jobs/{job_id}", timeout=30).json()
        if job["status"] in ("done", "failed"):
            job["_wall_time"] = time.perf_counter() - started
            return job
        time.sleep(0.2)
    raise TimeoutError(f"job {job_id} non terminé après {timeout:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="Fichier .mp4/.wav à envoyer")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="URL de l'instance à tester")
    parser.add_argument("--output-kind", default="text", help="video_embedded/video_track/subtitles/text")
    parser.add_argument("--concurrency", type=int, default=10, help="Nombre d'utilisateurs simultanés")
    parser.add_argument("--timeout", type=float, default=600.0, help="Timeout par job, en secondes")
    args = parser.parse_args()

    print(f"Envoi de {args.concurrency} requêtes simultanées vers {args.url} ({args.file.name}) ...")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(submit_and_wait, args.url, args.file, args.output_kind, args.timeout)
            for _ in range(args.concurrency)
        ]
        results = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as error:
                print(f"  échec : {error}")

    done = [job for job in results if job["status"] == "done"]
    durations = [job["_wall_time"] for job in done]
    media_duration = next((job["media_duration"] for job in done if job.get("media_duration")), None)

    print(f"\n{len(done)}/{args.concurrency} traitements réussis")
    if durations:
        print("Temps de traitement bout en bout (file d'attente comprise) :")
        print(f"  min={min(durations):.1f}s  p50={statistics.median(durations):.1f}s  max={max(durations):.1f}s")
        if media_duration:
            ratio = max(durations) / media_duration
            verdict = "OK (plus rapide que l'échantillon)" if ratio < 1 else "DÉPASSÉ"
            print(f"  durée de l'échantillon : {media_duration:.1f}s -> ratio pire cas = {ratio:.2f} [{verdict}]")


if __name__ == "__main__":
    main()
