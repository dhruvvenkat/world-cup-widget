# World Cup Widget

A native Python desktop widget that shows the current FIFA World Cup match. It uses PySide6/Qt, not HTML/CSS/JS.

## Features

- Frameless always-on-top desktop overlay with tray-controlled show/hide
- Drag to reposition
- Right-click menu with refresh and quit
- Polls for live or upcoming match data
- Uses Football-Data.org when configured
- Offline/sample fallback so the app still launches without an API token

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Live data configuration

Create a free API token at <https://www.football-data.org/> and put it in a local `.env` file:

```dotenv
FOOTBALL_DATA_TOKEN=your-token-here
```

Optional `.env` settings:

```dotenv
WORLD_CUP_COMPETITION=WC      # Football-Data competition code
WORLD_CUP_SEASON=2026         # Optional season filter
WORLD_CUP_REFRESH_SECONDS=60       # Normal polling interval
WORLD_CUP_LIVE_REFRESH_SECONDS=15  # Polling interval while a match is live
```

`.env` is ignored by git so your token stays local.

Without `FOOTBALL_DATA_TOKEN`, the widget displays a clearly-labelled sample fixture.

## Run

```bash
world-cup-widget
# or
python -m world_cup_widget.app
```

## Test

```bash
pytest
```

## Notes

Football match data APIs vary by tournament and licensing. The app keeps the UI independent from the provider, so if you prefer another feed later, add a new `MatchProvider` implementation in `src/world_cup_widget/provider.py`.
