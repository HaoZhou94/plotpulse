"""Shared application errors."""


class PlotPulseError(Exception):
    code = "PLOTPULSE_ERROR"
    http_status = 400
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.public_message = message


class ValidationError(PlotPulseError):
    code = "VALIDATION_ERROR"
    http_status = 422


class NotFoundError(PlotPulseError):
    code = "NOT_FOUND"
    http_status = 404


class ConflictError(PlotPulseError):
    code = "CONFLICT"
    http_status = 409


class AlgorithmNotConfiguredError(PlotPulseError):
    code = "ALGORITHM_NOT_CONFIGURED"
    http_status = 503


class MediaProbeError(PlotPulseError):
    code = "MEDIA_PROBE_ERROR"
    http_status = 422


class QualityGateError(PlotPulseError):
    code = "QUALITY_GATE_FAILED"
    http_status = 422


class JobCancelledError(PlotPulseError):
    code = "JOB_CANCELLED"
    http_status = 409
