"""Algorithm stage 1: Koala-compatible SVM shot-boundary detection."""

from __future__ import annotations

import importlib.util
import logging
import math
import os
from abc import abstractmethod
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit

from algorithms.base import AlgorithmModule
from errors import AlgorithmNotConfiguredError, VideoReadError
from models import AnalysisOptions, MediaMetadata, MediaSource, Shot


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "svm.joblib"
DEFAULT_SCALER_PATH = PROJECT_ROOT / "models" / "scaler.joblib"


def preprocess_frame(frame: Any) -> dict[str, Any]:
    """Extract the BGR histograms and edge map used to train the Koala SVM."""
    import cv2
    import numpy as np

    resized = cv2.resize(frame, (256, 256))
    channels = cv2.split(resized)
    histograms = [
        cv2.calcHist([channel], [0], None, [254], [1, 255])
        for channel in channels
    ]
    gray = cv2.resize(cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY), (128, 128))
    edge_map = np.maximum(gray, cv2.Canny(gray, 100, 200))
    return {"bgr_hist": np.asarray(histograms), "edge_map": edge_map}


def extract_features(feats_a: dict[str, Any], feats_b: dict[str, Any]) -> Any:
    """Build the two-dimensional BGR-correlation and edge-SSIM feature vector."""
    import cv2
    import numpy as np
    from skimage.metrics import structural_similarity as ssim

    bgr_similarity = cv2.compareHist(
        feats_a["bgr_hist"], feats_b["bgr_hist"], cv2.HISTCMP_CORREL
    )
    canny_similarity = ssim(
        feats_a["edge_map"], feats_b["edge_map"], data_range=255
    )
    return np.array([bgr_similarity, canny_similarity], dtype=np.float32)


def _trimmed_mu_std(values: Any) -> tuple[float, float]:
    """Return mean/std after discarding the lowest and highest 20 percent."""
    import numpy as np

    ordered = np.sort(values)
    size = len(ordered)
    trimmed = ordered[int(size * 0.2) : int(size * 0.8)]
    if len(trimmed) == 0:
        trimmed = ordered
    return float(trimmed.mean()), float(trimmed.std())


