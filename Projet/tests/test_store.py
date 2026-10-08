from datetime import datetime, timezone

import pytest

from subtitler.jobs.models import InputKind, Job, JobStatus, OutputKind
from subtitler.jobs.store import JobStore


def make_job(job_id: str, output_kind: OutputKind, duration: float = 10.0) -> Job:
    return Job(
        id=job_id, filename=f"{job_id}.mp4", input_kind=InputKind.VIDEO,
        output_kind=output_kind, model="m", status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc), media_duration=duration,
    )


def test_stats(tmp_path):
    store = JobStore(tmp_path / "db.sqlite")
    for job_id, kind in [("a", OutputKind.TEXT), ("b", OutputKind.TEXT),
                         ("c", OutputKind.SUBTITLES), ("d", OutputKind.VIDEO_TRACK),
                         ("e", OutputKind.VIDEO_EMBEDDED)]:
        store.add(make_job(job_id, kind))
    store.mark_running("a")
    store.mark_done("a", "hello", processing_time=2.0)
    store.mark_running("b")
    store.mark_done("b", "world", processing_time=4.0)
    store.mark_running("c")
    store.mark_failed("c", "boom")
    store.mark_running("d")

    stats = store.stats()
    assert stats["total_jobs"] == 5
    assert stats["inferences"] == {
        "total": 2, "by_kind": {"video_embedded": 0, "video_track": 0, "subtitles": 0, "text": 2},
    }
    assert stats["unfinished"]["total"] == 2
    assert stats["unfinished"]["by_kind"]["video_track"] == 1
    assert stats["failed"]["by_kind"]["subtitles"] == 1
    assert stats["avg_processing_time"] == 3.0
    assert stats["avg_realtime_ratio"] == pytest.approx(0.3)


def test_empty_stats(tmp_path):
    stats = JobStore(tmp_path / "db.sqlite").stats()
    assert stats["total_jobs"] == 0
    assert stats["avg_processing_time"] is None


def test_unfinished_jobs_survive_restart(tmp_path):
    JobStore(tmp_path / "db.sqlite").add(make_job("a", OutputKind.TEXT))
    reopened = JobStore(tmp_path / "db.sqlite")
    assert reopened.unfinished_ids() == ["a"]
    assert reopened.get("a").output_kind is OutputKind.TEXT
