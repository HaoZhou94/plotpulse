"""Async job lifecycle, SQLite persistence, and Java callback delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
import threading
import time
import urllib.request
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from algorithms.registry import AlgorithmRegistry
from config import Settings
from errors import (
    AlgorithmNotConfiguredError,
    ConflictError,
    JobCancelledError,
    NotFoundError,
    PlotPulseError,
)
from logging_utils import log_event
from media import SourcePolicy, redact_url
from models import (
    AnalysisOptions,
    AnalysisResult,
    CreateJobCommand,
    JobRecord,
    JobStatus,
    MediaSource,
    TERMINAL_JOB_STATUSES,
)
from pipeline import AnalysisPipeline


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(type(value).__name__)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def command_to_dict(command: CreateJobCommand) -> dict[str, Any]:
    return {
        "client_request_id": command.client_request_id,
        "source": asdict(command.source),
        "callback_url": command.callback_url,
        "options": asdict(command.options),
    }


def command_from_dict(data: Mapping[str, Any]) -> CreateJobCommand:
    return CreateJobCommand(
        str(data["client_request_id"]),
        MediaSource(**data["source"]),
        data.get("callback_url"),
        AnalysisOptions(**data["options"]),
    )


def result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    return {
        "schemaVersion": result.schema_version,
        "pipelineVersion": result.pipeline_version,
        "algorithmVersions": dict(result.algorithm_versions),
        "metadata": {
            "durationSeconds": result.metadata.duration_seconds,
            "formatName": result.metadata.format_name,
            "width": result.metadata.width,
            "height": result.metadata.height,
            "fps": result.metadata.fps,
            "hasAudio": result.metadata.has_audio,
            "hasSubtitle": result.metadata.has_subtitle,
        },
        "chapters": [
            {
                "id": chapter.chapter_id,
                "start": chapter.start,
                "end": chapter.end,
                "title": chapter.title,
                "summary": chapter.summary,
                "characters": list(chapter.characters),
                "tags": list(chapter.tags),
                "importance": chapter.importance,
                "spoilerLevel": chapter.spoiler_level,
                "thumbnailTime": chapter.thumbnail_time,
                "confidence": chapter.confidence,
                "evidenceIds": list(chapter.evidence_ids),
            }
            for chapter in result.chapters
        ],
        "scenes": [
            {
                "id": scene.scene_id,
                "start": scene.start,
                "end": scene.end,
                "semanticEventIds": list(scene.semantic_event_ids),
                "characters": list(scene.characters),
                "location": scene.location,
                "timeContext": scene.time_context,
                "entryBoundaryId": scene.entry_boundary_id,
                "confidence": scene.confidence,
            }
            for scene in result.scenes
        ],
        "transitions": [
            {
                "id": transition.boundary_id,
                "candidateWindow": [transition.window_start, transition.window_end],
                "cutTime": transition.cut_time,
                "reason": transition.reason,
                "confidence": transition.confidence,
                "scores": {
                    "narrative": transition.scores.narrative,
                    "dialogue": transition.scores.dialogue,
                    "action": transition.scores.action,
                    "audio": transition.scores.audio,
                    "visual": transition.scores.visual,
                    "rhythm": transition.scores.rhythm,
                    "continuity": transition.scores.continuity,
                    "total": transition.scores.total,
                },
                "detectedTransition": transition.detected_transition,
                "recommendedVisualTransition": transition.recommended_visual_transition,
                "recommendedAudioTransition": transition.recommended_audio_transition,
                "outgoingAudioEnd": transition.outgoing_audio_end,
                "incomingAudioStart": transition.incoming_audio_start,
                "evidenceIds": list(transition.evidence_ids),
            }
            for transition in result.transitions
        ],
        "qualityReport": {
            "valid": result.quality_report.valid,
            "coverage": result.quality_report.coverage,
            "errors": list(result.quality_report.errors),
            "warnings": list(result.quality_report.warnings),
        },
    }


def job_to_dict(record: JobRecord) -> dict[str, Any]:
    return {
        "jobId": record.job_id,
        "clientRequestId": record.client_request_id,
        "status": record.status.value,
        "stage": record.stage,
        "progress": record.progress,
        "error": (
            {"code": record.error_code, "message": record.error_message}
            if record.error_code else None
        ),
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }


_UNSET = object()


class JobRepository:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.lock = threading.RLock()
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    client_request_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    cancel_requested INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def create_or_get(self, command: CreateJobCommand) -> tuple[JobRecord, bool]:
        request_json = _json(command_to_dict(command))
        now = _utc_now()
        record = JobRecord(
            f"plot_{uuid.uuid4().hex}", command.client_request_id,
            JobStatus.QUEUED, "queued", 0, request_json,
            None, None, None, False, now, now,
        )
        with self.lock, self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.job_id, record.client_request_id, record.status.value,
                        record.stage, record.progress, record.request_json,
                        record.result_json, record.error_code, record.error_message,
                        int(record.cancel_requested), record.created_at, record.updated_at,
                    ),
                )
                return record, True
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE client_request_id = ?",
                    (command.client_request_id,),
                ).fetchone()
                if row is None:
                    raise
                existing = self._row(row)
                if existing.request_json != request_json:
                    raise ConflictError("clientRequestId was reused with different parameters")
                return existing, False

    def get(self, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise NotFoundError("job was not found")
        return self._row(row)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | object = _UNSET,
        stage: str | object = _UNSET,
        progress: int | object = _UNSET,
        result_json: str | None | object = _UNSET,
        error_code: str | None | object = _UNSET,
        error_message: str | None | object = _UNSET,
        cancel_requested: bool | object = _UNSET,
    ) -> JobRecord:
        fields = {
            "status": status.value if isinstance(status, JobStatus) else status,
            "stage": stage,
            "progress": progress,
            "result_json": result_json,
            "error_code": error_code,
            "error_message": error_message,
            "cancel_requested": int(cancel_requested) if isinstance(cancel_requested, bool) else cancel_requested,
        }
        assignments: list[str] = []
        values: list[Any] = []
        for name, value in fields.items():
            if value is not _UNSET:
                assignments.append(f"{name} = ?")
                values.append(value)
        assignments.append("updated_at = ?")
        values.extend((_utc_now(), job_id))
        with self.lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id = ?", values
            )
            if cursor.rowcount == 0:
                raise NotFoundError("job was not found")
        return self.get(job_id)

    def cancel(self, job_id: str) -> JobRecord:
        record = self.get(job_id)
        if record.status in TERMINAL_JOB_STATUSES:
            return record
        return self.update(job_id, status=JobStatus.CANCELLING, cancel_requested=True)

    @staticmethod
    def _row(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            row["job_id"], row["client_request_id"], JobStatus(row["status"]),
            row["stage"], int(row["progress"]), row["request_json"],
            row["result_json"], row["error_code"], row["error_message"],
            bool(row["cancel_requested"]), row["created_at"], row["updated_at"],
        )


class CallbackDispatcher:
    def __init__(self, settings: Settings, policy: SourcePolicy, logger: logging.Logger):
        self.settings = settings
        self.policy = policy
        self.logger = logger

    def send(self, url: str | None, payload: Mapping[str, Any]) -> None:
        if not url:
            return
        try:
            self.policy.validate_callback(url)
            body = _json(payload).encode("utf-8")
            timestamp = str(int(time.time()))
            signature = hmac.new(
                self.settings.callback_hmac_secret.encode("utf-8"),
                timestamp.encode("ascii") + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            request = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-PlotPulse-Timestamp": timestamp,
                    "X-PlotPulse-Signature": signature,
                },
            )
            with urllib.request.urlopen(
                request, timeout=self.settings.callback_timeout_seconds
            ) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"callback returned {response.status}")
            log_event(
                self.logger, logging.INFO, "callback_delivered",
                job_id=payload.get("jobId"), callback_url=redact_url(url),
            )
        except Exception:
            log_event(
                self.logger, logging.ERROR, "callback_failed",
                job_id=payload.get("jobId"), callback_url=redact_url(url),
                exc_info=True,
            )


class JobService:
    def __init__(
        self,
        settings: Settings,
        repository: JobRepository,
        pipeline: AnalysisPipeline,
        algorithms: AlgorithmRegistry,
        source_policy: SourcePolicy,
        callback: CallbackDispatcher,
        logger: logging.Logger,
    ):
        self.settings = settings
        self.repository = repository
        self.pipeline = pipeline
        self.algorithms = algorithms
        self.source_policy = source_policy
        self.callback = callback
        self.logger = logger
        self.executor = ThreadPoolExecutor(
            max_workers=settings.max_workers, thread_name_prefix="plotpulse-job"
        )
        self.futures: set[Future[Any]] = set()
        self.lock = threading.Lock()

    def create(self, command: CreateJobCommand) -> tuple[JobRecord, bool]:
        command.validate()
        self.source_policy.validate(command.source)
        self.source_policy.validate_callback(command.callback_url)
        if not self.algorithms.all_ready():
            missing = [name for name, ready in self.algorithms.readiness().items() if not ready]
            raise AlgorithmNotConfiguredError(
                "private algorithms are not configured: " + ", ".join(missing)
            )
        record, created = self.repository.create_or_get(command)
        if created:
            future = self.executor.submit(self._run, record.job_id)
            with self.lock:
                self.futures.add(future)
            future.add_done_callback(self._forget)
        return record, created

    def get(self, job_id: str) -> JobRecord:
        return self.repository.get(job_id)

    def get_result(self, job_id: str) -> Mapping[str, Any]:
        record = self.repository.get(job_id)
        if record.status != JobStatus.SUCCEEDED or not record.result_json:
            raise ConflictError(f"result is not available; status={record.status.value}")
        return json.loads(record.result_json)

    def cancel(self, job_id: str) -> JobRecord:
        return self.repository.cancel(job_id)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _forget(self, future: Future[Any]) -> None:
        with self.lock:
            self.futures.discard(future)

    def _run(self, job_id: str) -> None:
        command: CreateJobCommand | None = None
        try:
            record = self.repository.get(job_id)
            command = command_from_dict(json.loads(record.request_json))
            self.repository.update(job_id, status=JobStatus.PROCESSING)
            result = self.pipeline.analyze(
                command.source,
                command.options,
                job_id=job_id,
                on_progress=lambda stage, progress: self.repository.update(
                    job_id, stage=stage, progress=progress
                ),
                is_cancelled=lambda: self.repository.get(job_id).cancel_requested,
            )
            final = self.repository.update(
                job_id,
                status=JobStatus.SUCCEEDED,
                stage="completed",
                progress=100,
                result_json=_json(result_to_dict(result)),
                error_code=None,
                error_message=None,
            )
            self._notify(final, command)
        except JobCancelledError:
            final = self.repository.update(
                job_id, status=JobStatus.CANCELLED,
                error_code="JOB_CANCELLED", error_message="job was cancelled",
            )
            if command:
                self._notify(final, command)
        except PlotPulseError as exc:
            final = self.repository.update(
                job_id, status=JobStatus.FAILED,
                error_code=exc.code, error_message=exc.public_message,
            )
            log_event(
                self.logger, logging.ERROR, "job_failed",
                job_id=job_id, error_code=exc.code, exc_info=True,
            )
            if command:
                self._notify(final, command)
        except Exception:
            final = self.repository.update(
                job_id, status=JobStatus.FAILED,
                error_code="INTERNAL_ERROR", error_message="unexpected internal error",
            )
            log_event(
                self.logger, logging.ERROR, "job_failed",
                job_id=job_id, error_code="INTERNAL_ERROR", exc_info=True,
            )
            if command:
                self._notify(final, command)

    def _notify(self, record: JobRecord, command: CreateJobCommand) -> None:
        payload = job_to_dict(record)
        if record.result_json:
            payload["result"] = json.loads(record.result_json)
        self.callback.send(command.callback_url, payload)


def build_test_suite():
    import unittest
    from tempfile import TemporaryDirectory

    class RepositoryTests(unittest.TestCase):
        def test_idempotent_create(self) -> None:
            with TemporaryDirectory() as directory:
                repository = JobRepository(str(Path(directory) / "jobs.db"))
                command = CreateJobCommand(
                    "request-1", MediaSource("https://example.com/video.mp4"),
                    None, AnalysisOptions(),
                )
                first, created_first = repository.create_or_get(command)
                second, created_second = repository.create_or_get(command)
                self.assertTrue(created_first)
                self.assertFalse(created_second)
                self.assertEqual(first.job_id, second.job_id)

        def test_result_serializes_scenes_and_transitions(self) -> None:
            from models import (
                AnalysisResult, BoundaryScores, Chapter, MediaMetadata,
                QualityReport, SceneBoundary, SceneSegment,
            )

            result = AnalysisResult(
                "1.1", "0.4.0", {},
                MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                (Chapter("c1", 0, 10, "标题", "摘要"),),
                QualityReport(True, 1.0),
                scenes=(
                    SceneSegment("s1", 0, 5),
                    SceneSegment("s2", 5, 10, entry_boundary_id="b1"),
                ),
                transitions=(
                    SceneBoundary(
                        "b1", 4, 6, 5, "location changed", 0.9,
                        BoundaryScores(total=0.9), evidence_ids=("cue-1",),
                    ),
                ),
            )
            payload = result_to_dict(result)
            self.assertEqual("s1", payload["scenes"][0]["id"])
            self.assertEqual(5, payload["transitions"][0]["cutTime"])

    return unittest.defaultTestLoader.loadTestsFromTestCase(RepositoryTests)
