"""Runtime configuration, read from the container environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Matches the local demonstration database defined in `compose.yaml`. Compose also passes this in
#: explicitly as `BINDLESS_DATABASE_URL`; the default exists so the failure mode is a clear
#: connection error rather than a silent fallback somewhere else.
DEFAULT_DATABASE_URL = "postgresql+psycopg://bindless:bindless-local-demo@db:5432/bindless"


@dataclass(frozen=True, slots=True)
class Settings:
    """Process settings resolved from the environment."""

    database_url: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(database_url=os.environ.get("BINDLESS_DATABASE_URL", DEFAULT_DATABASE_URL))


def get_settings() -> Settings:
    return Settings.from_env()
