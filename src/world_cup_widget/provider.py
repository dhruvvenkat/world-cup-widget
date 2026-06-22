from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .config import Settings
from .models import Match, MatchStatus, StandingEntry, Team, TeamRecord


class MatchProviderError(RuntimeError):
    pass


class MatchProvider(ABC):
    @abstractmethod
    def current_match(self) -> Match | None:
        """Return the live match, or the next scheduled match if nothing is live."""

    def upcoming_matches(self, limit: int = 5) -> list[Match]:
        return []

    def close(self) -> None:
        """Release provider resources, if any."""


class FootballDataProvider(MatchProvider):
    """Football-Data.org provider.

    It supports FIFA World Cup via competition code ``WC``. A free API token is
    required and should be supplied as ``FOOTBALL_DATA_TOKEN``.
    """

    BASE_URL = "https://api.football-data.org/v4"
    LIVE_STATUSES = {"IN_PLAY"}
    SCHEDULED_STATUSES = {"SCHEDULED", "TIMED"}

    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        if not settings.football_data_token:
            raise MatchProviderError("FOOTBALL_DATA_TOKEN is not configured")
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"X-Auth-Token": settings.football_data_token})
        self._records_cache: dict[str, TeamRecord] = {}
        self._group_standings_cache: dict[str, tuple[StandingEntry, ...]] = {}
        self._records_cache_at: datetime | None = None

    def current_match(self) -> Match | None:
        matches = self._fetch_matches()
        if not matches:
            return None
        match = sorted(matches, key=lambda match: match.sort_key)[0]
        records, group_standings = self._fetch_standings()
        return self._with_records(match, records, group_standings)

    def upcoming_matches(self, limit: int = 5) -> list[Match]:
        records, group_standings = self._fetch_standings()
        matches = [self._with_records(match, records, group_standings) for match in self._fetch_matches()]
        upcoming = [match for match in matches if match.status is MatchStatus.SCHEDULED]
        return sorted(upcoming, key=lambda match: match.sort_key)[:limit]

    def _fetch_matches(self) -> list[Match]:
        today = datetime.now(timezone.utc).date()
        params: dict[str, str | int] = {
            "dateFrom": (today - timedelta(days=1)).isoformat(),
            "dateTo": (today + timedelta(days=7)).isoformat(),
        }
        if self.settings.season:
            params["season"] = self.settings.season

        url = f"{self.BASE_URL}/competitions/{self.settings.competition_code}/matches"
        response = self.session.get(url, params=params, timeout=(2, 3))
        if response.status_code >= 400:
            raise MatchProviderError(f"Football-Data request failed: {response.status_code} {response.text[:160]}")

        payload = response.json()
        return [self._parse_match(item) for item in payload.get("matches", [])]

    def _fetch_standings(self) -> tuple[dict[str, TeamRecord], dict[str, tuple[StandingEntry, ...]]]:
        if self._records_cache_at and datetime.now(timezone.utc) - self._records_cache_at < timedelta(minutes=5):
            return self._records_cache, getattr(self, "_group_standings_cache", {})

        params: dict[str, int] = {}
        if self.settings.season:
            params["season"] = self.settings.season

        url = f"{self.BASE_URL}/competitions/{self.settings.competition_code}/standings"
        response = self.session.get(url, params=params, timeout=(2, 3))
        if response.status_code >= 400:
            return self._records_cache, getattr(self, "_group_standings_cache", {})

        records: dict[str, TeamRecord] = {}
        group_standings: dict[str, tuple[StandingEntry, ...]] = {}
        all_entries: list[StandingEntry] = []
        for standing in response.json().get("standings", []):
            if standing.get("type") not in {None, "TOTAL"}:
                continue
            table_entries: list[StandingEntry] = []
            for row in standing.get("table", []):
                team = row.get("team") or {}
                record = TeamRecord(
                    wins=int(row.get("won") or 0),
                    draws=int(row.get("draw") or 0),
                    losses=int(row.get("lost") or 0),
                    points=row.get("points"),
                )
                for key in self._team_keys(team):
                    records[key] = record
                table_entries.append(StandingEntry(team=self._parse_team(team), record=record, position=row.get("position")))
            group_name = standing.get("group")
            if group_name and table_entries:
                group_standings[group_name] = tuple(table_entries)
            elif table_entries:
                all_entries = table_entries
        if all_entries:
            group_standings.update(self._derive_group_standings(all_entries))
        self._records_cache = records
        self._group_standings_cache = group_standings
        self._records_cache_at = datetime.now(timezone.utc)
        return records, group_standings

    def _derive_group_standings(self, all_entries: list[StandingEntry]) -> dict[str, tuple[StandingEntry, ...]]:
        memberships = self._fetch_group_memberships()
        by_key: dict[str, StandingEntry] = {}
        for entry in all_entries:
            for key in self._team_keys({"name": entry.team.name, "tla": entry.team.short_name, "shortName": entry.team.short_name}):
                by_key[key] = entry

        result: dict[str, tuple[StandingEntry, ...]] = {}
        for group, member_keys in memberships.items():
            entries: list[StandingEntry] = []
            seen: set[str] = set()
            for entry in all_entries:
                keys = self._team_keys({"name": entry.team.name, "tla": entry.team.short_name, "shortName": entry.team.short_name})
                if keys & member_keys and entry.team.display_name not in seen:
                    seen.add(entry.team.display_name)
                    entries.append(StandingEntry(entry.team, entry.record, len(entries) + 1))
            if entries:
                result[group] = tuple(entries)
        return result

    def _fetch_group_memberships(self) -> dict[str, set[str]]:
        params: dict[str, int] = {}
        if self.settings.season:
            params["season"] = self.settings.season
        url = f"{self.BASE_URL}/competitions/{self.settings.competition_code}/matches"
        response = self.session.get(url, params=params, timeout=(2, 3))
        if response.status_code >= 400:
            return {}
        memberships: dict[str, set[str]] = {}
        for item in response.json().get("matches", []):
            group = item.get("group")
            if not group:
                continue
            memberships.setdefault(group, set()).update(self._team_keys(item.get("homeTeam") or {}))
            memberships.setdefault(group, set()).update(self._team_keys(item.get("awayTeam") or {}))
        return memberships

    def _with_records(self, match: Match, records: dict[str, TeamRecord], group_standings: dict[str, tuple[StandingEntry, ...]]) -> Match:
        return Match(
            competition=match.competition,
            home_team=self._team_with_record(match.home_team, records),
            away_team=self._team_with_record(match.away_team, records),
            kickoff=match.kickoff,
            status=match.status,
            home_score=match.home_score,
            away_score=match.away_score,
            minute=match.minute,
            venue=match.venue,
            stage=match.stage,
            group=match.group,
            group_standings=group_standings.get(match.group or "", ()),
            source=match.source,
        )

    def _team_with_record(self, team: Team, records: dict[str, TeamRecord]) -> Team:
        record = records.get(team.name.upper()) or records.get((team.short_name or "").upper())
        return Team(name=team.name, short_name=team.short_name, crest_url=team.crest_url, record=record)

    def _parse_match(self, item: dict[str, Any]) -> Match:
        kickoff = self._parse_datetime(item.get("utcDate"))
        status = self._parse_status(item.get("status"), kickoff)
        score = item.get("score", {}).get("fullTime", {}) or {}
        return Match(
            competition=item.get("competition", {}).get("name") or "World Cup",
            home_team=self._parse_team(item.get("homeTeam") or {}),
            away_team=self._parse_team(item.get("awayTeam") or {}),
            kickoff=kickoff,
            status=status,
            home_score=score.get("home"),
            away_score=score.get("away"),
            venue=item.get("venue"),
            stage=item.get("stage"),
            group=item.get("group"),
            source="football-data.org",
        )

    def _parse_team(self, item: dict[str, Any]) -> Team:
        return Team(
            name=item.get("name") or "TBD",
            short_name=item.get("tla") or item.get("shortName"),
            crest_url=item.get("crest"),
        )

    def _team_keys(self, item: dict[str, Any]) -> set[str]:
        return {str(value).upper() for value in [item.get("name"), item.get("tla"), item.get("shortName")] if value}

    def close(self) -> None:
        self.session.close()

    def _parse_status(self, status: str | None, kickoff: datetime | None = None) -> MatchStatus:
        if status in self.LIVE_STATUSES:
            return MatchStatus.LIVE
        if status == "PAUSED":
            return MatchStatus.PAUSED
        if status in self.SCHEDULED_STATUSES and self._kickoff_is_current(kickoff):
            return MatchStatus.LIVE
        if status in self.SCHEDULED_STATUSES:
            return MatchStatus.SCHEDULED
        if status == "FINISHED":
            return MatchStatus.FINISHED
        return MatchStatus.UNKNOWN

    def _kickoff_is_current(self, kickoff: datetime | None) -> bool:
        if not kickoff:
            return False
        now = datetime.now(timezone.utc)
        elapsed = now - kickoff.astimezone(timezone.utc)
        return timedelta(minutes=0) <= elapsed <= timedelta(hours=2, minutes=30)

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class EspnScoreboardProvider(MatchProvider):
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    def __init__(self, session: requests.Session | None = None, league: str = "fifa.world") -> None:
        self.session = session or requests.Session()
        self.league = league

    def current_match(self) -> Match | None:
        response = self.session.get(f"{self.BASE_URL}/{self.league}/scoreboard", params={"limit": 100}, timeout=(2, 3))
        if response.status_code >= 400:
            raise MatchProviderError(f"ESPN scoreboard request failed: {response.status_code}")
        matches = [self._parse_event(event) for event in response.json().get("events", [])]
        matches = [match for match in matches if match]
        if not matches:
            return None
        return sorted(matches, key=lambda match: match.sort_key)[0]

    def upcoming_matches(self, limit: int = 5) -> list[Match]:
        response = self.session.get(f"{self.BASE_URL}/{self.league}/scoreboard", params={"limit": 100}, timeout=(2, 3))
        if response.status_code >= 400:
            raise MatchProviderError(f"ESPN scoreboard request failed: {response.status_code}")
        matches = [self._parse_event(event) for event in response.json().get("events", [])]
        upcoming = [match for match in matches if match and match.status is MatchStatus.SCHEDULED]
        return sorted(upcoming, key=lambda match: match.sort_key)[:limit]

    def _parse_event(self, event: dict[str, Any]) -> Match | None:
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((item for item in competitors if item.get("homeAway") == "home"), None)
        away = next((item for item in competitors if item.get("homeAway") == "away"), None)
        if not home or not away:
            return None
        status = self._parse_status(competition.get("status") or event.get("status") or {})
        return Match(
            competition=(event.get("league") or {}).get("name") or "FIFA World Cup",
            home_team=self._parse_team(home),
            away_team=self._parse_team(away),
            kickoff=self._parse_datetime(event.get("date")),
            status=status,
            home_score=self._parse_score(home.get("score")),
            away_score=self._parse_score(away.get("score")),
            minute=self._parse_minute(competition.get("status") or event.get("status") or {}),
            venue=(competition.get("venue") or {}).get("fullName"),
            stage=event.get("season", {}).get("slug"),
            group=None,
            source="espn",
        )

    def _parse_team(self, item: dict[str, Any]) -> Team:
        team = item.get("team") or {}
        return Team(
            name=team.get("displayName") or team.get("name") or "TBD",
            short_name=team.get("abbreviation"),
            record=self._parse_record(item.get("records") or []),
        )

    def _parse_record(self, records: list[dict[str, Any]]) -> TeamRecord | None:
        summary = next((record.get("summary") for record in records if record.get("summary")), None)
        if not summary:
            return None
        try:
            wins, draws, losses = [int(part) for part in summary.split("-", 2)]
        except ValueError:
            return None
        return TeamRecord(wins, draws, losses)

    def _parse_status(self, status: dict[str, Any]) -> MatchStatus:
        status_type = status.get("type") or {}
        name = status_type.get("name") or ""
        state = status_type.get("state") or ""
        if "HALFTIME" in name or "HALF_TIME" in name:
            return MatchStatus.PAUSED
        if state == "in" or "IN_PROGRESS" in name or "FIRST_HALF" in name or "SECOND_HALF" in name:
            return MatchStatus.LIVE
        if state == "post" or "FULL_TIME" in name:
            return MatchStatus.FINISHED
        if state == "pre":
            return MatchStatus.SCHEDULED
        return MatchStatus.UNKNOWN

    def _parse_minute(self, status: dict[str, Any]) -> int | None:
        display = (status.get("type") or {}).get("shortDetail") or status.get("displayClock") or ""
        digits = "".join(char for char in display if char.isdigit())
        return int(digits) if digits else None

    def _parse_score(self, value: str | int | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        if normalized.endswith("+00:00") and len(normalized) == 22:
            normalized = normalized.replace("+00:00", ":00+00:00")
        return datetime.fromisoformat(normalized)

    def close(self) -> None:
        self.session.close()


class CompositeProvider(MatchProvider):
    def __init__(self, providers: list[MatchProvider]) -> None:
        self.providers = providers

    def current_match(self) -> Match | None:
        errors: list[str] = []
        selected: Match | None = None
        for provider in self.providers:
            try:
                match = provider.current_match()
                if not match:
                    continue
                if selected is None:
                    selected = match
                    continue
                selected = self._merge_metadata(selected, match)
            except Exception as exc:
                errors.append(str(exc))
        if selected:
            return selected
        if errors:
            raise MatchProviderError("; ".join(errors))
        return None

    def upcoming_matches(self, limit: int = 5) -> list[Match]:
        for provider in self.providers:
            try:
                matches = provider.upcoming_matches(limit)
                if matches:
                    return matches[:limit]
            except Exception:
                continue
        return []

    def _merge_metadata(self, primary: Match, secondary: Match) -> Match:
        if not self._same_fixture(primary, secondary):
            return primary
        return Match(
            competition=primary.competition,
            home_team=primary.home_team,
            away_team=primary.away_team,
            kickoff=primary.kickoff or secondary.kickoff,
            status=primary.status,
            home_score=primary.home_score,
            away_score=primary.away_score,
            minute=primary.minute,
            venue=primary.venue or secondary.venue,
            stage=primary.stage or secondary.stage,
            group=primary.group or secondary.group,
            group_standings=primary.group_standings or secondary.group_standings,
            source=primary.source,
        )

    def _same_fixture(self, first: Match, second: Match) -> bool:
        first_codes = {first.home_team.display_name, first.away_team.display_name}
        second_codes = {second.home_team.display_name, second.away_team.display_name}
        return first_codes == second_codes

    def close(self) -> None:
        for provider in self.providers:
            provider.close()


class SampleProvider(MatchProvider):
    """Offline fallback used until a live provider is configured."""

    def current_match(self) -> Match:
        kickoff = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=2)
        return Match(
            competition="FIFA World Cup",
            home_team=Team("Team A", "TMA", record=TeamRecord(1, 0, 0, 3)),
            away_team=Team("Team B", "TMB", record=TeamRecord(0, 1, 0, 1)),
            kickoff=kickoff,
            status=MatchStatus.SCHEDULED,
            venue="Configure FOOTBALL_DATA_TOKEN for live data",
            stage="Sample fixture",
            source="sample",
        )

    def upcoming_matches(self, limit: int = 5) -> list[Match]:
        base = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        matches = [
            Match("FIFA World Cup", Team("Team C", "TMC"), Team("Team D", "TMD"), base + timedelta(hours=3), MatchStatus.SCHEDULED, source="sample"),
            Match("FIFA World Cup", Team("Team E", "TME"), Team("Team F", "TMF"), base + timedelta(hours=6), MatchStatus.SCHEDULED, source="sample"),
        ]
        return matches[:limit]


