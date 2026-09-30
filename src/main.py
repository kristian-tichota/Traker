import logging
import os
import sys

os.environ["QT_LOGGING_RULES"] = "qt.qpa.services=false;qt.qpa.services.warning=false"
os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt
from src.database import DatabaseClient
from src.desktop.kwin import release_stale_hold
from src.gui.main_window import MainWindow
from src.logging_setup import configure as configure_logging
from src.config import STYLESHEET, PALETTE
from backup import execute_safe_backup

log = logging.getLogger(__name__)


PALETTE_ROLES = {
    "Window": "base3", "WindowText": "base00", "Base": "base3", "AlternateBase": "base2",
    "ToolTipBase": "base3", "ToolTipText": "base00", "Text": "base00", "Button": "base2",
    "ButtonText": "base01", "Highlight": "base2", "HighlightedText": "base02",
}


def create_solarized_palette() -> QPalette:
    palette = QPalette()
    for role, colour in PALETTE_ROLES.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(PALETTE[colour]))
    return palette


def ensure_desktop_entry():
    desktop_dir = os.path.expanduser("~/.local/share/applications")
    desktop_file = os.path.join(desktop_dir, "Traker.desktop")
    if not os.path.exists(desktop_file):
        try:
            os.makedirs(desktop_dir, exist_ok=True)
            entry_content = f"""[Desktop Entry]
Type=Application
Name=Traker
Exec={sys.executable} {os.path.join(ROOT_DIR, 'src', 'main.py')}
Path={ROOT_DIR}
Terminal=false
Categories=Utility;Health;
"""
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(entry_content)
        except OSError as e:
            log.warning("Could not write the desktop entry %s: %s", desktop_file, e)


def main():
    configure_logging()
    ensure_desktop_entry()

    execute_safe_backup()

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(create_solarized_palette())
    app.setStyleSheet(STYLESHEET)
    app.setDesktopFileName("Traker.desktop")

    release_stale_hold()

    db = DatabaseClient()
    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
