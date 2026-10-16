"""PlotPulse command-line entry point."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Sequence


TEST_MODULES = {
    "config": "config",
    "media": "media",
    "shot_detection": "algorithms.shot_detection",
    "audio_detection": "algorithms.audio_detection",
    "ocr_detection": "algorithms.ocr_detection",
    "visual_analysis": "algorithms.visual_analysis",
    "timeline_fusion": "algorithms.timeline_fusion",
    "semantic_analysis": "algorithms.semantic_analysis",
    "scene_segmentation": "algorithms.scene_segmentation",
    "plot_segmentation": "algorithms.plot_segmentation",
    "chapter_generation": "algorithms.chapter_generation",
    "algorithm_registry": "algorithms.registry",
    "quality": "quality",
    "pipeline": "pipeline",
    "jobs": "jobs",
    "api": "api",
}


def run_tests(module_name: str | None, all_modules: bool) -> int:
    names = tuple(TEST_MODULES) if all_modules else (module_name,)
    suite = unittest.TestSuite()
    for name in names:
        if not name or name not in TEST_MODULES:
            print("Available modules: " + ", ".join(TEST_MODULES), file=sys.stderr)
            return 2
        module = importlib.import_module(TEST_MODULES[name])
        suite.addTests(module.build_test_suite())
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PlotPulse")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="YAML configuration file (default: config.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start Java-facing HTTP API")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    tests = sub.add_parser("self-test", help="run tests embedded in each module")
    group = tests.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--module", choices=tuple(TEST_MODULES))
    probe = sub.add_parser("probe", help="inspect one local video with ffprobe")
    probe.add_argument("--video", required=True)
    shots = sub.add_parser(
        "detect-shots", help="run the local Koala SVM shot detector"
    )
    shots.add_argument("--video", required=True)
    shots.add_argument("--output", help="optional JSON result path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # 运行各模块内部的单元测试
    if args.command == "self-test":
        return run_tests(args.module, args.all)
    # 启动给Java调用的HTTP服务
    if args.command == "serve":
        import uvicorn
        from api import create_app
        from config import Settings

        settings = Settings.from_yaml(args.config)
        uvicorn.run(
            create_app(settings=settings),
            host=args.host or settings.host,
            port=args.port or settings.port,
        )
        return 0
    # 只用ffprobe读取视频基础信息, 不执行剧情分析
    if args.command == "probe":
        from config import Settings
        from logging_utils import configure_logging
        from media import FFprobeMediaProbe, SourcePolicy
        from models import MediaSource

        settings = Settings.from_yaml(args.config)
        settings = Settings(**{**asdict(settings), "allow_local_media": True})
        source = MediaSource(args.video)
        SourcePolicy(settings).validate(source)
        result = FFprobeMediaProbe(settings, configure_logging(settings.log_level)).probe(source)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0
    if args.command == "detect-shots":
        from algorithms.shot_detection import PrivateShotDetection
        from config import Settings
        from logging_utils import configure_logging
        from media import FFprobeMediaProbe, SourcePolicy
        from models import AnalysisOptions, MediaSource

        settings = Settings.from_yaml(args.config)
        settings = Settings(**{**asdict(settings), "allow_local_media": True})
        source = MediaSource(args.video)
        SourcePolicy(settings).validate(source)
        metadata = FFprobeMediaProbe(
            settings, configure_logging(settings.log_level)
        ).probe(source)
        detector = PrivateShotDetection(
            settings.algorithm_configs.get("shot_detection")
        )
        shots = detector.detect(source, metadata, AnalysisOptions())
        payload = {
            "videoPath": str(Path(args.video).resolve()),
            "fps": metadata.fps,
            "durationSeconds": metadata.duration_seconds,
            "totalShots": len(shots),
            "shots": [asdict(shot) for shot in shots],
            "transitions": [
                {
                    "index": index,
                    "timeSeconds": shot.start,
                    "confidence": shot.confidence,
                    "rawScore": shot.transition_score,
                    "type": shot.transition_type,
                }
                for index, shot in enumerate(shots[1:], start=1)
            ],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding="utf-8")
            print(str(output))
        else:
            print(content)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
