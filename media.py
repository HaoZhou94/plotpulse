"""Video source policy and ffprobe metadata extraction."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlsplit, urlunsplit

from config import Settings
from errors import MediaProbeError, ValidationError
from logging_utils import log_event
from models import MediaMetadata, MediaSource


def _windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith("\\\\")


def _host_allowed(host: str, allowed_hosts: Sequence[str]) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        allowed == "*"
        or normalized == allowed.lower().rstrip(".")
        or normalized.endswith("." + allowed.lower().rstrip("."))
        for allowed in allowed_hosts
    )


def redact_url(value: str | None) -> str | None:
    if not value:
        return value
    if _windows_path(value):
        return f"local://***/{Path(value).name}"
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        filename = Path(parsed.path).name
        return urlunsplit((parsed.scheme, parsed.netloc, f"/***/{filename}", "", ""))
    return f"local://***/{Path(unquote(parsed.path or value)).name}"


class SourcePolicy:
    def __init__(self, settings: Settings):
        self._settings = settings

    def validate(self, source: MediaSource) -> None:
        self._validate_location(source.video_url, "videoUrl")
        if source.subtitle_url:
            self._validate_location(source.subtitle_url, "subtitleUrl")

    def validate_callback(self, callback_url: str | None) -> None:
        if not callback_url:
            return
        parsed = urlsplit(callback_url)
        if parsed.scheme != "https":
            raise ValidationError("callbackUrl must use HTTPS")
        if not parsed.hostname or not _host_allowed(
            parsed.hostname, self._settings.allowed_callback_hosts
        ):
            raise ValidationError("callbackUrl host is not allowed")

    def _validate_location(self, value: str, label: str) -> None:
        if _windows_path(value):
            self._validate_file(value, label)
            return
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"}:
            if not parsed.hostname or not _host_allowed(
                parsed.hostname, self._settings.allowed_media_hosts
            ):
                raise ValidationError(f"{label} host is not allowed")
            return
        if parsed.scheme in {"", "file"}:
            self._validate_file(unquote(parsed.path) if parsed.scheme else value, label)
            return
        raise ValidationError(f"{label} scheme must be HTTP, HTTPS, or local file")

    def _validate_file(self, value: str, label: str) -> None:
        if not self._settings.allow_local_media:
            raise ValidationError(f"local {label} is disabled")
        if not Path(value).expanduser().resolve().is_file():
            raise ValidationError(f"local {label} does not exist")


class MediaProbe(ABC):
    @abstractmethod
    def probe(self, source: MediaSource) -> MediaMetadata:
        raise NotImplementedError


class FFprobeMediaProbe(MediaProbe):
    def __init__(self, settings: Settings, logger: logging.Logger):
        self._settings = settings
        self._logger = logger

    def probe(self, source: MediaSource) -> MediaMetadata:
        command = [
            self._settings.ffprobe_bin,
            "-v", "error",
            "-show_entries",
            "format=duration,format_name:stream=codec_type,width,height,r_frame_rate",
            "-of", "json",
            source.video_url,
        ]
        started = time.monotonic()
        log_event(
            self._logger,
            logging.INFO,
            "media_probe_started",
            module_name="media",
            video_url=redact_url(source.video_url),
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._settings.ffprobe_timeout_seconds,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise MediaProbeError("ffprobe is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaProbeError("ffprobe timed out") from exc
        if completed.returncode != 0:
            raise MediaProbeError(
                f"ffprobe failed: {(completed.stderr or 'unknown error').strip()[:500]}"
            )
        try:
            metadata = self.parse_payload(json.loads(completed.stdout))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MediaProbeError("ffprobe returned invalid metadata") from exc
        if metadata.duration_seconds <= 0:
            raise MediaProbeError("video duration must be greater than zero")
        if metadata.duration_seconds > self._settings.max_video_duration_seconds:
            raise MediaProbeError("video duration exceeds configured limit")
        log_event(
            self._logger,
            logging.INFO,
            "media_probe_completed",
            module_name="media",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            duration_seconds=metadata.duration_seconds,
        )
        return metadata

    @staticmethod
    def parse_payload(payload: Mapping[str, Any]) -> MediaMetadata:
        format_payload = payload.get("format") or {}
        streams = payload.get("streams") or []
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if video is None:
            raise ValueError("no video stream")
        return MediaMetadata(
            duration_seconds=float(format_payload["duration"]),
            format_name=str(format_payload.get("format_name", "unknown")),
            width=int(video["width"]) if video.get("width") else None,
            height=int(video["height"]) if video.get("height") else None,
            fps=_fraction(video.get("r_frame_rate")),
            has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
            has_subtitle=any(stream.get("codec_type") == "subtitle" for stream in streams),
        )


def _fraction(value: Any) -> float | None:
    if not value:
        return None
    text = str(value)
    if "/" not in text:
        return float(text)
    numerator, denominator = text.split("/", 1)
    return None if float(denominator) == 0 else float(numerator) / float(denominator)


def build_test_suite():
    import unittest

    class MediaTests(unittest.TestCase):
        def test_host_allow_list(self) -> None:
            policy = SourcePolicy(Settings(allowed_media_hosts=("example.com",)))
            policy.validate(MediaSource("https://cdn.example.com/video.mp4"))
            with self.assertRaises(ValidationError):
                policy.validate(MediaSource("https://other.com/video.mp4"))

        def test_ffprobe_payload_mapping(self) -> None:
            result = FFprobeMediaProbe.parse_payload(
                {
                    "format": {"duration": "10.5", "format_name": "mp4"},
                    "streams": [
                        {"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "25/1"},
                        {"codec_type": "audio"},
                    ],
                }
            )
            self.assertEqual(25.0, result.fps)
            self.assertTrue(result.has_audio)

        def test_signed_url_is_redacted(self) -> None:
            self.assertEqual(
                "https://example.com/***/v.mp4",
                redact_url("https://example.com/a/v.mp4?secret=1"),
            )

    return unittest.defaultTestLoader.loadTestsFromTestCase(MediaTests)
