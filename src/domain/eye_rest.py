from dataclasses import dataclass
from typing import NamedTuple

GAZE = "LOOK FAR AWAY"
READY = "GET READY"
READY_MS = 3000

SET_REPETITIONS = 15


CLOSE = "close"
OPEN = "open"
SQUEEZE = "squeeze"
LOOK = "look"


class Step(NamedTuple):
    """One instruction of a routine, how long it is held, and the eyes' motion."""

    said: str
    ms: int
    motion: str


BLINK_CYCLE = (Step("CLOSE GENTLY", 2000, CLOSE), Step("OPEN", 2000, OPEN),
               Step("CLOSE GENTLY", 2000, CLOSE), Step("SQUEEZE", 2000, SQUEEZE),
               Step("OPEN", 2000, OPEN))

SET_REPETITION = (Step("CLOSE", 2000, CLOSE), Step("SQUEEZE", 2000, SQUEEZE),
                  Step("OPEN", 2000, OPEN))


def look_away(gaze_ms) -> tuple:
    """Return a rest: one blink cycle, then a gaze into the distance."""
    return BLINK_CYCLE + (Step(GAZE, max(0, int(gaze_ms)), LOOK),)


def blink_set(repetitions=SET_REPETITIONS) -> tuple:
    """Return a paced set of close-squeeze-open repetitions."""
    return SET_REPETITION * max(1, int(repetitions))


def length_ms(routine) -> int:
    return sum(step.ms for step in routine)


def step_at(routine, elapsed_ms):
    """Return (index, ms left in it) at elapsed_ms, or None after the routine."""
    left = max(0, int(elapsed_ms))
    for index, step in enumerate(routine):
        if left < step.ms:
            return index, step.ms - left
        left -= step.ms
    return None


@dataclass
class ScreenTime:
    """Screen time since the eyes last rested."""

    every_ms: int
    rested_after_ms: int
    screen_ms: int = 0

    def advance(self, delta_ms, away_ms) -> bool:
        """Count delta_ms unless the eyes have been away long enough; report a rest due."""
        if away_ms >= self.rested_after_ms:
            self.screen_ms = 0
            return False
        self.screen_ms += max(0, int(delta_ms))
        return self.screen_ms >= self.every_ms

    def rested(self):
        self.screen_ms = 0
