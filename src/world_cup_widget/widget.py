from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from .models import Match, MatchStatus
from .provider import FallbackProvider

COMIC_FONT = "Comic Sans MS"


class MatchFetchWorker(QThread):
    fetched = Signal(object, str)

    def __init__(self, provider: FallbackProvider) -> None:
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        match = self.provider.current_match()
        self.fetched.emit(match, self.provider.last_error or "")


class UpcomingFetchWorker(QThread):
    fetched = Signal(object)

    def __init__(self, provider: FallbackProvider) -> None:
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        self.fetched.emit(self.provider.upcoming_matches(5))


class LiveUnderline(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.offset = 0
        self.setFixedHeight(5)
        self.setVisible(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def set_active(self, active: bool) -> None:
        self.setVisible(active)
        if active and not self.timer.isActive():
            self.timer.start(28)
        elif not active:
            self.timer.stop()
            self.offset = 0
            self.update()

    def tick(self) -> None:
        self.offset = (self.offset + 4) % max(self.width(), 1)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self.isVisible():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(239, 68, 68), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        width = max(self.width(), 1)
        segment = max(width // 3, 48)
        x = width - self.offset
        painter.drawLine(x, 2, x - segment, 2)
        if x - segment < 0:
            painter.drawLine(width + x, 2, width + x - segment, 2)


class HoverLabel(QLabel):
    hovered = Signal(bool)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.hovered.emit(False)
        super().leaveEvent(event)


class StandingsPopup(QFrame):
    def __init__(self) -> None:
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 10, 14, 10)
        self.layout.setSpacing(4)
        self.setStyleSheet('''
            QFrame {
                background: transparent;
                border-radius: 12px;
                color: #f8fafc;
                font-family: "Comic Sans MS", "Comic Neue", "Comic Relief", cursive;
            }
            QLabel { background: transparent; }
        ''')

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)
        painter.fillPath(path, QColor(2, 6, 23, 235))
        painter.setPen(QPen(QColor(248, 113, 113, 190), 1))
        painter.drawPath(path)
        super().paintEvent(event)

    def set_match(self, match: Match) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        title = QLabel(match.group_label or "Group")
        title.setFont(QFont(COMIC_FONT, 12, QFont.Bold))
        self.layout.addWidget(title)
        if not match.group_standings:
            self.layout.addWidget(QLabel("Standings unavailable"))
            return
        for entry in match.group_standings:
            prefix = f"{entry.position}. " if entry.position else ""
            self.layout.addWidget(QLabel(f"{prefix}{entry.team.display_name_with_flag}  {entry.record.display_text}"))


class WorldCupWidget(QWidget):
    match_updated = Signal(object)

    def __init__(self, provider: FallbackProvider, refresh_seconds: int = 60, live_refresh_seconds: int = 15) -> None:
        super().__init__()
        self.provider = provider
        self.worker: MatchFetchWorker | None = None
        self.upcoming_worker: UpcomingFetchWorker | None = None
        self.current_match: Match | None = None
        self.normal_refresh_ms = max(refresh_seconds, 10) * 1000
        self.live_refresh_ms = max(live_refresh_seconds, 5) * 1000
        self.drag_position = None
        self._closing = False

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

        self.setWindowTitle("World Cup Widget")
        self.setWindowFlags(self._overlay_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumWidth(340)

        self.title = QLabel("World Cup")
        self.title.setFont(QFont(COMIC_FONT, 13, QFont.Bold))
        self.status = QLabel("Loading match...")
        self.status.setObjectName("status")
        self.live_underline = LiveUnderline()
        self.home_team = QLabel("-")
        self.home_team.setFont(QFont(COMIC_FONT, 18, QFont.Bold))
        self.home_record = QLabel("-")
        self.home_record.setObjectName("record")
        self.score = QLabel("vs")
        self.score.setFont(QFont(COMIC_FONT, 28, QFont.Bold))
        self.away_team = QLabel("-")
        self.away_team.setFont(QFont(COMIC_FONT, 18, QFont.Bold))
        self.away_record = QLabel("-")
        self.away_record.setObjectName("record")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.group_detail = HoverLabel("")
        self.group_detail.setObjectName("groupDetail")
        self.group_detail.setVisible(False)
        self.group_detail.hovered.connect(self.toggle_standings_popup)
        self.standings_popup = StandingsPopup()
        self.updated = QLabel("")
        self.updated.setObjectName("updated")
        self.upcoming_button = QPushButton("Upcoming ▾")
        self.upcoming_button.setObjectName("dropdownButton")
        self.upcoming_button.clicked.connect(self.toggle_upcoming_dropdown)
        self.upcoming_dropdown = QFrame(self)
        self.upcoming_dropdown.setObjectName("dropdown")
        self.upcoming_dropdown_layout = QVBoxLayout(self.upcoming_dropdown)
        self.upcoming_dropdown_layout.setContentsMargins(10, 8, 10, 8)
        self.upcoming_dropdown_layout.setSpacing(3)
        self.upcoming_dropdown.setMinimumHeight(0)
        self.upcoming_dropdown.setMaximumHeight(0)
        self.upcoming_dropdown.hide()

        layout = QVBoxLayout(self)
        self.main_layout = layout
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(7)
        for label in [self.title, self.status, self.group_detail, self.detail, self.updated]:
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            if label is self.status:
                layout.addWidget(self.live_underline)
            if label is self.detail:
                layout.addWidget(self.upcoming_button)

        match_grid = QGridLayout()
        match_grid.setHorizontalSpacing(14)
        match_grid.setVerticalSpacing(2)
        for label in [self.home_team, self.home_record, self.score, self.away_team, self.away_record]:
            label.setAlignment(Qt.AlignCenter)
        match_grid.addWidget(self.home_team, 0, 0)
        match_grid.addWidget(self.score, 0, 1, 2, 1)
        match_grid.addWidget(self.away_team, 0, 2)
        match_grid.addWidget(self.home_record, 1, 0)
        match_grid.addWidget(self.away_record, 1, 2)
        layout.insertLayout(2, match_grid)

        self.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #f8fafc;
                font-family: "Comic Sans MS", "Comic Neue", "Comic Relief", cursive;
                border-radius: 22px;
            }
            QLabel { background: transparent; }
            QLabel#status { color: #38bdf8; font-weight: 700; }
            QLabel#record { color: #cbd5e1; font-size: 12px; }
            QLabel#groupDetail { color: #fca5a5; font-weight: 700; }
            QLabel#updated { color: #94a3b8; font-size: 11px; }
            QPushButton#dropdownButton {
                background-color: rgba(15, 23, 42, 180);
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 130);
                border-radius: 10px;
                padding: 4px 8px;
            }
            QFrame#dropdown {
                background-color: rgba(15, 23, 42, 210);
                border: 1px solid rgba(148, 163, 184, 120);
                border-radius: 10px;
            }
        """)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.normal_refresh_ms)

        self.display_timer = QTimer(self)
        self.display_timer.timeout.connect(self.update_live_display)
        self.display_timer.start(1000)

        self.on_top_timer = QTimer(self)
        self.on_top_timer.timeout.connect(self.reinforce_always_on_top)
        self.on_top_timer.start(2000)
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        QTimer.singleShot(0, self.reinforce_always_on_top)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().changeEvent(event)
        if self.isVisible() and not self.isMinimized():
            QTimer.singleShot(0, self.reinforce_always_on_top)

    def reinforce_always_on_top(self) -> None:
        if self._closing or not self.isVisible() or self.isMinimized():
            return
        required_flags = self._overlay_flags()
        if self.windowFlags() & required_flags != required_flags:
            self.setWindowFlags(self.windowFlags() | required_flags)
            self.show()
        self.raise_()
        self._reinforce_x11_above_state()

    def _overlay_flags(self) -> Qt.WindowType:
        return Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus

    def _reinforce_x11_above_state(self) -> None:
        if not os.getenv("DISPLAY") or not shutil.which("wmctrl"):
            return
        try:
            window_id = hex(int(self.winId()))
            subprocess.run(
                ["wmctrl", "-i", "-r", window_id, "-b", "add,above,sticky"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.2,
            )
        except Exception:
            pass

    def refresh(self) -> None:
        if self._closing:
            return
        if self.worker and self._worker_is_running():
            return
        self.status.setText("Refreshing...")
        self.worker = MatchFetchWorker(self.provider)
        self.worker.fetched.connect(self.render_match)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _worker_finished(self) -> None:
        self.worker = None

    def _upcoming_worker_finished(self) -> None:
        self.upcoming_worker = None

    def toggle_upcoming_dropdown(self) -> None:
        if self.upcoming_dropdown.isVisible():
            self.upcoming_dropdown.hide()
            self.upcoming_dropdown.setMinimumHeight(0)
            self.upcoming_dropdown.setMaximumHeight(0)
            self.main_layout.removeWidget(self.upcoming_dropdown)
            self.upcoming_button.setText("Upcoming ▾")
            self._clear_upcoming_rows()
            self._resize_to_contents()
            return
        self.upcoming_dropdown.setMinimumHeight(0)
        self.upcoming_dropdown.setMaximumHeight(16777215)
        self.main_layout.insertWidget(self.main_layout.indexOf(self.upcoming_button) + 1, self.upcoming_dropdown)
        self.upcoming_dropdown.show()
        self.upcoming_button.setText("Upcoming ▴")
        self._set_upcoming_rows(["Loading..."])
        self._resize_to_contents()
        if self.upcoming_worker and self.upcoming_worker.isRunning():
            return
        self.upcoming_worker = UpcomingFetchWorker(self.provider)
        self.upcoming_worker.fetched.connect(self.render_upcoming_matches)
        self.upcoming_worker.finished.connect(self._upcoming_worker_finished)
        self.upcoming_worker.start()

    def render_upcoming_matches(self, matches: list[Match]) -> None:
        if not matches:
            self._set_upcoming_rows(["No upcoming matches"])
            self._resize_to_contents()
            return
        self._set_upcoming_rows([self._format_upcoming_match(match) for match in matches[:5]])
        self._resize_to_contents()

    def _format_upcoming_match(self, match: Match) -> str:
        kickoff = match.kickoff.astimezone().strftime("%a %H:%M") if match.kickoff else "TBD"
        return f"{kickoff} · {match.home_team.display_name_with_flag} vs {match.away_team.display_name_with_flag}"

    def _set_upcoming_rows(self, rows: list[str]) -> None:
        self._clear_upcoming_rows()
        for row in rows:
            label = QLabel(row)
            label.setWordWrap(False)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumHeight(24)
            self.upcoming_dropdown_layout.addWidget(label)

    def _clear_upcoming_rows(self) -> None:
        while self.upcoming_dropdown_layout.count():
            item = self.upcoming_dropdown_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _resize_to_contents(self) -> None:
        self.layout().activate()
        self.adjustSize()
        self.updateGeometry()

    def render_match(self, match: Match | None, error: str = "") -> None:
        if self._closing:
            return
        if not match:
            self.live_underline.set_active(False)
            self.current_match = None
            self.status.setText("No World Cup match found")
            self.home_team.setText("Check")
            self.away_team.setText("configuration")
            self.home_record.setText("-")
            self.away_record.setText("-")
            self.score.setText("-")
            self.detail.setText(error)
            self.group_detail.hide()
            return

        self.current_match = match
        self.title.setText(match.competition)
        self.update_live_display()
        if match.status is MatchStatus.LIVE:
            self.status.setStyleSheet("color: #ef4444;")
            self.live_underline.set_active(True)
            self.timer.setInterval(self.live_refresh_ms)
        else:
            self.status.setStyleSheet("")
            self.live_underline.set_active(False)
            self.timer.setInterval(self.normal_refresh_ms)
        self.home_team.setText(match.home_team.display_name_with_flag)
        self.home_record.setText(match.home_team.record_text)
        self.score.setText(match.score_text)
        self.away_team.setText(match.away_team.display_name_with_flag)
        self.away_record.setText(match.away_team.record_text)
        self.group_detail.setText(match.group_label or "")
        self.group_detail.setVisible(bool(match.group_label))
        details = [part for part in [match.venue, match.kickoff_text] if part]
        if error:
            details.append(f"Fallback active: {error}")
        self.detail.setText("\n".join(details))
        self.updated.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")
        self.match_updated.emit(match)

    def update_live_display(self) -> None:
        if not self.current_match or self._closing:
            return
        self.status.setText(self.current_match.status_text)
        if self.current_match.status is MatchStatus.SCHEDULED:
            self.detail.setText("\n".join(
                part
                for part in [
                    self.current_match.venue,
                    self.current_match.kickoff_text,
                ]
                if part
            ))
        if self.current_match.status is MatchStatus.LIVE:
            self.match_updated.emit(self.current_match)

    def toggle_standings_popup(self, show: bool) -> None:
        if not show or not self.current_match or not self.current_match.group_label:
            self.standings_popup.hide()
            return
        self.standings_popup.set_match(self.current_match)
        top_right = self.mapToGlobal(self.rect().topRight())
        self.standings_popup.move(top_right.x() + 10, top_right.y())
        self.standings_popup.show()

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        self.display_timer.stop()
        self.on_top_timer.stop()
        self.live_underline.set_active(False)
        self.standings_popup.hide()
        self.provider.close()
        if self.upcoming_worker and self.upcoming_worker.isRunning():
            self.upcoming_worker.terminate()
            self.upcoming_worker.wait(250)
            self.upcoming_worker = None
        if self.worker and self._worker_is_running():
            try:
                self.worker.fetched.disconnect(self.render_match)
            except RuntimeError:
                pass
            self.worker.wait(250)
            if self.worker and self._worker_is_running():
                self.worker.terminate()
                self.worker.wait(250)
            self.worker = None
        if self.upcoming_worker and self.upcoming_worker.isRunning():
            self.upcoming_worker.terminate()
            self.upcoming_worker = None

    def _worker_is_running(self) -> bool:
        try:
            return bool(self.worker and self.worker.isRunning())
        except RuntimeError:
            self.worker = None
            return False

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.shutdown()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 22, 22)
        painter.fillPath(path, QColor(2, 6, 23, 205))
        super().paintEvent(event)

    def fast_exit(self, exit_code: int = 0) -> None:
        """Exit immediately for development interrupts.

        Qt can otherwise wait on worker-thread cleanup while a request is in
        flight. For Ctrl+C/Escape during development, prefer process exit over
        graceful cleanup latency.
        """
        self._closing = True
        self.timer.stop()
        self.display_timer.stop()
        self.on_top_timer.stop()
        self.live_underline.set_active(False)
        self.standings_popup.hide()
        try:
            self.provider.close()
        except Exception:
            pass
        if self.worker and self._worker_is_running():
            try:
                self.worker.fetched.disconnect(self.render_match)
            except RuntimeError:
                pass
            self.worker.terminate()
            self.worker = None
        os._exit(exit_code)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() == Qt.Key_Escape:
            self.fast_exit(0)
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt API name
        menu = QMenu(self)
        refresh_action = QAction("Refresh now", self)
        refresh_action.triggered.connect(self.refresh)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(refresh_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        menu.exec(QCursor.pos())

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.buttons() == Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
