# Focus timer and enforced breaks

There is one split for the whole day: 30 minutes of focus and 30 of break, with a 60-minute break that
may be queued twice a day. There are no timer modes. `:break long` makes the next break the long one,
`:break cancel` withdraws it, and `:break` reports how many the day has left; the choice applies to
the next break and is spent when that break begins. Contract: `specs/features/pomodoro_timer.feature`.

Absence is not focus, and a stop is not a click. Both are `[timer]` keys and apply whether or not
breaks take the screens. After `idle_pause_secs` (300, `0` disables) with neither a key nor the mouse,
the interval stops itself and the window that proved the absence is stored again as rest overtime,
which is the one case that rewrites a minute already stored. Any input carries the interval on from
where it stopped, together with the break behind it, and nothing is recorded in between. Stopping a
running interval by hand requires `stop_hold_secs` (10) held on the play button rather than clicked,
and that time is focus overtime like any other pause. Every `[strict_break]` key, its default and its
effect are documented in the profile the application generates on first run, and a value that cannot
be read as a number costs a warning in the log and the default, not the tab.

## Strict break behaviour

`strict` is disabled in a generated profile, and everything in this section applies only where
`strict = true`. A desktop or activity switch is reversed, and each wall is placed on every desktop
and activity by a KWin window rule, which is the one form of the request KWin applies rather than
refusing in silence. Every screen is covered, and none of the walls is the application window, which
stays where it was, behind them. The keyboard starts on the wall covering the screen the application
is on.

A wall refuses `Alt+F4` and the application refuses to quit, though terminating the process still
works. Switching a monitor off is not an exit: the walls are rebuilt once the screens settle, and an
untouched wall is left alone. Pause and skip are refused, and the screen states why. Holding `Esc`
for `release_hold_secs` abandons the break rather than postponing it, and the remaining time is
recorded as `overridden_break`. When the break ends the walls stay and give up the desktops, the
switch and the focus: the countdown alone becomes `BREAK OVER` and a count up from that end, every
other readout stands, a file goes on playing under the keys that drive it, and the press that starts
focus takes the walls away. A wall shows the current session, the chores that are due and, after
`away_secs`, a configured activity; the chore tick is the one break surface that writes.

## Break activities

A standing entry is a `[[strict_break.activities]]` table carrying a `name` and a `path`. One-off
entries go in the queue instead, at `rest-queue.m3u` under the dotted key `[strict_break.queue]`, one
path per line, so any process can append to it. `:rest <path>` queues an entry, `:rest` reads the
queue back, `:rest rm 2` drops one and `:rest clear` empties it. An entry stays queued until it is
removed, and the queue is read once when a break begins. Playback position is held in
`rest-positions.json`, as a position for a video, a page for a PDF, and the length, so a long film can
span several breaks. A film requires both the `video` extra (`uv sync --extra video`) and `libmpv`, a
system library (`media-video/mpv` with `USE="libmpv"`) that no lockfile carries. Without either, a
break still holds the screens and the screen that would show a film displays `COULD NOT PLAY`.

## Session verification

`scripts/check_desktop_integration.py` listens for a desktop switch; `--screens` reports the outputs
and the effect of a switch, `--release` clears what a crash during a break left behind, `--media`
reports what this machine gives the player, and `--idle` reports whether idle time is answered.
`journalctl --user -b -g 'traker:'` prints one `holding '<caption>' wall=… everyDesktop=…` line per
window. The script MUST be re-run after a Plasma upgrade. Mechanism and upstream refusals:
`docs/architecture/invariants.md` and `docs/guides/placing-the-window.md`.
