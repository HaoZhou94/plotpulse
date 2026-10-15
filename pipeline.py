"""Only coordinates algorithm stages; it does not implement any model logic."""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from algorithms.registry import AlgorithmRegistry
from errors import JobCancelledError, QualityGateError
from logging_utils import log_event
from media import MediaProbe, SourcePolicy
from models import (
    AnalysisOptions,
    AnalysisResult,
    MediaSource,
    PIPELINE_VERSION,
    SCHEMA_VERSION,
)
from quality import ChapterQualityValidator


ProgressCallback = Callable[[str, int], None]
CancelCheck = Callable[[], bool]
T = TypeVar("T")


class AnalysisPipeline:
    def __init__(
        self,
        source_policy: SourcePolicy,
        media_probe: MediaProbe,
        algorithms: AlgorithmRegistry,
        quality_validator: ChapterQualityValidator,
        logger: logging.Logger,
    ):
        self.source_policy = source_policy
        self.media_probe = media_probe
        self.algorithms = algorithms
        self.quality_validator = quality_validator
        self.logger = logger

    def analyze(
        self,
        source: MediaSource,
        options: AnalysisOptions,
        job_id: str = "direct",
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> AnalysisResult:
        progress = on_progress or (lambda _stage, _value: None)
        cancelled = is_cancelled or (lambda: False)
        options.validate()
        self._stage(job_id, "validate_source", 3, lambda: self.source_policy.validate(source), progress, cancelled)
        metadata = self._stage(job_id, "probe_media", 8, lambda: self.media_probe.probe(source), progress, cancelled)
        shots = self._stage(
            job_id, "shot_detection", 18,
            lambda: self.algorithms.shot_detection.detect(source, metadata, options),
            progress, cancelled,
        )
        audio = self._stage(
            job_id, "audio_detection", 30,
            lambda: self.algorithms.audio_detection.analyze(source, metadata, options),
            progress, cancelled,
        )
        ocr = self._stage(
            job_id, "ocr_detection", 40,
            lambda: self.algorithms.ocr_detection.detect(source, metadata, shots, options),
            progress, cancelled,
        )
        visuals = self._stage(
            job_id, "visual_analysis", 52,
            lambda: self.algorithms.visual_analysis.analyze(source, metadata, shots, options),
            progress, cancelled,
        )
        timeline = self._stage(
            job_id, "timeline_fusion", 62,
            lambda: self.algorithms.timeline_fusion.fuse(shots, audio, ocr, visuals, options),
            progress, cancelled,
        )
        semantics = self._stage(
            job_id, "semantic_analysis", 72,
            lambda: self.algorithms.semantic_analysis.analyze(timeline, options),
            progress, cancelled,
        )
        segments = self._stage(
            job_id, "plot_segmentation", 82,
            lambda: self.algorithms.plot_segmentation.segment(semantics, metadata, options),
            progress, cancelled,
        )
        chapters = tuple(self._stage(
            job_id, "chapter_generation", 92,
            lambda: self.algorithms.chapter_generation.generate(segments, semantics, options),
            progress, cancelled,
        ))
        report = self._stage(
            job_id, "quality_validation", 97,
            lambda: self.quality_validator.validate(metadata, chapters),
            progress, cancelled,
        )
        if not report.valid:
            raise QualityGateError("; ".join(report.errors))
        progress("completed", 100)
        return AnalysisResult(
            schema_version=SCHEMA_VERSION,
            pipeline_version=PIPELINE_VERSION,
            algorithm_versions=self.algorithms.versions(),
            metadata=metadata,
            chapters=chapters,
            quality_report=report,
        )

    def _stage(
        self,
        job_id: str,
        name: str,
        progress_value: int,
        action: Callable[[], T],
        on_progress: ProgressCallback,
        is_cancelled: CancelCheck,
    ) -> T:
        if is_cancelled():
            raise JobCancelledError("job was cancelled")
        on_progress(name, progress_value)
        started = time.monotonic()
        log_event(
            self.logger, logging.INFO, "algorithm_stage_started",
            job_id=job_id, stage=name, progress=progress_value,
        )
        try:
            result = action()
        except Exception:
            log_event(
                self.logger, logging.ERROR, "algorithm_stage_failed",
                job_id=job_id, stage=name,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                exc_info=True,
            )
            raise
        if is_cancelled():
            raise JobCancelledError("job was cancelled")
        log_event(
            self.logger, logging.INFO, "algorithm_stage_completed",
            job_id=job_id, stage=name,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            result_count=len(result) if hasattr(result, "__len__") else None,
        )
        return result


def build_test_suite():
    import unittest

    from algorithms.audio_detection import AudioDetectionAlgorithm
    from algorithms.chapter_generation import ChapterGenerationAlgorithm
    from algorithms.ocr_detection import OCRDetectionAlgorithm
    from algorithms.plot_segmentation import PlotSegmentationAlgorithm
    from algorithms.semantic_analysis import SemanticAnalysisAlgorithm
    from algorithms.shot_detection import ShotDetectionAlgorithm
    from algorithms.timeline_fusion import TimelineFusionAlgorithm
    from algorithms.visual_analysis import VisualAnalysisAlgorithm
    from config import Settings
    from logging_utils import configure_logging
    from media import MediaProbe
    from models import (
        AudioAnalysis, Chapter, MediaMetadata, OCRSegment, PlotSegment,
        SemanticEvent, Shot, TimelineEvent, VisualEvent,
    )

    class Ready:
        name = "fake"
        version = "test-1"

        def ready(self) -> bool:
            return True

    class FakeProbe(MediaProbe):
        def probe(self, source):  # type: ignore[no-untyped-def]
            return MediaMetadata(100, "mp4", 1920, 1080, 25, True, False)

    class FakeShot(Ready, ShotDetectionAlgorithm):
        def detect(self, source, metadata, options):  # type: ignore[no-untyped-def]
            return (Shot("s1", 0, 100, 1.0),)

    class FakeAudio(Ready, AudioDetectionAlgorithm):
        def analyze(self, source, metadata, options):  # type: ignore[no-untyped-def]
            return AudioAnalysis()

    class FakeOCR(Ready, OCRDetectionAlgorithm):
        def detect(self, source, metadata, shots, options):  # type: ignore[no-untyped-def]
            return ()

    class FakeVisual(Ready, VisualAnalysisAlgorithm):
        def analyze(self, source, metadata, shots, options):  # type: ignore[no-untyped-def]
            return (VisualEvent("v1", 0, 100, "scene"),)

    class FakeTimeline(Ready, TimelineFusionAlgorithm):
        def fuse(self, shots, audio, ocr, visual, options):  # type: ignore[no-untyped-def]
            return (TimelineEvent("t1", 0, 100, ("v1",)),)

    class FakeSemantic(Ready, SemanticAnalysisAlgorithm):
        def analyze(self, timeline, options):  # type: ignore[no-untyped-def]
            return (SemanticEvent("e1", 0, 100, "topic", "summary"),)

    class FakeSegment(Ready, PlotSegmentationAlgorithm):
        def segment(self, events, metadata, options):  # type: ignore[no-untyped-def]
            return (PlotSegment("p1", 0, 100, ("e1",), 1.0, 1.0),)

    class FakeChapter(Ready, ChapterGenerationAlgorithm):
        def generate(self, segments, events, options):  # type: ignore[no-untyped-def]
            return (Chapter("c1", 0, 100, "完整章节", "完整章节摘要"),)

    class PipelineTests(unittest.TestCase):
        def test_pipeline_coordinates_all_algorithm_modules(self) -> None:
            settings = Settings(allowed_media_hosts=("media.example.com",))
            registry = AlgorithmRegistry(
                FakeShot(), FakeAudio(), FakeOCR(), FakeVisual(),
                FakeTimeline(), FakeSemantic(), FakeSegment(), FakeChapter(),
            )
            pipeline = AnalysisPipeline(
                SourcePolicy(settings), FakeProbe(), registry,
                ChapterQualityValidator(), configure_logging("CRITICAL"),
            )
            progress: list[str] = []
            result = pipeline.analyze(
                MediaSource("https://media.example.com/video.mp4"),
                AnalysisOptions(),
                on_progress=lambda stage, _value: progress.append(stage),
            )
            self.assertEqual(1, len(result.chapters))
            self.assertIn("shot_detection", progress)
            self.assertIn("chapter_generation", progress)

    return unittest.defaultTestLoader.loadTestsFromTestCase(PipelineTests)
