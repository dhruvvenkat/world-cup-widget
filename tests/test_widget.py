from datetime import datetime, timezone

from PySide6.QtWidgets import QApplication, QLabel

from world_cup_widget.models import Match, MatchStatus, StandingEntry, Team, TeamRecord
from world_cup_widget.widget import WorldCupWidget


class StaticProvider:
    last_error = None

    def __init__(self, match):
        self.match = match

    def current_match(self):
        return self.match

    def close(self):
        pass


def get_app():
    return QApplication.instance() or QApplication([])


def test_live_underline_runs_only_during_active_live_play():
    app = get_app()
    live_match = Match(
        "World Cup",
        Team("New Zealand", "NZL"),
        Team("Egypt", "EGY"),
        datetime.now(timezone.utc),
        MatchStatus.LIVE,
        1,
        0,
        group="GROUP_G",
        group_standings=(
            StandingEntry(Team("New Zealand", "NZL"), TeamRecord(1, 1, 0, 4), 1),
            StandingEntry(Team("Egypt", "EGY"), TeamRecord(0, 1, 1, 1), 2),
        ),
    )
    widget = WorldCupWidget(StaticProvider(live_match), refresh_seconds=60, live_refresh_seconds=5)
    while widget.worker and widget._worker_is_running():
        app.processEvents()
    app.processEvents()

    assert not widget.live_underline.isHidden()
    assert widget.live_underline.timer.isActive()
    assert widget.group_detail.text() == "Group G"
    widget.toggle_standings_popup(True)
    assert widget.standings_popup.isVisible()
    popup_text = "\n".join(label.text() for label in widget.standings_popup.findChildren(QLabel))
    assert "NZL" in popup_text
    assert "EGY" in popup_text
    widget.toggle_standings_popup(False)
    assert not widget.standings_popup.isVisible()

    halftime_match = Match("World Cup", Team("New Zealand", "NZL"), Team("Egypt", "EGY"), datetime.now(timezone.utc), MatchStatus.PAUSED, 1, 0)
    widget.render_match(halftime_match)

    assert widget.live_underline.isHidden()
    assert not widget.live_underline.timer.isActive()
    assert widget.status.text() == "Halftime"
    widget.shutdown()
