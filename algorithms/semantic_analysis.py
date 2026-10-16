"""Algorithm stage 6: text and multimodal event semantic analysis."""

from abc import abstractmethod
from typing import Sequence

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError
from models import AnalysisOptions, SemanticEvent, TimelineFusionResult


class SemanticAnalysisAlgorithm(AlgorithmModule):
    @abstractmethod
    def analyze(
        self, timeline: TimelineFusionResult, options: AnalysisOptions
    ) -> Sequence[SemanticEvent]:
        raise NotImplementedError


class PrivateSemanticAnalysis(SemanticAnalysisAlgorithm):
    """Replace this method body with the private semantic-model call."""

    def analyze(self, timeline, options):  # type: ignore[no-untyped-def]
        raise self.not_configured()


def build_test_suite():
    import unittest

    class SemanticAnalysisTests(unittest.TestCase):
        def test_placeholder_is_explicitly_unconfigured(self) -> None:
            algorithm = PrivateSemanticAnalysis()
            self.assertFalse(algorithm.ready())
            with self.assertRaises(AlgorithmNotConfiguredError):
                algorithm.analyze(TimelineFusionResult(), AnalysisOptions())

    return unittest.defaultTestLoader.loadTestsFromTestCase(SemanticAnalysisTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
