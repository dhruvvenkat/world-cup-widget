from datetime import datetime, timezone

from world_cup_widget.config import Settings
from world_cup_widget.models import MatchStatus
from world_cup_widget.provider import FootballDataProvider, SampleProvider, build_provider


def test_settings_loads_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FOOTBALL_DATA_TOKEN", raising=False)
    monkeypatch.delenv("WORLD_CUP_REFRESH_SECONDS", raising=False)
    tmp_path.joinpath(".env").write_text(
        "FOOTBALL_DATA_TOKEN=dotenv-token\nWORLD_CUP_REFRESH_SECONDS=45\n",
        encoding="utf-8",
    )

    settings = Settings.from_env()

    assert settings.football_data_token == "dotenv-token"
    assert settings.refresh_seconds == 45


class FakeResponse:
    status_code = 200
    text = "ok"

    def json(self):
        return {
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


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.params = None

    def get(self, url, params, timeout):
        self.params = params
        return FakeResponse()


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
    assert match.score_text == "1 - 0"
    assert match.kickoff == datetime(2026, 6, 22, 19, tzinfo=timezone.utc)
    assert session.headers["X-Auth-Token"] == "token"


def test_build_provider_without_token_uses_fallback():
    provider = build_provider(Settings(football_data_token=None))
    assert provider.primary is None
    assert provider.current_match().source == "sample"
