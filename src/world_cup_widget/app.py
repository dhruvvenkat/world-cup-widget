from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .config import Settings
from .provider import build_provider
from .tray import TrayIndicator
from .widget import WorldCupWidget


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("World Cup Widget")

    settings = Settings.from_env()
    widget = WorldCupWidget(
        build_provider(settings),
        refresh_seconds=settings.refresh_seconds,
        live_refresh_seconds=settings.live_refresh_seconds,
    )
    widget.move(80, 80)
    widget.show()
    tray = TrayIndicator(widget)
    tray.show()
    app.tray_indicator = tray  # keep alive for the lifetime of QApplication

    # Qt's event loop can otherwise delay Python signal handling. This no-op
    # timer keeps Ctrl+C responsive while developing from a terminal.
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(100)

    def handle_sigint(signum, frame) -> None:  # noqa: ARG001
        widget.fast_exit(130)

    signal.signal(signal.SIGINT, handle_sigint)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
