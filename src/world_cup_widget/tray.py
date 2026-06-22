from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .models import Match
from .widget import WorldCupWidget


class TrayIndicator:
    """Native system tray/status-area indicator for the current match.

    On some Linux desktops, especially stock GNOME, tray icons only appear when
    AppIndicator/tray support is enabled by the desktop shell.
    """

    def __init__(self, widget: WorldCupWidget) -> None:
        self.widget = widget
        self.tray = QSystemTrayIcon(self._make_icon(), widget)
        self.tray.setToolTip("World Cup Widget: loading match...")

        self.menu = QMenu()
        self.summary_action = QAction("Loading match...", self.menu)
        self.summary_action.setEnabled(False)
        self.toggle_action = QAction("Hide widget", self.menu)
        self.toggle_action.triggered.connect(self.toggle_widget)
        refresh_action = QAction("Refresh now", self.menu)
        refresh_action.triggered.connect(widget.refresh)
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(QApplication.quit)

        self.menu.addAction(self.summary_action)
        self.menu.addSeparator()
        self.menu.addAction(self.toggle_action)
        self.menu.addAction(refresh_action)
        self.menu.addSeparator()
        self.menu.addAction(quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        widget.match_updated.connect(self.update_match)

    def show(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def update_match(self, match: Match) -> None:
        text = self._summary(match)
        self.tray.setToolTip(text)
        self.summary_action.setText(text)
        self.tray.setIcon(self._make_icon(match.score_text))

    def toggle_widget(self) -> None:
        if self.widget.isVisible():
            self.widget.hide()
            self.toggle_action.setText("Show widget")
        else:
            self.widget.show()
            self.widget.raise_()
            self.widget.reinforce_always_on_top()
            self.toggle_action.setText("Hide widget")

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick}:
            self.toggle_widget()

    def _summary(self, match: Match) -> str:
        return (
            f"{match.home_team.display_name} {match.score_text} {match.away_team.display_name}\n"
            f"{match.home_team.record_text} | {match.away_team.record_text}\n"
            f"{match.status_text}"
        )

    def _make_icon(self, text: str = "⚽") -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(2, 6, 23, 230))
        painter.setPen(QColor(56, 189, 248))
        painter.drawEllipse(3, 3, 58, 58)
        painter.setPen(QColor(248, 250, 252))
        font = QFont("Inter", 18, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text if len(text) <= 3 else "⚽")
        painter.end()
        return QIcon(pixmap)
