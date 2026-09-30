# Focus timer and enforced breaks

There is one split for the whole day, with a long break that may be queued a set number of times a
day. There are no timer modes. `:break long` makes the next break the long one, `:break cancel`
withdraws it, and `:break` reports how many the day has left; the choice is spent when that break
begins. Contract: `specs/features/pomodoro_timer.feature`. The generated profile documents every key.

After `idle_pause_secs` without input, a focus interval stops itself and that window is stored again
as rest overtime, the one case that rewrites a stored minute. Stopping a running interval by hand
requires `stop_hold_secs` held on the play button, and that time is focus overtime.

## Strict break behaviour

Everything in this section applies only where `strict = true`. A desktop or activity switch is
reversed, and a KWin window rule places each wall on every desktop and activity. Every screen is
covered; the application window stays behind the walls, and the keyboard starts on the wall covering
its screen. The walls hold Plasma's Do Not Disturb through `Notifications.Inhibit` and ask a
restarted notification server again; Plasma drops the hold when Traker exits.

Holding `Esc` for `release_hold_secs` abandons the break, and the remaining time is recorded as
`overridden_break`. When the break ends the walls stay but give up the desktops, the switch and the
focus: the countdown becomes `BREAK OVER` and a count up in a blue frame on each wall that shows no
activity, a file goes on playing, and the press that starts focus takes the walls away. A wall shows
the session, the chores that are due and, after `away_secs`, the offers; a pressed offer glows,
yellow while the offers are held back. The chore tick is the one surface that writes to the service.

## Break activities

Offers come in key order: the queue, the `[[strict_break.activities]]` entries, then one shelf per
subfolder of the media folder, `Media/` in the checkout unless `[strict_break.library]` names another.
A shelf lists its folder, the file opened last marked or, once that one ended, the next by name; the
list climbs to the media folder, and 0 returns from a file to it. The queue is `rest-queue.m3u`, one
path per line, so any process can append to it; `:rest` reads, extends and prunes it. Positions are
kept in `rest-positions.json`, so a film or a book spans several breaks.

A film needs the `video` extra and the system `libmpv` (`media-video/mpv` with `USE="libmpv"`), which
no lockfile carries; an EPUB, an Anki deck and a web page need QtWebEngine, the `anki` extra. Without
them the screen displays `COULD NOT PLAY`, `COULD NOT READ`, `COULD NOT REVIEW` or `COULD NOT OPEN`,
and the break still holds.

A deck is reviewed by Anki's own reviewer through AnkiConnect at `anki_url`, which chooses, schedules
and sounds every card; the wall draws it in Solarized light, forwards the keys and confirms each
answer on the next card. A `deck` of `*` lists every deck first. Anki MUST be running, its window MAY
stay minimized, and its timebox MUST be 0.

A `url` opens as a web page that takes every key except `Esc` and `Ctrl+0`, which puts the wall back.
It stays loaded until the walls go, and Traker writes none of its storage to disk.

## State hook

`[hooks] state` is a shell command run each time what the break shows changes, with `{state}` replaced
by `focus`, `break`, `video`, `document`, `book`, `deck` or `page`. Runs go one at a time off the
interface thread; a burst of changes is one run of its last state, and quitting tells `focus`.

## Session verification

`scripts/check_desktop_integration.py` listens for a desktop switch; `--screens`, `--release`,
`--media`, `--idle` and `--notifications` report the outputs, clear what a crashed break left
behind, and check the player, the idle time and Do Not Disturb. `journalctl --user -b -g 'traker:'`
prints one `holding '<caption>' wall=… everyDesktop=…` line per window. The script MUST be re-run
after a Plasma upgrade. Mechanism: `docs/architecture/invariants.md` and `placing-the-window.md`.
