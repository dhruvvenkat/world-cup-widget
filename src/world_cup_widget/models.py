from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .flags import flag_for_code


class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TeamRecord:
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int | None = None

    @property
    def display_text(self) -> str:
        suffix = f" • {self.points} pts" if self.points is not None else ""
        return f"{self.wins}-{self.draws}-{self.losses}{suffix}"


@dataclass(frozen=True)
class Team:
    name: str
    short_name: str | None = None
    crest_url: str | None = None
    record: TeamRecord | None = None

    @property
    def display_name(self) -> str:
        return self.short_name or self.name

    @property
    def flag(self) -> str:
        return flag_for_code(self.short_name)

    @property
    def display_name_with_flag(self) -> str:
        return f"{self.flag} {self.display_name}" if self.flag else self.display_name

    @property
    def record_text(self) -> str:
        return self.record.display_text if self.record else "Record unavailable"


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
            minute = self.live_minute
            return f"LIVE {minute}'" if minute else "LIVE"
        if self.status is MatchStatus.SCHEDULED:
            return f"Kickoff {self.kickoff_text}"
        if self.status is MatchStatus.FINISHED:
            return "Full time"
        return "Status unavailable"

    @property
    def live_minute(self) -> int | None:
        if self.minute:
            return self.minute
        if self.status is not MatchStatus.LIVE or not self.kickoff:
            return None
        elapsed = datetime.now(timezone.utc) - self.kickoff.astimezone(timezone.utc)
        minute = int(elapsed.total_seconds() // 60) + 1
        return max(1, min(minute, 120))

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
