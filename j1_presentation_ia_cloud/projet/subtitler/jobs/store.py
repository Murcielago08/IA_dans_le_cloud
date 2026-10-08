"""Persistance des jobs dans SQLite.

La base survit aux redémarrages : c'est elle qui permet de reprendre les
traitements interrompus et de calculer les statistiques d'usage.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from subtitler.jobs.models import InputKind, Job, JobStatus, OutputKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    input_kind TEXT NOT NULL,
    output_kind TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    media_duration REAL,
    started_at TEXT,
    finished_at TEXT,
    processing_time REAL,
    text TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        filename=row["filename"],
        input_kind=InputKind(row["input_kind"]),
        output_kind=OutputKind(row["output_kind"]),
        model=row["model"],
        status=JobStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        media_duration=row["media_duration"],
        started_at=_parse_date(row["started_at"]),
        finished_at=_parse_date(row["finished_at"]),
        processing_time=row["processing_time"],
        text=row["text"],
        error=row["error"],
    )


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Une connexion par opération : simple et sûr entre threads.
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def add(self, job: Job) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO jobs (id, filename, input_kind, output_kind, model, status,"
                " created_at, media_duration) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (job.id, job.filename, job.input_kind, job.output_kind, job.model,
                 job.status, job.created_at.isoformat(), job.media_duration),
            )

    def get(self, job_id: str) -> Job | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def recent(self, limit: int = 50, offset: int = 0) -> list[Job]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    def unfinished_ids(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM jobs WHERE status IN (?, ?) ORDER BY created_at",
                (JobStatus.PENDING, JobStatus.RUNNING),
            ).fetchall()
        return [row["id"] for row in rows]

    def mark_pending(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status = ?, started_at = NULL WHERE id = ?",
                (JobStatus.PENDING, job_id),
            )

    def mark_running(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
                (JobStatus.RUNNING, _now().isoformat(), job_id),
            )

    def mark_done(self, job_id: str, text: str, processing_time: float) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, processing_time = ?, text = ?"
                " WHERE id = ?",
                (JobStatus.DONE, _now().isoformat(), processing_time, text, job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
                (JobStatus.FAILED, _now().isoformat(), error, job_id),
            )

    def stats(self) -> dict:
        """Statistiques d'usage demandées par l'administrateur."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT output_kind, status, COUNT(*) AS count"
                " FROM jobs GROUP BY output_kind, status"
            ).fetchall()
            overall = db.execute(
                "SELECT AVG(processing_time) AS avg_time,"
                " AVG(processing_time / media_duration) AS avg_ratio"
                " FROM jobs WHERE status = ? AND media_duration > 0",
                (JobStatus.DONE,),
            ).fetchone()

        def count(statuses: set[JobStatus]) -> dict:
            by_kind = {kind.value: 0 for kind in OutputKind}
            for row in rows:
                if row["status"] in statuses:
                    by_kind[row["output_kind"]] += row["count"]
            return {"total": sum(by_kind.values()), "by_kind": by_kind}

        return {
            "total_jobs": sum(row["count"] for row in rows),
            "inferences": count({JobStatus.DONE}),
            "unfinished": count({JobStatus.PENDING, JobStatus.RUNNING}),
            "failed": count({JobStatus.FAILED}),
            "avg_processing_time": overall["avg_time"],
            # < 1 : le traitement est plus rapide que la durée du média.
            "avg_realtime_ratio": overall["avg_ratio"],
        }
