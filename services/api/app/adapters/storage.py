from __future__ import annotations

from pathlib import Path
from typing import Protocol


class MediaStorage(Protocol):
    async def put(self, key: str, content: bytes) -> str: ...


class LocalMediaStorage:
    """Development boundary. Stage 4 does not make media required for reporting."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def put(self, key: str, content: bytes) -> str:
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise ValueError("Invalid storage key")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return key
