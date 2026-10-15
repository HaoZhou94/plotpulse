"""Algorithm stage 1: video shot-boundary detection."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, MediaMetadata, MediaSource, Shot


class ShotDetectionAlgorithm(AlgorithmModule):
    @abstractmethod
    def detect(
        self, source: MediaSource, metadata: MediaMetadata, options: AnalysisOptions
    ) -> Sequence[Shot]:
        raise NotImplementedError


class PrivateShotDetection(ShotDetectionAlgorithm):
    """Replace this method body with the private shot-detection call."""

    def detect(self, source, metadata, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class ShotDetectionTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateShotDetection()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.detect(
                    MediaSource("https://media.example.com/video.mp4"),
                    MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                    AnalysisOptions(),
                )

    return unittest.defaultTestLoader.loadTestsFromTestCase(ShotDetectionTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
