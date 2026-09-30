import contextlib
import os
import shutil
import tempfile


def write(path, text):
    """Replace a file's text in one rename, so no reader or crash sees half of it."""
    target = os.path.realpath(path)
    folder = os.path.dirname(target)
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".", suffix=".part")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(text)
        if os.path.exists(target):
            shutil.copymode(target, temporary)
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temporary)
        raise
