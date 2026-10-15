"""DTOs shared by algorithm modules, pipeline, jobs, and API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from errors import ValidationError


SCHEMA_VERSION = "1.0"
PIPELINE_VERSION = "0.3.0"


@dataclass(frozen=True)
class MediaSource:
    video_url: str
    subtitle_url: str | None = None


@dataclass(frozen=True)
class AnalysisOptions:
    language: str = "zh"
    profile: str = "balanced"
    target_chapter_seconds: int = 180
    spoiler_policy: str = "masked"

    def validate(self) -> None:
        if self.profile not in {"fast", "balanced", "quality"}:
            raise ValidationError("profile must be fast, balanced, or quality")
        if not 45 <= self.target_chapter_seconds <= 600:
            raise ValidationError("targetChapterSeconds must be between 45 and 600")
        if self.spoiler_policy not in {"masked", "full"}:
            raise ValidationError("spoilerPolicy must be masked or full")


@dataclass(frozen=True)
class MediaMetadata:
    duration_seconds: float
    format_name: str
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool
    has_subtitle: bool


@dataclass(frozen=True)
class Shot:
    shot_id: str
    start: float
    end: float
    confidence: float


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class AudioEvent:
    event_id: str
    start: float
    end: float
    event_type: str
    description: str
    confidence: float | None = None


@dataclass(frozen=True)
class AudioAnalysis:
    transcripts: tuple[TranscriptSegment, ...] = ()
    events: tuple[AudioEvent, ...] = ()


@dataclass(frozen=True)
class OCRSegment:
    segment_id: str
    start: float
    end: float
    text: str
    confidence: float


@dataclass(frozen=True)
class VisualEvent:
    event_id: str
    start: float
    end: float
    description: str
    entities: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    start: float
    end: float
    evidence_ids: tuple[str, ...]
    transcript: str = ""
    audio_description: str = ""
    visual_description: str = ""
    ocr_text: str = ""


@dataclass(frozen=True)
class SemanticEvent:
    event_id: str
    start: float
    end: float
    topic: str
    summary: str
    characters: tuple[str, ...] = ()
    location: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class PlotSegment:
    segment_id: str
    start: float
    end: float
    semantic_event_ids: tuple[str, ...]
    importance: float
    confidence: float


@dataclass(frozen=True)
class Chapter:
    chapter_id: str
    start: float
    end: float
    title: str
    summary: str
    characters: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    importance: float = 0.0
    spoiler_level: int = 0
    thumbnail_time: float | None = None
    confidence: float | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityReport:
    valid: bool
    coverage: float
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    schema_version: str
    pipeline_version: str
    algorithm_versions: Mapping[str, str]
    metadata: MediaMetadata
    chapters: tuple[Chapter, ...]
    quality_report: QualityReport


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


TERMINAL_JOB_STATUSES = {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED}


@dataclass(frozen=True)
class CreateJobCommand:
    client_request_id: str
    source: MediaSource
    callback_url: str | None
    options: AnalysisOptions

    def validate(self) -> None:
        if not self.client_request_id or len(self.client_request_id) > 128:
            raise ValidationError("clientRequestId must contain 1 to 128 characters")
        self.options.validate()


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    client_request_id: str
    status: JobStatus
    stage: str
    progress: int
    request_json: str
    result_json: str | None
    error_code: str | None
    error_message: str | None
    cancel_requested: bool
    created_at: str
    updated_at: str
