"""Registry protocol — RegistryClient implementations push/inspect images."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ImageRef(BaseModel):
    registry: str
    repository: str
    tag: str
    digest: str | None = None

    @property
    def reference(self) -> str:
        if self.digest:
            return f"{self.registry}/{self.repository}@{self.digest}"
        return f"{self.registry}/{self.repository}:{self.tag}"

    @property
    def with_tag_only(self) -> str:
        return f"{self.registry}/{self.repository}:{self.tag}"


@runtime_checkable
class RegistryClient(Protocol):
    host: str

    async def authenticate(self) -> None: ...

    async def manifest_digest(self, ref: ImageRef) -> str | None: ...

    def docker_config_json(self) -> bytes:
        """Return a JSON blob suitable for `~/.docker/config.json`."""
        ...
