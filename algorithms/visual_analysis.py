"""Algorithm stage 4: visual scene, character, and action analysis."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, MediaMetadata, MediaSource, Shot, VisualEvent


class VisualAnalysisAlgorithm(AlgorithmModule):
    @abstractmethod
    def analyze(
        self,
        source: MediaSource,
        metadata: MediaMetadata,
        shots: Sequence[Shot],
        options: AnalysisOptions,
    ) -> Sequence[VisualEvent]:
        raise NotImplementedError


class PrivateVisualAnalysis(VisualAnalysisAlgorithm):
    """Replace this method body with the private visual-model call."""

    def analyze(self, source, metadata, shots, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class VisualAnalysisTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateVisualAnalysis()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.analyze(
                    MediaSource("https://media.example.com/video.mp4"),
                    MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                    (),
                    AnalysisOptions(),
                )

    return unittest.defaultTestLoader.loadTestsFromTestCase(VisualAnalysisTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
