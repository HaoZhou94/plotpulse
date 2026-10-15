"""Algorithm stage 7: split semantic events into plot segments."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, MediaMetadata, PlotSegment, SemanticEvent


class PlotSegmentationAlgorithm(AlgorithmModule):
    @abstractmethod
    def segment(
        self,
        semantic_events: Sequence[SemanticEvent],
        metadata: MediaMetadata,
        options: AnalysisOptions,
    ) -> Sequence[PlotSegment]:
        raise NotImplementedError


class PrivatePlotSegmentation(PlotSegmentationAlgorithm):
    """Replace this method body with the private segmentation call."""

    def segment(self, semantic_events, metadata, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class PlotSegmentationTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivatePlotSegmentation()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.segment(
                    (),
                    MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                    AnalysisOptions(),
                )

    return unittest.defaultTestLoader.loadTestsFromTestCase(PlotSegmentationTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
