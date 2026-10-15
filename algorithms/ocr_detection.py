"""Algorithm stage 3: time-aligned OCR extraction."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, MediaMetadata, MediaSource, OCRSegment, Shot


class OCRDetectionAlgorithm(AlgorithmModule):
    @abstractmethod
    def detect(
        self,
        source: MediaSource,
        metadata: MediaMetadata,
        shots: Sequence[Shot],
        options: AnalysisOptions,
    ) -> Sequence[OCRSegment]:
        raise NotImplementedError


class PrivateOCRDetection(OCRDetectionAlgorithm):
    """Replace this method body with the private OCR call."""

    def detect(self, source, metadata, shots, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class OCRDetectionTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateOCRDetection()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.detect(
                    MediaSource("https://media.example.com/video.mp4"),
                    MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                    (),
                    AnalysisOptions(),
                )

    return unittest.defaultTestLoader.loadTestsFromTestCase(OCRDetectionTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
