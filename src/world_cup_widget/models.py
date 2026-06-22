from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Team:
    name: str
    short_name: str | None = None
    crest_url: str | None = None

    @property
    def display_name(self) -> str:
        return self.short_name or self.name


@dataclass(frozen=True)
class Match:
    competition: str
    home_team: Team
    away_team: Team
    kickoff: datetime | None
    status: MatchStatus
    home_score: int | None = None
    away_score: int | None = None
    minute: int | None = None
    venue: str | None = None
    stage: str | None = None
    source: str = "unknown"

    @property
    def score_text(self) -> str:
        if self.home_score is None or self.away_score is None:
            return "vs"
        return f"{self.home_score} - {self.away_score}"

    @property
    def kickoff_text(self) -> str:
        if not self.kickoff:
            return "Kickoff unavailable"
        local_dt = self.kickoff.astimezone()
        return local_dt.strftime("%a %d %b, %H:%M")

    @property
    def status_text(self) -> str:
        if self.status is MatchStatus.LIVE:
            return f"LIVE {self.minute}'" if self.minute else "LIVE"
        if self.status is MatchStatus.SCHEDULED:
            return f"Kickoff {self.kickoff_text}"
        if self.status is MatchStatus.FINISHED:
            return "Full time"
        return "Status unavailable"

    @property
    def sort_key(self) -> tuple[int, float]:
        priority = {
            MatchStatus.LIVE: 0,
            MatchStatus.SCHEDULED: 1,
            MatchStatus.FINISHED: 2,
            MatchStatus.UNKNOWN: 3,
        }[self.status]
        timestamp = self.kickoff.timestamp() if self.kickoff else datetime.max.replace(tzinfo=timezone.utc).timestamp()
        return priority, timestamp