class FallbackProvider(MatchProvider):
    def __init__(self, primary: MatchProvider | None, fallback: MatchProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.last_error: str | None = None
        self.last_primary_match: Match | None = None

    def current_match(self) -> Match | None:
        if self.primary:
            try:
                match = self.primary.current_match()
                if match:
                    self.last_error = None
                    self.last_primary_match = match
                    return match
            except Exception as exc:  # keep widget alive on network/API issues
                self.last_error = str(exc)
                if self.last_primary_match:
                    return self.last_primary_match
        return self.fallback.current_match()

    def upcoming_matches(self, limit: int = 5) -> list[Match]:
        if self.primary:
            try:
                matches = self.primary.upcoming_matches(limit)
                if matches:
                    return matches[:limit]
            except Exception as exc:
                self.last_error = str(exc)
        return self.fallback.upcoming_matches(limit)

    def close(self) -> None:
        if self.primary:
            self.primary.close()
        self.fallback.close()


def build_provider(settings: Settings) -> FallbackProvider:
    providers: list[MatchProvider] = [EspnScoreboardProvider()]
    if settings.football_data_token:
        providers.append(FootballDataProvider(settings))
    primary: MatchProvider | None = CompositeProvider(providers) if providers else None
    return FallbackProvider(primary=primary, fallback=SampleProvider())
