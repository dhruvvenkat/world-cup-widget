from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .config import Settings
from .models import Match, MatchStatus, Team


class MatchProviderError(RuntimeError):
    pass


class MatchProvider(ABC):
    @abstractmethod
    def current_match(self) -> Match | None:
        """Return the live match, or the next scheduled match if nothing is live."""


class FootballDataProvider(MatchProvider):
    """Football-Data.org provider.

    It supports FIFA World Cup via competition code ``WC``. A free API token is
    required and should be supplied as ``FOOTBALL_DATA_TOKEN``.
    """

    BASE_URL = "https://api.football-data.org/v4"
    LIVE_STATUSES = {"IN_PLAY", "PAUSED"}
    SCHEDULED_STATUSES = {"SCHEDULED", "TIMED"}

    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        if not settings.football_data_token:
            raise MatchProviderError("FOOTBALL_DATA_TOKEN is not configured")
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"X-Auth-Token": settings.football_data_token})

    def current_match(self) -> Match | None:
        matches = self._fetch_matches()
        if not matches:
            return None
        return sorted(matches, key=lambda match: match.sort_key)[0]

    def _fetch_matches(self) -> list[Match]:
        today = datetime.now(timezone.utc).date()
        params: dict[str, str | int] = {
            "dateFrom": (today - timedelta(days=1)).isoformat(),
            "dateTo": (today + timedelta(days=7)).isoformat(),
        }
        if self.settings.season:
            params["season"] = self.settings.season

        url = f"{self.BASE_URL}/competitions/{self.settings.competition_code}/matches"
        response = self.session.get(url, params=params, timeout=10)
        if response.status_code >= 400:
            raise MatchProviderError(f"Football-Data request failed: {response.status_code} {response.text[:160]}")

        payload = response.json()
        return [self._parse_match(item) for item in payload.get("matches", [])]

    def _parse_match(self, item: dict[str, Any]) -> Match:
        status = self._parse_status(item.get("status"))
        score = item.get("score", {}).get("fullTime", {}) or {}
        return Match(
            competition=item.get("competition", {}).get("name") or "World Cup",
            home_team=self._parse_team(item.get("homeTeam") or {}),
            away_team=self._parse_team(item.get("awayTeam") or {}),
            kickoff=self._parse_datetime(item.get("utcDate")),
            status=status,
            home_score=score.get("home"),
            away_score=score.get("away"),
            venue=item.get("venue"),
            stage=item.get("stage"),
            source="football-data.org",
        )

    def _parse_team(self, item: dict[str, Any]) -> Team:
        return Team(
            name=item.get("name") or "TBD",
            short_name=item.get("tla") or item.get("shortName"),
            crest_url=item.get("crest"),
        )

    def _parse_status(self, status: str | None) -> MatchStatus:
        if status in self.LIVE_STATUSES:
            return MatchStatus.LIVE
        if status in self.SCHEDULED_STATUSES:
            return MatchStatus.SCHEDULED
        if status == "FINISHED":
            return MatchStatus.FINISHED
        return MatchStatus.UNKNOWN

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SampleProvider(MatchProvider):
    """Offline fallback used until a live provider is configured."""

    def current_match(self) -> Match:
        kickoff = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=2)
        return Match(
            competition="FIFA World Cup",
            home_team=Team("Team A", "TMA"),
            away_team=Team("Team B", "TMB"),
            kickoff=kickoff,
            status=MatchStatus.SCHEDULED,
            venue="Configure FOOTBALL_DATA_TOKEN for live data",
            stage="Sample fixture",
            source="sample",
        )


class FallbackProvider(MatchProvider):
    def __init__(self, primary: MatchProvider | None, fallback: MatchProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.last_error: str | None = None

    def current_match(self) -> Match | None:
        if self.primary:
            try:
                match = self.primary.current_match()
                if match:
                    self.last_error = None
                    return match
            except Exception as exc:  # keep widget alive on network/API issues
                self.last_error = str(exc)
        return self.fallback.current_match()

    def close(self) -> None:
        if self.primary:
            self.primary.close()
        self.fallback.close()


def build_provider(settings: Settings) -> FallbackProvider:
    primary: MatchProvider | None = None
    if settings.football_data_token:
        primary = FootballDataProvider(settings)
    return FallbackProvider(primary=primary, fallback=SampleProvider())
