from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QMenu, QVBoxLayout, QWidget

from .models import Match, MatchStatus
from .provider import FallbackProvider


class MatchFetchWorker(QThread):
    fetched = Signal(object, str)

    def __init__(self, provider: FallbackProvider) -> None:
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        match = self.provider.current_match()
        self.fetched.emit(match, self.provider.last_error or "")


class WorldCupWidget(QWidget):
    match_updated = Signal(object)

    def __init__(self, provider: FallbackProvider, refresh_seconds: int = 60, live_refresh_seconds: int = 15) -> None:
        super().__init__()
        self.provider = provider
        self.worker: MatchFetchWorker | None = None
        self.current_match: Match | None = None
        self.normal_refresh_ms = max(refresh_seconds, 10) * 1000
        self.live_refresh_ms = max(live_refresh_seconds, 5) * 1000
        self.drag_position = None
        self._closing = False

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

        self.setWindowTitle("World Cup Widget")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(340)

        self.title = QLabel("World Cup")
        self.title.setFont(QFont("Inter", 13, QFont.Bold))
        self.status = QLabel("Loading match...")
        self.status.setObjectName("status")
        self.home_team = QLabel("-")
        self.home_team.setFont(QFont("Inter", 18, QFont.Bold))
        self.home_record = QLabel("-")
        self.home_record.setObjectName("record")
        self.score = QLabel("vs")
        self.score.setFont(QFont("Inter", 28, QFont.Bold))
        self.away_team = QLabel("-")
        self.away_team.setFont(QFont("Inter", 18, QFont.Bold))
        self.away_record = QLabel("-")
        self.away_record.setObjectName("record")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.updated = QLabel("")
        self.updated.setObjectName("updated")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(7)
        for label in [self.title, self.status, self.detail, self.updated]:
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)

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
                border-radius: 22px;
            }
            QLabel { background: transparent; }
            QLabel#status { color: #38bdf8; font-weight: 700; }
            QLabel#record { color: #cbd5e1; font-size: 12px; }
            QLabel#updated { color: #94a3b8; font-size: 11px; }
        """)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.normal_refresh_ms)

        self.display_timer = QTimer(self)
        self.display_timer.timeout.connect(self.update_live_display)
        self.display_timer.start(1000)
        self.refresh()

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

    def render_match(self, match: Match | None, error: str = "") -> None:
        if self._closing:
            return
        if not match:
            self.current_match = None
            self.status.setText("No World Cup match found")
            self.home_team.setText("Check")
            self.away_team.setText("configuration")
            self.home_record.setText("-")
            self.away_record.setText("-")
            self.score.setText("-")
            self.detail.setText(error)
            return

        self.current_match = match
        self.title.setText(match.competition)
        self.update_live_display()
        if match.status is MatchStatus.LIVE:
            self.status.setStyleSheet("color: #ef4444;")
            self.timer.setInterval(self.live_refresh_ms)
        else:
            self.status.setStyleSheet("")
            self.timer.setInterval(self.normal_refresh_ms)
        self.home_team.setText(match.home_team.display_name_with_flag)
        self.home_record.setText(match.home_team.record_text)
        self.score.setText(match.score_text)
        self.away_team.setText(match.away_team.display_name_with_flag)
        self.away_record.setText(match.away_team.record_text)
        details = [part for part in [match.stage, match.venue, match.kickoff_text, f"Source: {match.source}"] if part]
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
                    self.current_match.stage,
                    self.current_match.venue,
                    self.current_match.kickoff_text,
                    f"Source: {self.current_match.source}",
                ]
                if part
            ))
        if self.current_match.status is MatchStatus.LIVE:
            self.match_updated.emit(self.current_match)

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        self.display_timer.stop()
        self.provider.close()
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
