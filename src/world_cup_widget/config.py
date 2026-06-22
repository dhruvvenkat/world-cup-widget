from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    refresh_seconds: int = 60
    live_refresh_seconds: int = 15
    football_data_token: str | None = None
    competition_code: str = "WC"
    season: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        season_raw = os.getenv("WORLD_CUP_SEASON")
        return cls(
            refresh_seconds=int(os.getenv("WORLD_CUP_REFRESH_SECONDS", "60")),
            live_refresh_seconds=int(os.getenv("WORLD_CUP_LIVE_REFRESH_SECONDS", "15")),
            football_data_token=os.getenv("FOOTBALL_DATA_TOKEN"),
            competition_code=os.getenv("WORLD_CUP_COMPETITION", "WC"),
            season=int(season_raw) if season_raw else None,
        )
