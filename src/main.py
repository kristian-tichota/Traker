import logging
import os
import sys

os.environ["QT_LOGGING_RULES"] = "qt.qpa.services=false;qt.qpa.services.warning=false"
os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import QLoggingCategory
from src.database import DatabaseClient
from src.desktop.kwin import release_stale_hold
from src.gui.main_window import MainWindow
from src.logging_setup import configure as configure_logging
from src.config import STYLESHEET, PALETTE
from backup import execute_safe_backup

log = logging.getLogger(__name__)


def create_solarized_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PALETTE['base3']))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE['base00']))
    palette.setColor(QPalette.ColorRole.Base, QColor(PALETTE['base3']))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PALETTE['base2']))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PALETTE['base3']))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(PALETTE['base00']))
    palette.setColor(QPalette.ColorRole.Text, QColor(PALETTE['base00']))
    palette.setColor(QPalette.ColorRole.Button, QColor(PALETTE['base2']))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(PALETTE['base01']))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PALETTE['base2']))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(PALETTE['base02']))
    return palette


def ensure_desktop_entry():
    desktop_dir = os.path.expanduser("~/.local/share/applications")
    desktop_file = os.path.join(desktop_dir, "Traker.desktop")
    if not os.path.exists(desktop_file):
        try:
            os.makedirs(desktop_dir, exist_ok=True)
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            entry_content = f"""[Desktop Entry]
Type=Application
Name=Traker
Exec={sys.executable} {os.path.join(root_dir, 'src', 'main.py')}
Path={root_dir}
Terminal=false
Categories=Utility;Health;
"""
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(entry_content)
        except OSError as e:
            log.warning("Could not write the desktop entry %s: %s", desktop_file, e)


def main():
    configure_logging()
    QLoggingCategory.setFilterRules("qt.qpa.services=false\nqt.qpa.services.warning=false")
    ensure_desktop_entry()

    execute_safe_backup()

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
