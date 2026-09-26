# Focus timer and enforced breaks

There is one split for the whole day, with a long break that may be queued a set number of times a
day. There are no timer modes. `:break long` makes the next break the long one, `:break cancel`
withdraws it, and `:break` reports how many the day has left; the choice is spent when that break
begins. Contract: `specs/features/pomodoro_timer.feature`. The generated profile documents every key.

Absence is not focus, and a stop is not a click, whether or not breaks take the screens. After
`idle_pause_secs` with neither a key nor the mouse, the interval stops itself and the window that
proved the absence is stored again as rest overtime, the one case that rewrites a stored minute. Any
input carries the interval on, together with the break behind it. Stopping a running interval
requires `stop_hold_secs` held on the play button, and that time is focus overtime.

## Strict break behaviour

Everything in this section applies only where `strict = true`. A desktop or activity switch is
reversed, and each wall is placed on every desktop and activity by a KWin window rule, the one form of
the request KWin applies rather than refusing in silence. Every screen is covered; the application
window stays behind the walls, and the keyboard starts on the wall covering its screen.

A wall refuses `Alt+F4` and the application refuses to quit, though terminating the process still
works. A monitor switched off is not an exit: the walls are rebuilt once the screens settle. Pause and
skip are refused. Holding `Esc` for `release_hold_secs` abandons the break, and the remaining time is
recorded as `overridden_break`. When the break ends the walls stay but give up the desktops, the
switch and the focus: the countdown becomes `BREAK OVER` and a count up, a file goes on playing, and
the press that starts focus takes the walls away. A wall shows the session, the chores that are due
and, after `away_secs`, the offers; the chore tick is the one surface that writes to the service.

## Break activities

Offers come in key order: the queue, the `[[strict_break.activities]]` entries, then one shelf per
subfolder of the media folder, `Media/` in the checkout unless `[strict_break.library]` names another.
A shelf opens the file opened last in it or, once that one reached its end, the next by name. The
queue is `rest-queue.m3u`, one path per line, so any process can append to it; `:rest` reads, extends
and prunes it. Positions are kept in `rest-positions.json`, so a film or a book spans several breaks.

A film needs the `video` extra and the system `libmpv` (`media-video/mpv` with `USE="libmpv"`), which
no lockfile carries; an EPUB and an Anki deck need QtWebEngine, the `anki` extra. Without them the
screen displays `COULD NOT PLAY`, `COULD NOT READ` or `COULD NOT REVIEW`, and the break still holds.
An EPUB is set in CSS columns on a Solarized light page in the middle of the screen, and its position
is a share of its text, so a changed page size keeps the place.

A deck is reviewed by Anki's own reviewer through AnkiConnect at `anki_url`, which chooses, schedules
and sounds every card; the wall draws it and forwards the keys.
A `deck` of `*` lists every deck first. Anki MUST be running, its window MAY stay minimized, and its
timebox MUST be 0.

## Session verification

`scripts/check_desktop_integration.py` listens for a desktop switch; `--screens`, `--release`,
`--media` and `--idle` report the outputs, clear what a crashed break left behind, and report what the
player gets and whether idle time is answered. `journalctl --user -b -g 'traker:'` prints one
`holding '<caption>' wall=… everyDesktop=…` line per window. The script MUST be re-run after a
Plasma upgrade. Mechanism: `docs/architecture/invariants.md` and `placing-the-window.md`.
