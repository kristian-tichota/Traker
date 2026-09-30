import logging
import time

from src.desktop.session import session_call

log = logging.getLogger(__name__)

SCREENSAVER = "org.freedesktop.ScreenSaver"
SCREENSAVER_PATH = "/ScreenSaver"
RETRY_S = 60.0

_quiet_until = 0.0


def idle_ms():
    """Return milliseconds since the session last saw input, or None."""
    global _quiet_until
    if time.monotonic() < _quiet_until:
        return None

    answered, away = session_call(SCREENSAVER, SCREENSAVER_PATH, SCREENSAVER,
                                  "GetSessionIdleTime")
    if not answered or away is None:
        if not _quiet_until:
            log.info("%s does not say how long this session has been idle: the timer "
                     "does not pause itself on an absence until it answers.", SCREENSAVER)
        _quiet_until = time.monotonic() + RETRY_S
        return None
    return int(away)
