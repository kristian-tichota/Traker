import logging

from src.desktop.session import session_call

log = logging.getLogger(__name__)

SCREENSAVER = "org.freedesktop.ScreenSaver"
SCREENSAVER_PATH = "/ScreenSaver"

_unanswered = False


def idle_ms():
    """Return milliseconds since the session last saw input, or None."""
    global _unanswered
    if _unanswered:
        return None

    answered, away = session_call(SCREENSAVER, SCREENSAVER_PATH, SCREENSAVER,
                                  "GetSessionIdleTime")
    if not answered or away is None:
        _unanswered = True
        log.info("%s does not say how long this session has been idle: the "
                 "timer will not pause itself on an absence.", SCREENSAVER)
        return None
    return int(away)
