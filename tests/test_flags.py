from world_cup_widget.flags import flag_for_code
from world_cup_widget.models import Team


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