def _resolve_project_path(value: Any, default: Path) -> Path:
    path = Path(str(value)) if value else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _video_location(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "file":
        return value
    path = unquote(parsed.path)
    if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path


class ShotDetectionAlgorithm(AlgorithmModule):
    @abstractmethod
    def detect(
        self, source: MediaSource, metadata: MediaMetadata, options: AnalysisOptions
    ) -> Sequence[Shot]:
        raise NotImplementedError


class PrivateShotDetection(ShotDetectionAlgorithm):
    """Koala-compatible SVM classifier followed by temporal 3-sigma filtering."""

    name = "koala-transition-svm"
    version = "1.0"

    def __init__(self, config=None):  # type: ignore[no-untyped-def]
        super().__init__(config)
        self.model_path = _resolve_project_path(
            self.config.get("model_path"), DEFAULT_MODEL_PATH
        )
        self.scaler_path = _resolve_project_path(
            self.config.get("scaler_path"), DEFAULT_SCALER_PATH
        )
        self.minimum_decode_ratio = float(
            self.config.get("minimum_decode_ratio", 0.95)
        )
        self.skip_start_seconds = float(self.config.get("skip_start_seconds", 0))
        self.skip_end_seconds = float(self.config.get("skip_end_seconds", 0))
        self.merge_window_frames = int(self.config.get("merge_window_frames", 3))
        self.minimum_shot_seconds = float(
            self.config.get("minimum_shot_seconds", 0.3)
        )
        self.open_timeout_ms = int(self.config.get("open_timeout_ms", 120000))
        self.read_timeout_ms = int(self.config.get("read_timeout_ms", 120000))
        self._model: Any | None = None
        self._scaler: Any | None = None

    def ready(self) -> bool:
        if self._readiness_errors():
            return False
        try:
            self._validate_config()
            self._load_model()
        except Exception:
            return False
        return True

    def detect(
        self,
        source: MediaSource,
        metadata: MediaMetadata,
        options: AnalysisOptions,
    ) -> Sequence[Shot]:
        del options
        errors = self._readiness_errors()
        if errors:
            raise AlgorithmNotConfiguredError(
                "Koala SVM shot detection is not ready: " + "; ".join(errors)
            )
        self._validate_config()
        model, scaler = self._load_model()

        import cv2
        import numpy as np

        cap = cv2.VideoCapture()
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_ms)
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_ms)
        cap.open(_video_location(source.video_url))
        if not cap.isOpened():
            cap.release()
            raise VideoReadError("unable to open video for shot detection")

        capture_fps = float(cap.get(cv2.CAP_PROP_FPS))
        fps = capture_fps if capture_fps > 0 else float(metadata.fps or 0)
        if fps <= 0:
            cap.release()
            raise VideoReadError("unable to determine video frame rate")
        reported_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        expected_frames = reported_frames if reported_frames > 0 else int(
            round(metadata.duration_seconds * fps)
        )

        logger = logging.getLogger("plotpulse")
        previous_features: dict[str, Any] | None = None
        svm_scores: list[float] = []
        frame_numbers: list[int] = []
        decoded_frames = 0
        progress_interval = max(1, expected_frames // 10)
        try:
            while True:
                success, frame = cap.read()
                if not success:
                    break
                frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                decoded_frames += 1
                if frame_index % progress_interval == 0:
                    logger.info(
                        "shot_detection_decode_progress",
                        extra={
                            "module_name": "shot_detection",
                            "decoded_frames": decoded_frames,
                            "expected_frames": expected_frames,
                        },
                    )
                current_features = preprocess_frame(frame)
                if previous_features is not None:
                    features = extract_features(
                        previous_features, current_features
                    ).reshape(1, -1)
                    transformed = scaler.transform(features)
                    score = float(
                        np.asarray(model.decision_function(transformed)).reshape(-1)[0]
                    )
                    svm_scores.append(score)
                    frame_numbers.append(frame_index)
                previous_features = current_features
        finally:
            cap.release()

        if expected_frames > 0:
            decode_ratio = decoded_frames / expected_frames
            if decode_ratio < self.minimum_decode_ratio:
                raise VideoReadError(
                    "video decoding was incomplete: "
                    f"decoded={decoded_frames}, expected={expected_frames}, "
                    f"ratio={decode_ratio:.2%}"
                )
        if not svm_scores:
            return (Shot("shot-000001", 0.0, metadata.duration_seconds, 1.0),)

        candidates = self._transition_candidates(
            np.asarray(svm_scores, dtype=np.float64),
            frame_numbers,
            fps,
            metadata.duration_seconds,
        )
        boundaries = self._merge_candidates(candidates, fps, metadata.duration_seconds)
        return self._build_shots(boundaries, metadata.duration_seconds, fps)

    def _readiness_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.model_path.is_file():
            errors.append(f"model file is missing: {self.model_path}")
        if not self.scaler_path.is_file():
            errors.append(f"scaler file is missing: {self.scaler_path}")
        for import_name, package_name in (
            ("cv2", "opencv-python-headless"),
            ("joblib", "joblib"),
            ("numpy", "numpy"),
            ("skimage", "scikit-image"),
            ("sklearn", "scikit-learn"),
        ):
            if importlib.util.find_spec(import_name) is None:
                errors.append(f"Python dependency is missing: {package_name}")
        return errors

    def _validate_config(self) -> None:
        if not 0 < self.minimum_decode_ratio <= 1:
            raise AlgorithmNotConfiguredError(
                "minimum_decode_ratio must be greater than 0 and at most 1"
            )
        if self.skip_start_seconds < 0 or self.skip_end_seconds < 0:
            raise AlgorithmNotConfiguredError("skip durations must not be negative")
        if self.merge_window_frames < 0:
            raise AlgorithmNotConfiguredError("merge_window_frames must not be negative")
        if self.minimum_shot_seconds < 0:
            raise AlgorithmNotConfiguredError("minimum_shot_seconds must not be negative")

    def _load_model(self) -> tuple[Any, Any]:
        if self._model is not None and self._scaler is not None:
            return self._model, self._scaler
        import joblib

        try:
            model = joblib.load(self.model_path)
            scaler = joblib.load(self.scaler_path)
        except Exception as exc:
            raise AlgorithmNotConfiguredError(
                "failed to load Koala SVM/scaler; verify that the artifacts are trusted "
                "and use a compatible scikit-learn version"
            ) from exc
        for label, component in (("SVM", model), ("scaler", scaler)):
            feature_count = getattr(component, "n_features_in_", 2)
            if int(feature_count) != 2:
                raise AlgorithmNotConfiguredError(
                    f"{label} expects {feature_count} features; Koala extraction produces 2"
                )
        if not hasattr(model, "decision_function") or not hasattr(scaler, "transform"):
            raise AlgorithmNotConfiguredError(
                "model must expose decision_function and scaler must expose transform"
            )
        self._model, self._scaler = model, scaler
        return model, scaler

    def _transition_candidates(
        self,
        scores: Any,
        frame_numbers: Sequence[int],
        fps: float,
        duration_seconds: float,
    ) -> list[tuple[int, float]]:
        import numpy as np

        count = len(scores)
        smoothed = scores.copy()
        if count >= 3:
            smoothed[1:-1] = np.convolve(scores, np.ones(3) / 3.0, mode="valid")
        visible = np.ones(count, dtype=bool)
        for index in range(count):
            if scores[index] < 0:
                visible[index] = False
            elif index >= 8 and smoothed[index] < 0.75:
                start = max(index - 8, 0)
                mean, std = _trimmed_mu_std(smoothed[start:index])
                if smoothed[index] < mean - 3 * max(0.2, std):
                    visible[index] = False

        start_frame = int(self.skip_start_seconds * fps)
        end_frame = int((duration_seconds - self.skip_end_seconds) * fps)
        candidates: list[tuple[int, float]] = []
        for index, frame_number in enumerate(frame_numbers):
            if frame_number < start_frame or frame_number >= end_frame:
                continue
            if not visible[index]:
                candidates.append((int(frame_number), float(scores[index])))
        return candidates

    def _merge_candidates(
        self,
        candidates: Sequence[tuple[int, float]],
        fps: float,
        duration_seconds: float,
    ) -> list[tuple[int, float]]:
        """Cluster adjacent negative frames and enforce the minimum shot duration."""
        if not candidates:
            return []
        clusters: list[list[tuple[int, float]]] = []
        for candidate in sorted(candidates):
            if not clusters or candidate[0] - clusters[-1][-1][0] > self.merge_window_frames:
                clusters.append([candidate])
            else:
                clusters[-1].append(candidate)
        strongest = [min(cluster, key=lambda value: value[1]) for cluster in clusters]
        minimum_frames = int(round(self.minimum_shot_seconds * fps))
        filtered: list[tuple[int, float]] = []
        total_frames = int(round(duration_seconds * fps))
        for candidate in strongest:
            frame_number, score = candidate
            if frame_number <= minimum_frames or total_frames - frame_number <= minimum_frames:
                continue
            if filtered and frame_number - filtered[-1][0] < minimum_frames:
                if score < filtered[-1][1]:
                    filtered[-1] = candidate
                continue
            filtered.append(candidate)
        return filtered

    @staticmethod
    def _build_shots(
        boundaries: Sequence[tuple[int, float]],
        duration_seconds: float,
        fps: float,
    ) -> tuple[Shot, ...]:
        starts = [(0.0, None)] + [
            (frame_number / fps, score) for frame_number, score in boundaries
        ]
        ends = [value[0] for value in starts[1:]] + [duration_seconds]
        shots: list[Shot] = []
        for index, ((start, score), end) in enumerate(zip(starts, ends), start=1):
            confidence = (
                1.0
                if score is None
                else 1.0 / (1.0 + math.exp(max(-60, min(60, score))))
            )
            shots.append(
                Shot(
                    shot_id=f"shot-{index:06d}",
                    start=start,
                    end=end,
                    confidence=confidence,
                    transition_type=None if index == 1 else "unknown",
                    transition_score=score,
                )
            )
        return tuple(shots)


def build_test_suite():
    import unittest
    from tempfile import TemporaryDirectory

    class ShotDetectionTests(unittest.TestCase):
        def test_missing_model_is_explicitly_unconfigured(self) -> None:
            with TemporaryDirectory() as directory:
                algorithm = PrivateShotDetection(
                    {
                        "model_path": str(Path(directory) / "svm.joblib"),
                        "scaler_path": str(Path(directory) / "scaler.joblib"),
                    }
                )
                self.assertFalse(algorithm.ready())
                with self.assertRaises(AlgorithmNotConfiguredError):
                    algorithm.detect(
                        MediaSource("https://media.example.com/video.mp4"),
                        MediaMetadata(10, "mp4", 1920, 1080, 25, True, False),
                        AnalysisOptions(),
                    )

        def test_boundaries_are_converted_to_continuous_shots(self) -> None:
            shots = PrivateShotDetection._build_shots(
                ((25, -2.0), (75, -1.0)), 4.0, 25.0
            )
            self.assertEqual(3, len(shots))
            self.assertEqual((0.0, 1.0), (shots[0].start, shots[0].end))
            self.assertEqual(shots[0].end, shots[1].start)
            self.assertEqual(shots[1].end, shots[2].start)
            self.assertEqual(4.0, shots[-1].end)
            self.assertIsNone(shots[0].transition_type)
            self.assertEqual("unknown", shots[1].transition_type)
            self.assertEqual(-2.0, shots[1].transition_score)

        def test_adjacent_candidates_are_merged_by_strongest_score(self) -> None:
            algorithm = PrivateShotDetection(
                {"merge_window_frames": 3, "minimum_shot_seconds": 0.1}
            )
            result = algorithm._merge_candidates(
                ((25, -1.0), (27, -2.0), (75, -0.5)), 25.0, 4.0
            )
            self.assertEqual([(27, -2.0), (75, -0.5)], result)

        @unittest.skipUnless(
            all(
                importlib.util.find_spec(name) is not None
                for name in ("cv2", "numpy", "skimage")
            ),
            "Koala feature dependencies are not installed",
        )
        def test_feature_extraction_produces_two_finite_values(self) -> None:
            import numpy as np

            first = np.zeros((64, 64, 3), dtype=np.uint8)
            second = np.full((64, 64, 3), 255, dtype=np.uint8)
            features = extract_features(
                preprocess_frame(first), preprocess_frame(second)
            )
            self.assertEqual((2,), features.shape)
            self.assertTrue(np.isfinite(features).all())

    return unittest.defaultTestLoader.loadTestsFromTestCase(ShotDetectionTests)


if __name__ == "__main__":
    import unittest
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(build_test_suite()).wasSuccessful())
