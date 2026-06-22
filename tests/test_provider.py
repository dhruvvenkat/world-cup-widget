from datetime import datetime, timedelta, timezone

from world_cup_widget.config import Settings
from world_cup_widget.models import MatchStatus
from world_cup_widget.models import Match, Team
from world_cup_widget.provider import EspnScoreboardProvider, FallbackProvider, FootballDataProvider, MatchProvider, SampleProvider, build_provider


def test_settings_loads_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FOOTBALL_DATA_TOKEN", raising=False)
    monkeypatch.delenv("WORLD_CUP_REFRESH_SECONDS", raising=False)
    monkeypatch.delenv("WORLD_CUP_LIVE_REFRESH_SECONDS", raising=False)
    tmp_path.joinpath(".env").write_text(
        "FOOTBALL_DATA_TOKEN=dotenv-token\nWORLD_CUP_REFRESH_SECONDS=45\nWORLD_CUP_LIVE_REFRESH_SECONDS=7\n",
        encoding="utf-8",
    )

    settings = Settings.from_env()

    assert settings.football_data_token == "dotenv-token"
    assert settings.refresh_seconds == 45
    assert settings.live_refresh_seconds == 7


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    status_code = 200
    text = "ok"

    def json(self):
        return self._payload


MATCHES_PAYLOAD = {
            "matches": [
                {
                    "competition": {"name": "FIFA World Cup"},
                    "homeTeam": {"name": "France", "tla": "FRA"},
                    "awayTeam": {"name": "Brazil", "tla": "BRA"},
                    "utcDate": "2026-06-22T19:00:00Z",
                    "status": "IN_PLAY",
                    "score": {"fullTime": {"home": 1, "away": 0}},
                    "venue": "MetLife Stadium",
                    "stage": "GROUP_STAGE",
                }
            ]
        }

STANDINGS_PAYLOAD = {
    "standings": [
        {
            "table": [
                {"team": {"name": "France", "tla": "FRA"}, "won": 2, "draw": 1, "lost": 0, "points": 7},
                {"team": {"name": "Brazil", "tla": "BRA"}, "won": 1, "draw": 1, "lost": 1, "points": 4},
            ]
        }
    ]
}

ESPN_PAYLOAD = {
    "events": [
        {
            "date": "2026-06-22T01:00Z",
            "competitions": [
                {
                    "status": {"type": {"state": "in", "name": "STATUS_FIRST_HALF", "shortDetail": "17'"}},
                    "competitors": [
                        {"homeAway": "home", "score": "1", "team": {"displayName": "New Zealand", "abbreviation": "NZL"}, "records": [{"summary": "0-1-0"}]},
                        {"homeAway": "away", "score": "0", "team": {"displayName": "Egypt", "abbreviation": "EGY"}, "records": [{"summary": "0-1-0"}]},
                    ],
                }
            ],
        }
    ]
}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.params = None

    def get(self, url, params, timeout):
        self.params = params
        if url.endswith("/standings"):
            return FakeResponse(STANDINGS_PAYLOAD)
        return FakeResponse(MATCHES_PAYLOAD)


class FakeEspnSession:
    def get(self, url, params, timeout):
        return FakeResponse(ESPN_PAYLOAD)


class ErrorProvider(MatchProvider):
    def current_match(self):
        raise RuntimeError("rate limited")


def test_sample_provider_returns_config_hint():
    match = SampleProvider().current_match()
    assert match.status is MatchStatus.SCHEDULED
    assert match.source == "sample"
    assert "Configure" in (match.venue or "")


def test_football_data_provider_parses_match():
    session = FakeSession()
    provider = FootballDataProvider(Settings(football_data_token="token"), session=session)
    match = provider.current_match()

    assert match is not None
    assert match.status is MatchStatus.LIVE
    assert match.home_team.display_name == "FRA"
    assert match.away_team.display_name == "BRA"
    assert match.home_team.record_text == "2-1-0 • 7 pts"
    assert match.away_team.record_text == "1-1-1 • 4 pts"
    assert match.score_text == "1 - 0"
    assert match.kickoff == datetime(2026, 6, 22, 19, tzinfo=timezone.utc)
    assert session.headers["X-Auth-Token"] == "token"


def test_football_data_provider_infers_live_when_status_lags_after_kickoff():
    provider = FootballDataProvider(Settings(football_data_token="token"), session=FakeSession())
    kickoff = datetime.now(timezone.utc) - timedelta(minutes=8)

    status = provider._parse_status("TIMED", kickoff)

    assert status is MatchStatus.LIVE


def test_espn_scoreboard_provider_parses_live_score():
    match = EspnScoreboardProvider(session=FakeEspnSession()).current_match()

    assert match is not None
    assert match.status is MatchStatus.LIVE
    assert match.home_team.display_name == "NZL"
    assert match.away_team.display_name == "EGY"
    assert match.score_text == "1 - 0"
    assert match.status_text == "LIVE 17'"
    assert match.source == "espn"


def test_build_provider_without_token_uses_fallback():
    provider = build_provider(Settings(football_data_token=None))
    assert provider.primary is not None


def test_fallback_provider_keeps_last_primary_match_on_transient_error():
    provider = FallbackProvider(ErrorProvider(), SampleProvider())
    provider.last_primary_match = Match(
        competition="World Cup",
        home_team=Team("New Zealand", "NZL"),
        away_team=Team("Egypt", "EGY"),
        kickoff=datetime.now(timezone.utc) - timedelta(minutes=7),
        status=MatchStatus.LIVE,
        home_score=0,
        away_score=0,
        source="football-data.org",
    )

    match = provider.current_match()

    assert match.source == "football-data.org"
    assert match.status is MatchStatus.LIVE
    assert provider.last_error == "rate limited"
