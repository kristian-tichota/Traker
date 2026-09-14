import datetime
import logging

from PyQt6.QtCore import QTimer

from src.desktop import kde_config
from src.desktop.session import session_call
from src.domain.clock import minutes_of_day, within_window
from src.profile import UserProfile

log = logging.getLogger(__name__)

SERVICE = "org.kde.KWin"
EFFECTS_PATH = "/Effects"
EFFECTS = "org.kde.kwin.Effects"

EFFECT = "colorblindnesscorrection"
EFFECT_GROUP = f"Effect-{EFFECT}"
PLUGINS_GROUP = "Plugins"
ENABLED_KEY = f"{EFFECT}Enabled"

MONOCHROME = 3

DEFAULT_FROM = "20:00"
DEFAULT_TO = "06:00"
DEFAULT_INTENSITY = 1.0

# KWin rolls an intensity of zero over to full; off is the effect unloaded.
MIN_INTENSITY = 0.05

TICK_MS = 60_000


def switched_on(profile) -> bool:
    """Whether [grayscale] is asked for at all, whatever the hour is."""
    return profile.get_metric("grayscale", "enabled", False) is True


def wanted_at(profile, at) -> bool:
    """Whether the screens should be grey at the given datetime."""
    if not switched_on(profile):
        return False
    start = minutes_of_day(profile.get_metric("grayscale", "from", DEFAULT_FROM))
    end = minutes_of_day(profile.get_metric("grayscale", "to", DEFAULT_TO))
    if start is None or end is None:
        log.warning("[grayscale] from/to are not both HH:MM; the screens are "
                    "left in colour.")
        return False
    return within_window(at.hour * 60 + at.minute, start, end)


class NightFilter:
    """Follows the clock, and asks KWin for grey when it crosses into the hours."""

    def __init__(self, caller=None, clock=None):
        self._call = caller or session_call
        self._now = clock or datetime.datetime.now
        self._asked_for = None
        self._tick = QTimer()
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self.follow_the_clock)

    def begin(self):
        """Start following the clock, from wherever it happens to be now."""
        self.follow_the_clock()
        self._tick.start()

    def stop(self):
        """Stop following it, and leave the screens exactly as they are."""
        self._tick.stop()

    def follow_the_clock(self):
        """Ask for what the hour calls for, if that is not what was asked last."""
        profile = UserProfile()
        if not switched_on(profile) and self._asked_for is None:
            self._asked_for = False
            return

        wanted = wanted_at(profile, self._now())
        if wanted == self._asked_for:
            return
        intensity = profile.number("grayscale", "intensity", DEFAULT_INTENSITY,
                                   low=MIN_INTENSITY, high=1.0)
        if self.apply(wanted, intensity):
            self._asked_for = wanted

    def apply(self, grey, intensity=DEFAULT_INTENSITY) -> bool:
        """Write it down and then ask for it."""
        self._persist(grey, intensity)
        method = "loadEffect" if grey else "unloadEffect"
        reached, took = self._call(SERVICE, EFFECTS_PATH, EFFECTS, method, EFFECT)
        if not reached:
            log.info("No KWin to take the screens' colour away; nothing here "
                     "applies on this session.")
            return False
        if grey:
            if took is False:
                log.warning("KWin would not load %s; the screens keep their "
                            "colour.", EFFECT)
                return False
            self._call(SERVICE, EFFECTS_PATH, EFFECTS, "reconfigureEffect", EFFECT)
        log.info("[grayscale]: the screens are %s.",
                 "monochrome" if grey else "in colour again")
        return True

    def _persist(self, grey, intensity) -> bool:
        """The two kwinrc groups, edited rather than replaced."""
        path = kde_config.KWINRC_PATH
        before = kde_config.text(path)
        if before is None:
            return False
        after = before
        if grey:
            after = kde_config.with_keys(after, EFFECT_GROUP, (
                ("Mode", str(MONOCHROME)),
                ("Intensity", f"{intensity:g}"),
            ))
        after = kde_config.with_keys(
            after, PLUGINS_GROUP, ((ENABLED_KEY, "true" if grey else "false"),))
        return after == before or kde_config.store(path, after)
