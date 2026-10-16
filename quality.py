"""Deterministic validation after private chapter generation."""

from typing import Sequence

from models import Chapter, MediaMetadata, QualityReport, SceneBoundary, SceneSegment


class ChapterQualityValidator:
    def __init__(self, minimum_coverage: float = 0.80):
        self.minimum_coverage = minimum_coverage

    def validate(
        self,
        metadata: MediaMetadata,
        chapters: Sequence[Chapter],
        scenes: Sequence[SceneSegment] | None = None,
        transitions: Sequence[SceneBoundary] | None = None,
    ) -> QualityReport:
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
        if scenes is not None:
            self._validate_scenes(metadata, scenes, transitions or (), errors, warnings)
        return QualityReport(not errors, round(coverage, 6), tuple(errors), tuple(warnings))

    @staticmethod
    def _validate_scenes(
        metadata: MediaMetadata,
        scenes: Sequence[SceneSegment],
        transitions: Sequence[SceneBoundary],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        if not scenes:
            errors.append("no scenes were generated")
            return
        ordered_scenes = sorted(scenes, key=lambda value: (value.start, value.end))
        scene_ids: set[str] = set()
        for index, scene in enumerate(ordered_scenes):
            label = f"scene[{index}]"
            if scene.scene_id in scene_ids:
                errors.append(f"{label} has a duplicate id")
            scene_ids.add(scene.scene_id)
            if scene.start < 0 or scene.end <= scene.start:
                errors.append(f"{label} has an invalid range")
                continue
            if scene.end > metadata.duration_seconds + 0.5:
                errors.append(f"{label} exceeds video duration")
            if index:
                previous = ordered_scenes[index - 1]
                if scene.start < previous.end - 0.05:
                    errors.append(f"{label} overlaps the previous scene")
                elif scene.start - previous.end > 0.5:
                    warnings.append(f"{label} starts after a scene gap longer than 0.5 seconds")
        if ordered_scenes[0].start > 0.5:
            warnings.append("scene coverage starts after the beginning of the video")
        if metadata.duration_seconds - ordered_scenes[-1].end > 0.5:
            warnings.append("scene coverage ends before the end of the video")

        ordered_transitions = sorted(transitions, key=lambda value: value.cut_time)
        if len(ordered_transitions) != max(0, len(ordered_scenes) - 1):
            errors.append("scene transition count does not match adjacent scene count")
        boundary_ids: set[str] = set()
        for index, boundary in enumerate(ordered_transitions):
            label = f"transition[{index}]"
            if boundary.boundary_id in boundary_ids:
                errors.append(f"{label} has a duplicate id")
            boundary_ids.add(boundary.boundary_id)
            if not 0 <= boundary.window_start <= boundary.cut_time <= boundary.window_end:
                errors.append(f"{label} cut time is outside its candidate window")
            if boundary.window_end > metadata.duration_seconds + 0.5:
                errors.append(f"{label} candidate window exceeds video duration")
            if not 0 <= boundary.confidence <= 1:
                errors.append(f"{label} confidence must be between 0 and 1")
            for score_name, score in vars(boundary.scores).items():
                if not 0 <= score <= 1:
                    errors.append(f"{label} score {score_name} must be between 0 and 1")
            if not boundary.evidence_ids:
                warnings.append(f"{label} has no supporting evidence")
            for audio_time_name, audio_time in (
                ("outgoing_audio_end", boundary.outgoing_audio_end),
                ("incoming_audio_start", boundary.incoming_audio_start),
            ):
                if audio_time is not None and not 0 <= audio_time <= metadata.duration_seconds:
                    errors.append(f"{label} {audio_time_name} is outside video duration")
            if index < len(ordered_scenes) - 1:
                previous = ordered_scenes[index]
                following = ordered_scenes[index + 1]
                if abs(previous.end - boundary.cut_time) > 0.05:
                    errors.append(f"{label} does not align with the previous scene end")
                if abs(following.start - boundary.cut_time) > 0.05:
                    errors.append(f"{label} does not align with the following scene start")
                if following.entry_boundary_id != boundary.boundary_id:
                    errors.append(f"scene[{index + 1}] does not reference {label}")


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

        def test_valid_scene_boundary_passes(self) -> None:
            from models import BoundaryScores, SceneBoundary, SceneSegment

            result = ChapterQualityValidator().validate(
                self.metadata,
                (Chapter("1", 0, 100, "完整章节", "完整章节摘要"),),
                (
                    SceneSegment("s1", 0, 50),
                    SceneSegment("s2", 50, 100, entry_boundary_id="b1"),
                ),
                (
                    SceneBoundary(
                        "b1", 48, 52, 50, "location changed", 0.9,
                        BoundaryScores(total=0.9), evidence_ids=("shot-1",),
                    ),
                ),
            )
            self.assertTrue(result.valid)

        def test_misaligned_scene_boundary_fails(self) -> None:
            from models import SceneBoundary, SceneSegment

            result = ChapterQualityValidator().validate(
                self.metadata,
                (Chapter("1", 0, 100, "完整章节", "完整章节摘要"),),
                (
                    SceneSegment("s1", 0, 50),
                    SceneSegment("s2", 50, 100, entry_boundary_id="b1"),
                ),
                (SceneBoundary("b1", 48, 52, 49, "early cut", 0.9),),
            )
            self.assertFalse(result.valid)

    return unittest.defaultTestLoader.loadTestsFromTestCase(QualityTests)
