import logging
import shutil

log = logging.getLogger(__name__)

PROGRAM = "kscreen-doctor"


def _start(*arguments) -> bool:
    """Start kscreen-doctor with arguments, without waiting for it."""
    from PyQt6.QtCore import QProcess

    started, _pid = QProcess.startDetached(PROGRAM, list(arguments))
    return started


def _reachable() -> bool:
    """Report whether kscreen-doctor can switch outputs off on this session."""
    from PyQt6.QtGui import QGuiApplication

    return (QGuiApplication.platformName().startswith("wayland")
            and shutil.which(PROGRAM) is not None)


class ScreenPower:
    """Switches every output off through KWin, and on again when asked."""

    def __init__(self, start=None, reachable=None):
        self._start = _start if start is None else start
        self.available = (_reachable if reachable is None else reachable)()
        self.darkened = False

    def off(self) -> bool:
        """Switch every output off until the next key press or pointer movement."""
        if not self.available:
            log.debug("%s cannot switch the outputs off on this session.", PROGRAM)
            return False
        if not self._start("--dpms", "off"):
            log.warning("%s did not start; the screens stay on.", PROGRAM)
            return False
        self.darkened = True
        return True

    def wake(self):
        """Switch every output on, if this switched them off."""
        if not self.darkened:
            return
        self.darkened = False
        if not self._start("--dpms", "on"):
            log.warning("%s did not start; the screens stay off until a key is "
                        "pressed.", PROGRAM)
