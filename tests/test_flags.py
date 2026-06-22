from datetime import datetime, timedelta, timezone

from world_cup_widget.flags import flag_for_code
from world_cup_widget.models import Match, MatchStatus, Team


def test_flag_for_fifa_code():
    assert flag_for_code("FRA") == "🇫🇷"
    assert flag_for_code("BRA") == "🇧🇷"
    assert flag_for_code("NZL") == "🇳🇿"


def test_flag_for_iso2_code():
    assert flag_for_code("US") == "🇺🇸"


def test_subdivision_flags_are_supported():
    assert flag_for_code("ENG")
    assert flag_for_code("SCO")
    assert flag_for_code("WAL")


def test_unknown_code_has_no_flag():
    assert flag_for_code(None) == ""
    assert flag_for_code("TBD") == ""


def test_team_display_name_with_flag():
    assert Team("France", "FRA").display_name_with_flag == "🇫🇷 FRA"
    assert Team("To be decided", "TBD").display_name_with_flag == "TBD"


def test_live_match_status_uses_elapsed_kickoff_minute():
    match = Match(
        competition="World Cup",
        home_team=Team("France", "FRA"),
        away_team=Team("Brazil", "BRA"),
        kickoff=datetime.now(timezone.utc) - timedelta(minutes=24, seconds=5),
        status=MatchStatus.LIVE,
    )

    assert match.live_minute in {25, 26}
    assert match.status_text.startswith("LIVE ")
    assert match.score_text == "0 - 0"
