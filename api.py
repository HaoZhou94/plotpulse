"""FastAPI adapter consumed by the Java platform."""

from contextlib import asynccontextmanager
from typing import Any, Mapping

from algorithms.registry import AlgorithmRegistry, build_private_algorithms
from config import Settings
from errors import PlotPulseError
from jobs import (
    CallbackDispatcher,
    JobRepository,
    JobService,
    job_to_dict,
)
from logging_utils import configure_logging
from media import FFprobeMediaProbe, SourcePolicy
from models import AnalysisOptions, CreateJobCommand, MediaSource
from pipeline import AnalysisPipeline
from quality import ChapterQualityValidator

# 负责组装所有组件
def build_service(
    settings: Settings,
    algorithms: AlgorithmRegistry | None = None,
) -> JobService:
    logger = configure_logging(settings.log_level)
    algorithms = algorithms or build_private_algorithms(settings.algorithm_configs)
    policy = SourcePolicy(settings)
    repository = JobRepository(settings.database_path)
    pipeline = AnalysisPipeline(
        policy,
        FFprobeMediaProbe(settings, logger),
        algorithms,
        ChapterQualityValidator(),
        logger,
    )
    return JobService(
        settings,
        repository,
        pipeline,
        algorithms,
        policy,
        CallbackDispatcher(settings, policy, logger),
        logger,
    )


def create_app(settings: Settings | None = None, service: JobService | None = None):
    """Create the HTTP application. FastAPI is imported only when API is used."""
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, ConfigDict, Field

    settings = settings or Settings.from_yaml()
    service = service or build_service(settings)

    class OptionsRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        language: str = "zh"
        profile: str = "balanced"
        targetChapterSeconds: int = Field(default=180, ge=45, le=600)
        spoilerPolicy: str = "masked"

    class CreateRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        clientRequestId: str = Field(min_length=1, max_length=128)
        videoUrl: str = Field(min_length=1)
        subtitleUrl: str | None = None
        callbackUrl: str | None = None
        options: OptionsRequest = Field(default_factory=OptionsRequest)

    @asynccontextmanager
    async def lifespan(_):  # type: ignore[no-untyped-def]
        yield
        service.shutdown()

    app = FastAPI(title="PlotPulse API", version="0.4.0", lifespan=lifespan)

    @app.exception_handler(PlotPulseError)
    async def handle_error(_, exc: PlotPulseError):  # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {
                "code": exc.code,
                "message": exc.public_message,
                "retryable": exc.retryable,
            }},
        )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "UP"}

    @app.get("/health/ready")
    def ready():  # type: ignore[no-untyped-def]
        readiness = service.algorithms.readiness()
        is_ready = all(readiness.values())
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={"status": "UP" if is_ready else "NOT_READY", "algorithms": readiness},
        )

    @app.post("/api/v1/plot-jobs", status_code=202)
    def create_job(
        request: CreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if idempotency_key and idempotency_key != request.clientRequestId:
            raise HTTPException(422, "Idempotency-Key must equal clientRequestId")
        command = CreateJobCommand(
            request.clientRequestId,
            MediaSource(request.videoUrl, request.subtitleUrl),
            request.callbackUrl,
            AnalysisOptions(
                request.options.language,
                request.options.profile,
                request.options.targetChapterSeconds,
                request.options.spoilerPolicy,
            ),
        )
        record, created = service.create(command)
        response = job_to_dict(record)
        response["deduplicated"] = not created
        return response

    @app.get("/api/v1/plot-jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return job_to_dict(service.get(job_id))

    @app.get("/api/v1/plot-jobs/{job_id}/result")
    def get_result(job_id: str) -> Mapping[str, Any]:
        return service.get_result(job_id)

    @app.post("/api/v1/plot-jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        return job_to_dict(service.cancel(job_id))

    return app


def build_test_suite():
    import unittest

    try:
        from fastapi.testclient import TestClient
    except ImportError:
        TestClient = None  # type: ignore[assignment,misc]

    class ApiTests(unittest.TestCase):
        @unittest.skipIf(TestClient is None, "FastAPI is not installed in the active environment")
        def test_unconfigured_algorithms_report_not_ready(self) -> None:
            from tempfile import TemporaryDirectory
            from pathlib import Path

            with TemporaryDirectory() as directory:
                settings = Settings(
                    database_path=str(Path(directory) / "jobs.db"),
                    log_level="CRITICAL",
                )
                with TestClient(create_app(settings=settings)) as client:  # type: ignore[misc]
                    response = client.get("/health/ready")
                    self.assertEqual(503, response.status_code)

    return unittest.defaultTestLoader.loadTestsFromTestCase(ApiTests)
