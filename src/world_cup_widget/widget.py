from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QFont
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

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
    def __init__(self, provider: FallbackProvider, refresh_seconds: int = 60) -> None:
        super().__init__()
        self.provider = provider
        self.worker: MatchFetchWorker | None = None
        self.drag_position = None

        self.setWindowTitle("World Cup Widget")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(340)

        self.title = QLabel("World Cup")
        self.title.setFont(QFont("Inter", 13, QFont.Bold))
        self.status = QLabel("Loading match...")
        self.status.setObjectName("status")
        self.teams = QLabel("-")
        self.teams.setFont(QFont("Inter", 18, QFont.Bold))
        self.score = QLabel("vs")
        self.score.setFont(QFont("Inter", 28, QFont.Bold))
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.updated = QLabel("")
        self.updated.setObjectName("updated")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(7)
        for label in [self.title, self.status, self.teams, self.score, self.detail, self.updated]:
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(18, 24, 38, 232);
                color: #f8fafc;
                border-radius: 22px;
            }
            QLabel { background: transparent; }
            QLabel#status { color: #38bdf8; font-weight: 700; }
            QLabel#updated { color: #94a3b8; font-size: 11px; }
        """)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(max(refresh_seconds, 10) * 1000)
        self.refresh()

    def refresh(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.status.setText("Refreshing...")
        self.worker = MatchFetchWorker(self.provider)
        self.worker.fetched.connect(self.render_match)
        self.worker.start()

    def render_match(self, match: Match | None, error: str = "") -> None:
        if not match:
            self.status.setText("No World Cup match found")
            self.teams.setText("Check configuration")
            self.score.setText("-")
            self.detail.setText(error)
            return

        self.title.setText(match.competition)
        self.status.setText(match.status_text)
        if match.status is MatchStatus.LIVE:
            self.status.setStyleSheet("color: #ef4444;")
        else:
            self.status.setStyleSheet("")
        self.teams.setText(f"{match.home_team.display_name}  •  {match.away_team.display_name}")
        self.score.setText(match.score_text)
        details = [part for part in [match.stage, match.venue, match.kickoff_text, f"Source: {match.source}"] if part]
        if error:
            details.append(f"Fallback active: {error}")
        self.detail.setText("\n".join(details))
        self.updated.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")

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
