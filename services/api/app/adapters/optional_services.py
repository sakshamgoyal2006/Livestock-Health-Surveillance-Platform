from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AdapterStatus:
    available: bool
    provider: str
    detail: str


class OptionalAnalysisAdapter(Protocol):
    def status(self) -> AdapterStatus: ...


class UnavailableDevelopmentAdapter:
    """Explicit null adapter: base report persistence never depends on analysis."""

    def __init__(self, capability: str) -> None:
        self.capability = capability

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            available=False,
            provider="local-unavailable",
            detail=f"{self.capability} is deferred beyond Checkpoint 1",
        )


OPTIONAL_ADAPTERS = {
    name: UnavailableDevelopmentAdapter(name) for name in ("image", "voice", "nlp", "weather", "ml")
}
