import logging
import os
import tomllib

log = logging.getLogger(__name__)

LOCAL_SERVER_URL = "http://127.0.0.1:6035"


def _load_server_creds():
    """Resolve credentials from the environment, then the profile, then the default."""
    from src.profile import PROFILE_PATH

    url = os.environ.get("TRAKER_SERVER_URL")
    token = os.environ.get("TRAKER_API_TOKEN")

    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "rb") as f:
                data = tomllib.load(f)
            server_cfg = data.get("server", {})
            url = url or server_cfg.get("url")
            token = token or server_cfg.get("token")
        except OSError as e:
            log.warning("Could not read %s: %s", PROFILE_PATH, e)
        except tomllib.TOMLDecodeError as e:
            log.warning("Could not parse server settings in %s: %s", PROFILE_PATH, e)

    return url or LOCAL_SERVER_URL, token or ""

SERVER_URL, API_TOKEN = _load_server_creds()

CAFFEINE_HALF_LIFE = 5.0
SLEEP_CAFFEINE_THRESHOLD = 20.0

PALETTE = {
    "base03": "#002b36", "base02": "#073642", "base01": "#586e75", "base00": "#657b83",
    "base0": "#839496",  "base1": "#93a1a1",  "base2": "#eee8d5",  "base3": "#fdf6e3",
    "yellow": "#b58900", "orange": "#cb4b16", "red": "#dc322f",    "magenta": "#d33682",
    "violet": "#6c71c4", "blue": "#268bd2",   "cyan": "#2aa198",   "green": "#859900",
}

STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {PALETTE['base3']};
    color: {PALETTE['base00']};
}}
QTabWidget {{
    background-color: {PALETTE['base3']};
}}
QTabWidget::pane {{
    background-color: {PALETTE['base3']};
    border: 1px solid {PALETTE['base1']};
    top: -1px;
}}
QTabWidget > QWidget {{
    background-color: {PALETTE['base3']};
    color: {PALETTE['base00']};
}}
QTableView {{
    background-color: {PALETTE['base3']};
    color: {PALETTE['base00']};
    gridline-color: {PALETTE['base2']};
    selection-background-color: {PALETTE['base2']};
    selection-color: {PALETTE['base02']};
    border: 1px solid {PALETTE['base1']};
    font-family: 'Fira Code', monospace;
    font-size: 12px;
}}
QHeaderView::section {{
    background-color: {PALETTE['base2']};
    color: {PALETTE['base01']};
    padding: 5px;
    border: 1px solid {PALETTE['base1']};
    font-weight: bold;
}}
QLineEdit {{
    background-color: {PALETTE['base2']};
    color: {PALETTE['base03']};
    border: 1px solid {PALETTE['base1']};
    border-radius: 2px;
    padding: 6px;
    font-family: 'Fira Code', monospace;
}}
QLabel {{
    color: {PALETTE['base00']};
    font-family: 'Fira Code', monospace;
}}
QTabBar::tab {{
    background: {PALETTE['base2']};
    color: {PALETTE['base01']};
    padding: 8px 16px;
    border: 1px solid {PALETTE['base1']};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: {PALETTE['base3']};
    color: {PALETTE['base00']};
    font-weight: bold;
}}
QComboBox {{
    background-color: {PALETTE['base2']};
    color: {PALETTE['base00']};
    border: 1px solid {PALETTE['base1']};
    border-radius: 2px;
    padding: 3px 6px;
    font-family: 'Fira Code', monospace;
}}
"""
