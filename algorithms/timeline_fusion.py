"""Algorithm stage 5: fuse shot, audio, OCR, and visual evidence."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import (
    AnalysisOptions,
    AudioAnalysis,
    OCRSegment,
    Shot,
    TimelineEvent,
    VisualEvent,
)


class TimelineFusionAlgorithm(AlgorithmModule):
    @abstractmethod
    def fuse(
        self,
        shots: Sequence[Shot],
        audio: AudioAnalysis,
        ocr_segments: Sequence[OCRSegment],
        visual_events: Sequence[VisualEvent],
        options: AnalysisOptions,
    ) -> Sequence[TimelineEvent]:
        raise NotImplementedError


class PrivateTimelineFusion(TimelineFusionAlgorithm):
    """Replace this method body with the private fusion implementation."""

    def fuse(self, shots, audio, ocr_segments, visual_events, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class TimelineFusionTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateTimelineFusion()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.fuse((), AudioAnalysis(), (), (), AnalysisOptions())

    return unittest.defaultTestLoader.loadTestsFromTestCase(TimelineFusionTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
