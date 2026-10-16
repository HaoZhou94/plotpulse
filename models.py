"""DTOs shared by algorithm modules, pipeline, jobs, and API."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from errors import ValidationError


SCHEMA_VERSION = "1.1"
PIPELINE_VERSION = "0.4.0"

# 视频地址和字幕地址
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

# 时长、分辨率、帧率
@dataclass(frozen=True)
class MediaMetadata:
    duration_seconds: float
    format_name: str
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool
    has_subtitle: bool

# 镜头检测结果; frozen=True表示对象创建后不能随意修改，可以降低不同模块之间互相篡改数据的风险
@dataclass(frozen=True)
class Shot:
    shot_id: str
    start: float
    end: float
    confidence: float
    # Transition used to enter this shot; the first shot has no incoming transition.
    transition_type: str | None = None
    # Raw SVM decision score for the incoming transition; lower means more anomalous.
    transition_score: float | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float | None = None
    sentence_complete: bool | None = None
    emotion: str | None = None


@dataclass(frozen=True)
class AudioEvent:
    event_id: str
    start: float
    end: float
    event_type: str
    description: str
    confidence: float | None = None
    boundary_time: float | None = None
    salience: float | None = None

# 语音文本和音频文件
@dataclass(frozen=True)
class AudioAnalysis:
    transcripts: tuple[TranscriptSegment, ...] = ()
    events: tuple[AudioEvent, ...] = ()

# 画面文字
@dataclass(frozen=True)
class OCRSegment:
    segment_id: str
    start: float
    end: float
    text: str
    confidence: float

# 视觉事件
@dataclass(frozen=True)
class VisualEvent:
    event_id: str
    start: float
    end: float
    description: str
    entities: tuple[str, ...] = ()
    confidence: float | None = None
    event_type: str | None = None
    action_phase: str | None = None
    location: str | None = None

# 多模态融合结果
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
class BoundaryCue:
    """A timestamped piece of multimodal evidence for a possible scene boundary."""

    cue_id: str
    timestamp: float
    modality: str
    cue_type: str
    confidence: float
    description: str = ""
    start: float | None = None
    end: float | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TimelineFusionResult:
    events: tuple[TimelineEvent, ...] = ()
    boundary_cues: tuple[BoundaryCue, ...] = ()

    def __len__(self) -> int:
        return len(self.events)

# 语义事件
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
    character_goal: str | None = None
    emotion: str | None = None
    plot_function: str | None = None
    state_changes: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundaryScores:
    narrative: float = 0.0
    dialogue: float = 0.0
    action: float = 0.0
    audio: float = 0.0
    visual: float = 0.0
    rhythm: float = 0.0
    continuity: float = 0.0
    total: float = 0.0


@dataclass(frozen=True)
class SceneBoundary:
    boundary_id: str
    window_start: float
    window_end: float
    cut_time: float
    reason: str
    confidence: float
    scores: BoundaryScores = field(default_factory=BoundaryScores)
    detected_transition: str | None = None
    recommended_visual_transition: str = "hard_cut"
    recommended_audio_transition: str = "none"
    outgoing_audio_end: float | None = None
    incoming_audio_start: float | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SceneSegment:
    scene_id: str
    start: float
    end: float
    semantic_event_ids: tuple[str, ...] = ()
    characters: tuple[str, ...] = ()
    location: str | None = None
    time_context: str | None = None
    entry_boundary_id: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class SceneSegmentationResult:
    scenes: tuple[SceneSegment, ...] = ()
    boundaries: tuple[SceneBoundary, ...] = ()

    def __len__(self) -> int:
        return len(self.scenes)

# 剧情分段
@dataclass(frozen=True)
class PlotSegment:
    segment_id: str
    start: float
    end: float
    semantic_event_ids: tuple[str, ...]
    importance: float
    confidence: float

# 最终展示给观众的剧情章节
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

# 最终完整结果
@dataclass(frozen=True)
class AnalysisResult:
    schema_version: str
    pipeline_version: str
    algorithm_versions: Mapping[str, str]
    metadata: MediaMetadata
    chapters: tuple[Chapter, ...]
    quality_report: QualityReport
    scenes: tuple[SceneSegment, ...] = ()
    transitions: tuple[SceneBoundary, ...] = ()


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
