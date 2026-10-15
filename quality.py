"""Deterministic validation after private chapter generation."""

from typing import Sequence

from models import Chapter, MediaMetadata, QualityReport


class ChapterQualityValidator:
    def __init__(self, minimum_coverage: float = 0.80):
        self.minimum_coverage = minimum_coverage

    def validate(self, metadata: MediaMetadata, chapters: Sequence[Chapter]) -> QualityReport:
        if not chapters:
            return QualityReport(False, 0.0, ("no chapters were generated",))
        ordered = sorted(chapters, key=lambda value: (value.start, value.end))
        errors: list[str] = []
        warnings: list[str] = []
        seen_ids: set[str] = set()
        previous_end = 0.0
        covered = 0.0
        for index, chapter in enumerate(ordered):
            label = f"chapter[{index}]"
            if chapter.chapter_id in seen_ids:
                errors.append(f"{label} has a duplicate id")
            seen_ids.add(chapter.chapter_id)
            if chapter.start < 0 or chapter.end <= chapter.start:
                errors.append(f"{label} has an invalid range")
                continue
            if chapter.end > metadata.duration_seconds + 0.5:
                errors.append(f"{label} exceeds video duration")
            if index and chapter.start < previous_end - 0.05:
                errors.append(f"{label} overlaps the previous chapter")
            if index and chapter.start - previous_end > 30:
                warnings.append(f"{label} starts after a gap longer than 30 seconds")
            if not chapter.title.strip() or not chapter.summary.strip():
                errors.append(f"{label} has an empty title or summary")
            covered += max(0.0, chapter.end - max(previous_end, chapter.start))
            previous_end = max(previous_end, chapter.end)
        coverage = min(1.0, covered / metadata.duration_seconds)
        if coverage < self.minimum_coverage:
            warnings.append(f"coverage {coverage:.1%} is below {self.minimum_coverage:.1%}")
        return QualityReport(not errors, round(coverage, 6), tuple(errors), tuple(warnings))


def build_test_suite():
    import unittest

    class QualityTests(unittest.TestCase):
        metadata = MediaMetadata(100, "mp4", 1920, 1080, 25, True, False)

        def test_overlap_fails(self) -> None:
            result = ChapterQualityValidator().validate(
                self.metadata,
                (
                    Chapter("1", 0, 60, "第一段", "第一段摘要"),
                    Chapter("2", 50, 100, "第二段", "第二段摘要"),
                ),
            )
            self.assertFalse(result.valid)

        def test_valid_full_coverage_passes(self) -> None:
            result = ChapterQualityValidator().validate(
                self.metadata,
                (
                    Chapter("1", 0, 50, "第一段", "第一段摘要"),
                    Chapter("2", 50, 100, "第二段", "第二段摘要"),
                ),
            )
            self.assertTrue(result.valid)
            self.assertEqual(1.0, result.coverage)

    return unittest.defaultTestLoader.loadTestsFromTestCase(QualityTests)
