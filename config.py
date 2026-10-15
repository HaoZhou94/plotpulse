"""Load validated runtime settings from config.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from errors import ValidationError


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, Mapping):
        raise ValidationError(f"config section '{name}' must be a mapping")
    return value


def _hosts(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationError(f"{field_name} must be a YAML list of host names")
    return tuple(item.strip().lower() for item in value if item.strip())


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_path: str = "./data/plotpulse.db"
    max_workers: int = 1
    ffprobe_bin: str = "ffprobe"
    ffprobe_timeout_seconds: int = 60
    max_video_duration_seconds: float = 21600
    allow_local_media: bool = False
    allowed_media_hosts: tuple[str, ...] = ()
    allowed_callback_hosts: tuple[str, ...] = ()
    callback_hmac_secret: str = ""
    callback_timeout_seconds: int = 10
    algorithm_configs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path = "config.yaml") -> "Settings":
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is required to read config.yaml; install requirements.txt"
            ) from exc
        config_path = Path(path)
        if not config_path.is_file():
            raise ValidationError(f"configuration file does not exist: {config_path}")
        try:
            content = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValidationError(f"invalid YAML configuration: {exc}") from exc
        if not isinstance(content, Mapping):
            raise ValidationError("config.yaml root must be a mapping")
        return cls.from_mapping(content)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Settings":
        server = _section(data, "server")
        logging_config = _section(data, "logging")
        storage = _section(data, "storage")
        worker = _section(data, "worker")
        media = _section(data, "media")
        callback = _section(data, "callback")
        algorithms = _section(data, "algorithms")
        algorithm_configs: dict[str, Mapping[str, Any]] = {}
        for name, value in algorithms.items():
            if not isinstance(value, Mapping):
                raise ValidationError(f"algorithms.{name} must be a mapping")
            algorithm_configs[str(name)] = dict(value)
        settings = cls(
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 8000)),
            log_level=str(logging_config.get("level", "INFO")).upper(),
            database_path=str(storage.get("database_path", "./data/plotpulse.db")),
            max_workers=int(worker.get("max_workers", 1)),
            ffprobe_bin=str(media.get("ffprobe_bin", "ffprobe")),
            ffprobe_timeout_seconds=int(media.get("ffprobe_timeout_seconds", 60)),
            max_video_duration_seconds=float(
                media.get("max_video_duration_seconds", 21600)
            ),
            allow_local_media=bool(media.get("allow_local_media", False)),
            allowed_media_hosts=_hosts(media.get("allowed_hosts", []), "media.allowed_hosts"),
            allowed_callback_hosts=_hosts(
                callback.get("allowed_hosts", []), "callback.allowed_hosts"
            ),
            callback_hmac_secret=str(callback.get("hmac_secret", "")),
            callback_timeout_seconds=int(callback.get("timeout_seconds", 10)),
            algorithm_configs=algorithm_configs,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValidationError("server.port must be between 1 and 65535")
        if self.max_workers < 1:
            raise ValidationError("worker.max_workers must be at least 1")
        if self.ffprobe_timeout_seconds < 1:
            raise ValidationError("media.ffprobe_timeout_seconds must be at least 1")
        if self.max_video_duration_seconds <= 0:
            raise ValidationError("media.max_video_duration_seconds must be positive")
        if self.callback_timeout_seconds < 1:
            raise ValidationError("callback.timeout_seconds must be at least 1")


def build_test_suite():
    import unittest

    class ConfigTests(unittest.TestCase):
        def test_nested_yaml_mapping_is_converted(self) -> None:
            settings = Settings.from_mapping(
                {
                    "server": {"port": 9000},
                    "worker": {"max_workers": 2},
                    "media": {"allowed_hosts": ["Media.Example.com"]},
                    "callback": {"allowed_hosts": ["java.example.com"]},
                    "algorithms": {"shot_detection": {"endpoint": "http://shot"}},
                }
            )
            self.assertEqual(9000, settings.port)
            self.assertEqual(2, settings.max_workers)
            self.assertEqual(("media.example.com",), settings.allowed_media_hosts)
            self.assertEqual(
                "http://shot", settings.algorithm_configs["shot_detection"]["endpoint"]
            )

        def test_invalid_worker_count_is_rejected(self) -> None:
            with self.assertRaises(ValidationError):
                Settings.from_mapping({"worker": {"max_workers": 0}})

    return unittest.defaultTestLoader.loadTestsFromTestCase(ConfigTests)
