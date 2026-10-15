"""Algorithm stage 8: chapter title, summary, tag, and thumbnail metadata."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, Chapter, PlotSegment, SemanticEvent


class ChapterGenerationAlgorithm(AlgorithmModule):
    @abstractmethod
    def generate(
        self,
        plot_segments: Sequence[PlotSegment],
        semantic_events: Sequence[SemanticEvent],
        options: AnalysisOptions,
    ) -> Sequence[Chapter]:
        raise NotImplementedError


class PrivateChapterGeneration(ChapterGenerationAlgorithm):
    """Replace this method body with the private chapter-model call."""

    def generate(self, plot_segments, semantic_events, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class ChapterGenerationTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateChapterGeneration()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.generate((), (), AnalysisOptions())

    return unittest.defaultTestLoader.loadTestsFromTestCase(ChapterGenerationTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
