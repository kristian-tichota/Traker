import logging
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

PLACEHOLDER = "{state}"

TIMEOUT_SECS = 3.0


class StateHook:
    """Run a shell command per state, one run at a time, the latest state winning."""

    def __init__(self, command="", run=subprocess.run):
        self.command = str(command or "").strip()
        self.told = None
        self._run = run
        self._heard = None
        self._failing = False
        self._closed = False
        self._pool = (ThreadPoolExecutor(max_workers=1, thread_name_prefix="state-hook")
                      if self.command else None)

    def tell(self, state):
        """Hand state to the command, unless it is the state told last."""
        if self._closed or state == self.told:
            return
        self.told = state
        if self._pool is not None:
            self._pool.submit(self._deliver)

    def close(self):
        """Finish the runs still owed, then take no more states."""
        self._closed = True
        if self._pool is not None:
            self._pool.shutdown(wait=True)

    def _deliver(self):
        """Run the command for the latest state, unless the command already heard it."""
        state = self.told
        if state == self._heard:
            return
        self._heard = state
        try:
            finished = self._run(self.command.replace(PLACEHOLDER, shlex.quote(state)),
                                 shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, text=True, timeout=TIMEOUT_SECS)
        except (OSError, subprocess.SubprocessError) as error:
            self._fail(state, str(error))
            return
        if finished.returncode:
            said = (finished.stderr or "").strip().splitlines()
            self._fail(state, said[-1] if said else f"exit status {finished.returncode}")
        elif self._failing:
            self._failing = False
            log.info("The state hook runs again.")

    def _fail(self, state, why):
        """Log the first failure of a run of them as a warning, and the rest quietly."""
        report = log.debug if self._failing else log.warning
        self._failing = True
        report("The state hook failed for %r: %s", state, why)
