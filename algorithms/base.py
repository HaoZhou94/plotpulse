"""Minimal common contract for all algorithm stages."""

from abc import ABC
from typing import Any, Mapping

from errors import AlgorithmNotConfiguredError


class AlgorithmModule(ABC):
    name = "unconfigured"
    version = "unconfigured"

    def __init__(self, config: Mapping[str, Any] | None = None):
        self.config = dict(config or {})

    def ready(self) -> bool:
        return False

    def not_configured(self) -> AlgorithmNotConfiguredError:
        return AlgorithmNotConfiguredError(
            f"{self.__class__.__name__} has not been connected to a private model"
        )
