import logging
import os

DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%H:%M:%S"

LEVEL_ENV_VAR = "TRAKER_LOG_LEVEL"


def configure(level=None, stream=None) -> None:
    """Attach one stderr handler to the root logger."""
    if level is None:
        level = os.environ.get(LEVEL_ENV_VAR, "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.strip().upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(h, "_traker_handler", False) for h in root.handlers):
        return

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT))
    handler._traker_handler = True
    root.addHandler(handler)
