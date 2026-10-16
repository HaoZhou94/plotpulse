"""Algorithm stage 7: locate scene boundaries from narrative and multimodal cues."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import (
    AnalysisOptions,
    MediaMetadata,
    SceneSegmentationResult,
    SemanticEvent,
    TimelineFusionResult,
)


class SceneSegmentationAlgorithm(AlgorithmModule):
    """Turn coarse narrative changes into evidence-backed, exact scene cuts."""

    @abstractmethod
    def segment(
        self,
        timeline: TimelineFusionResult,
        semantic_events: Sequence[SemanticEvent],
        metadata: MediaMetadata,
        options: AnalysisOptions,
    ) -> SceneSegmentationResult:
        raise NotImplementedError


class PrivateSceneSegmentation(SceneSegmentationAlgorithm):
    """Replace this method body with the private scene-segmentation call."""

    def segment(self, timeline, semantic_events, metadata, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class SceneSegmentationTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateSceneSegmentation()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.segment(
                    TimelineFusionResult(),
                    (),
                    MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                    AnalysisOptions(),
                )

    return unittest.defaultTestLoader.loadTestsFromTestCase(SceneSegmentationTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
