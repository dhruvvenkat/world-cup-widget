from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .config import Settings
from .provider import build_provider
from .widget import WorldCupWidget


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("World Cup Widget")

    settings = Settings.from_env()
    widget = WorldCupWidget(build_provider(settings), refresh_seconds=settings.refresh_seconds)
    widget.move(80, 80)
    widget.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
