#!/usr/bin/env python3

import logging
import traceback
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

log = logging.getLogger(__name__)

_in_flight = set()

_reaper = None


class _Reaper(QObject):
    """Releases a finished worker, on the GUI thread."""

    @pyqtSlot(object)
    def retire(self, worker):
        _in_flight.discard(worker)


def _reaper_instance() -> "_Reaper":
    global _reaper
    if _reaper is None:
        _reaper = _Reaper()
    return _reaper


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)


class DbWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # broad: the thread boundary, where anything else is lost
            log.exception("%s raised on a worker thread", getattr(self.fn, '__name__', self.fn))
            self.signals.error.emit((e, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit(self)


def run_in_background(pool, fn, on_result, on_error=None, *args, **kwargs) -> DbWorker:
    """Run fn off the UI thread and wire both of its outcomes."""
    worker = DbWorker(fn, *args, **kwargs)
    worker.signals.result.connect(on_result)
    worker.signals.error.connect(on_error if on_error is not None else _log_worker_error)

    worker.signals.finished.connect(_reaper_instance().retire)
    _in_flight.add(worker)
    pool.start(worker)
    return worker


def discard(_outcome):
    """Discard the result of a write whose only reported outcome is failure."""


def _log_worker_error(failure):
    error, formatted = failure
    logging.getLogger(__name__).error("Background call failed: %s\n%s", error, formatted)
