"""One place to assemble or replace the nine algorithm stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from algorithms.audio_detection import AudioDetectionAlgorithm, PrivateAudioDetection
from algorithms.chapter_generation import ChapterGenerationAlgorithm, PrivateChapterGeneration
from algorithms.ocr_detection import OCRDetectionAlgorithm, PrivateOCRDetection
from algorithms.plot_segmentation import PlotSegmentationAlgorithm, PrivatePlotSegmentation
from algorithms.scene_segmentation import PrivateSceneSegmentation, SceneSegmentationAlgorithm
from algorithms.semantic_analysis import PrivateSemanticAnalysis, SemanticAnalysisAlgorithm
from algorithms.shot_detection import PrivateShotDetection, ShotDetectionAlgorithm
from algorithms.timeline_fusion import PrivateTimelineFusion, TimelineFusionAlgorithm
from algorithms.visual_analysis import PrivateVisualAnalysis, VisualAnalysisAlgorithm


@dataclass(frozen=True)
class AlgorithmRegistry:
    shot_detection: ShotDetectionAlgorithm
    audio_detection: AudioDetectionAlgorithm
    ocr_detection: OCRDetectionAlgorithm
    visual_analysis: VisualAnalysisAlgorithm
    timeline_fusion: TimelineFusionAlgorithm
    semantic_analysis: SemanticAnalysisAlgorithm
    scene_segmentation: SceneSegmentationAlgorithm
    plot_segmentation: PlotSegmentationAlgorithm
    chapter_generation: ChapterGenerationAlgorithm

    def readiness(self) -> dict[str, bool]:
        return {name: algorithm.ready() for name, algorithm in self._items().items()}

    def versions(self) -> dict[str, str]:
        return {name: algorithm.version for name, algorithm in self._items().items()}

    def all_ready(self) -> bool:
        return all(self.readiness().values())

    def _items(self) -> dict[str, AlgorithmModuleType]:
        return {
            "shotDetection": self.shot_detection,
            "audioDetection": self.audio_detection,
            "ocrDetection": self.ocr_detection,
            "visualAnalysis": self.visual_analysis,
            "timelineFusion": self.timeline_fusion,
            "semanticAnalysis": self.semantic_analysis,
            "sceneSegmentation": self.scene_segmentation,
            "plotSegmentation": self.plot_segmentation,
            "chapterGeneration": self.chapter_generation,
        }


AlgorithmModuleType = (
    ShotDetectionAlgorithm
    | AudioDetectionAlgorithm
    | OCRDetectionAlgorithm
    | VisualAnalysisAlgorithm
    | TimelineFusionAlgorithm
    | SemanticAnalysisAlgorithm
    | SceneSegmentationAlgorithm
    | PlotSegmentationAlgorithm
    | ChapterGenerationAlgorithm
)


def build_private_algorithms(
    configs: Mapping[str, Mapping[str, Any]] | None = None,
) -> AlgorithmRegistry:
    configs = configs or {}
    return AlgorithmRegistry(
        shot_detection=PrivateShotDetection(configs.get("shot_detection")),
        audio_detection=PrivateAudioDetection(configs.get("audio_detection")),
        ocr_detection=PrivateOCRDetection(configs.get("ocr_detection")),
        visual_analysis=PrivateVisualAnalysis(configs.get("visual_analysis")),
        timeline_fusion=PrivateTimelineFusion(configs.get("timeline_fusion")),
        semantic_analysis=PrivateSemanticAnalysis(configs.get("semantic_analysis")),
        scene_segmentation=PrivateSceneSegmentation(configs.get("scene_segmentation")),
        plot_segmentation=PrivatePlotSegmentation(configs.get("plot_segmentation")),
        chapter_generation=PrivateChapterGeneration(configs.get("chapter_generation")),
    )


def build_test_suite():
    import unittest

    class RegistryTests(unittest.TestCase):
        def test_default_algorithms_are_all_unconfigured(self) -> None:
            registry = build_private_algorithms()
            self.assertFalse(registry.all_ready())
            self.assertEqual(9, len(registry.readiness()))

        def test_stage_config_is_injected(self) -> None:
            registry = build_private_algorithms(
                {"shot_detection": {"endpoint": "http://shot-service"}}
            )
            self.assertEqual(
                "http://shot-service", registry.shot_detection.config["endpoint"]
            )

    return unittest.defaultTestLoader.loadTestsFromTestCase(RegistryTests)
