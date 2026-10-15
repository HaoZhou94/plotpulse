"""Algorithm stage 2: ASR, VAD, speaker, and audio-event analysis."""

from abc import abstractmethod

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, AudioAnalysis, MediaMetadata, MediaSource


class AudioDetectionAlgorithm(AlgorithmModule):
    @abstractmethod
    def analyze(
        self, source: MediaSource, metadata: MediaMetadata, options: AnalysisOptions
    ) -> AudioAnalysis:
        raise NotImplementedError


class PrivateAudioDetection(AudioDetectionAlgorithm):
    """Replace this method body with the private audio-analysis call."""

    def analyze(self, source, metadata, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class AudioDetectionTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateAudioDetection()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.analyze(
                    MediaSource("https://media.example.com/video.mp4"),
                    MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                    AnalysisOptions(),
                )

    return unittest.defaultTestLoader.loadTestsFromTestCase(AudioDetectionTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
