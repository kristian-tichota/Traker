import logging
import shlex
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

PLACEHOLDER = "{state}"

TIMEOUT_SECS = 3.0

RETRY_SECS = (1, 2, 4, 8, 15, 30)


class StateHook:
    """Run a shell command per state, one run at a time, the latest state winning."""

    def __init__(self, command="", run=subprocess.run, retry_secs=RETRY_SECS):
        self.command = str(command or "").strip()
        self.told = None
        self._run = run
        self._retry_secs = tuple(retry_secs)
        self._heard = None
        self._failing = False
        self._closed = False
        self._newer = threading.Event()
        self._pool = (ThreadPoolExecutor(max_workers=1, thread_name_prefix="state-hook")
                      if self.command else None)

    def tell(self, state):
        """Hand state to the command, unless it is the state told last."""
        if self._closed or state == self.told:
            return
        self.told = state
        self._newer.set()
        if self._pool is not None:
            self._pool.submit(self._deliver)

    def tell_again(self):
        """Hand the state told last to the command once more, though it heard it."""
        if self._closed or self.told is None or self._pool is None:
            return
        self._pool.submit(self._deliver, True)

    def close(self):
        """Finish the runs still owed, then take no more states."""
        self._closed = True
        self._newer.set()
        if self._pool is not None:
            self._pool.shutdown(wait=True)

    def _deliver(self, again=False):
        """Run the command for the latest state, retrying a failure while it stays the latest."""
        self._newer.clear()
        state = self.told
        if state == self._heard and not again:
            return
        self._heard = state
        for wait in (*self._retry_secs, None):
            if self._ran(state) or wait is None or self._closed or self.told != state:
                return
            if self._newer.wait(wait):
                return

    def _ran(self, state) -> bool:
        """Run the command once for state, reporting whether it succeeded."""
        try:
            finished = self._run(self.command.replace(PLACEHOLDER, shlex.quote(state)),
                                 shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, text=True, timeout=TIMEOUT_SECS)
        except (OSError, subprocess.SubprocessError) as error:
            self._fail(state, str(error))
            return False
        if finished.returncode:
            said = (finished.stderr or "").strip().splitlines()
            self._fail(state, said[-1] if said else f"exit status {finished.returncode}")
            return False
        if self._failing:
            self._failing = False
            log.info("The state hook runs again.")
        return True

    def _fail(self, state, why):
        """Log the first failure of a run of them as a warning, and the rest quietly."""
        report = log.debug if self._failing else log.warning
        self._failing = True
        report("The state hook failed for %r: %s", state, why)
