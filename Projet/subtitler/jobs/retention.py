"""Durée de conservation des données : purge des traitements trop anciens.

Les fichiers envoyés, les résultats et la ligne en base d'un traitement sont
supprimés une fois la durée de conservation dépassée (6 mois par défaut),
qu'il ait été retiré de l'historique ou non. Les traitements encore en
attente ou en cours ne sont jamais purgés.
"""

import logging
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from subtitler.jobs.store import JobStore

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 3600


def purge_expired(store: JobStore, jobs_dir: Path, retention_days: int, now: datetime | None = None) -> int:
    """Supprime les traitements créés il y a plus de ``retention_days`` jours ; renvoie leur nombre."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    deleted = 0
    for job_id in store.expired_ids(cutoff):
        # Les fichiers d'abord : si leur suppression échoue, la ligne reste et
        # la prochaine purge réessaiera, au lieu de laisser des fichiers orphelins.
        shutil.rmtree(jobs_dir / job_id, ignore_errors=True)
        if (jobs_dir / job_id).exists():
            logger.warning("Fichiers du traitement %s non supprimés, nouvel essai à la prochaine purge", job_id)
            continue
        store.delete(job_id)
        deleted += 1
    if deleted:
        logger.info("Purge : %d traitement(s) de plus de %d jours supprimé(s)", deleted, retention_days)
    return deleted


class RetentionTask:
    """Lance la purge au démarrage puis à intervalle régulier, en arrière-plan."""

    def __init__(self, store: JobStore, jobs_dir: Path, retention_days: int,
                 interval: float = PURGE_INTERVAL_SECONDS):
        self.store = store
        self.jobs_dir = jobs_dir
        self.retention_days = retention_days
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="retention", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                purge_expired(self.store, self.jobs_dir, self.retention_days)
            except Exception:
                logger.exception("La purge des données a échoué")
            self._stop.wait(self.interval)
