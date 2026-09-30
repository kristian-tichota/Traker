from PyQt6.QtCore import QTimer


def stop_timers(widget) -> None:
    """Stop every QTimer parented anywhere under widget."""
    for timer in widget.findChildren(QTimer):
        timer.stop()


class LatchesShutdown:
    """The _shut_down flag the two mixins below both set, and both read."""

    _shut_down = False

    def is_shut_down(self) -> bool:
        """Report whether shutdown() has latched, so teardown restarts nothing."""
        return self._shut_down

    def shutdown(self):
        self._shut_down = True


class ShutdownMixin(LatchesShutdown):
    """Gives a view a shutdown() that stops its timers."""

    def shutdown(self):
        super().shutdown()
        stop_timers(self)


class PausesWhenHidden(LatchesShutdown):
    """Runs an animation timer only while the widget is on screen."""

    paused_timer_attribute = None

    paused_timer_interval_ms = 30

    def _paused_timer(self):
        name = self.paused_timer_attribute
        return getattr(self, name, None) if name else None

    def resume_animation(self):
        timer = self._paused_timer()
        if timer is not None:
            timer.start(self.paused_timer_interval_ms)

    def pause_animation(self):
        timer = self._paused_timer()
        if timer is not None:
            timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.is_shut_down():
            self.resume_animation()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.pause_animation()

    def shutdown(self):
        super().shutdown()
        self.pause_animation()
