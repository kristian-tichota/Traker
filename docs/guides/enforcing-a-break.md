# Focus timer and enforced breaks

There is one split for the whole day, with a long break that may be queued a set number of times a
day. `:break long` makes the next break the long one, `:break cancel` withdraws it, and `:break`
reports how many the day has left. Contract: `specs/features/pomodoro_timer.feature`. The generated
profile documents every key.

After `idle_pause_secs` without input, a focus interval stops itself and that window is stored again
as rest overtime, the one case that rewrites a stored minute. Stopping a running interval by hand
requires `stop_hold_secs` held on the play button, and that time is focus overtime. `I'm Away` stops
focus and raises a break's walls in any mode; the wait is rest overtime, and one `Esc` takes the walls
down and runs focus on from where it stopped.

## Strict break behaviour

Everything in this section applies only where `strict = true`. A desktop or activity switch is
reversed, and a KWin window rule places each wall on every desktop and activity. Every screen is
covered; the application window stays behind the walls, and the keyboard starts on the wall covering
its screen. The walls hold Plasma's Do Not Disturb through `Notifications.Inhibit` and ask a
restarted notification server again; Plasma drops the hold when Traker exits. On Wayland,
`screens_off_key` switches the monitors off until the next key press, which reaches nothing else, a
pointer movement or the end of the break.

Holding `Esc` for `release_hold_secs` abandons the break, records the remaining time as
`overridden_break` and runs focus at once. Running focus is focus overtime until the moment the break
would have ended; a second early exit owes the later of the two moments, not their sum. When the
break ends the walls stay but give up the desktops, the switch and the focus: the countdown becomes
`BREAK OVER` and a count up in a frame on each wall that shows no activity, faint at first and at
full size after `over_ramp_secs`, a file goes on playing, and the press that starts focus takes the
walls away. A wall shows the session, the chores that are due and, after `away_secs`, the offers; a
pressed offer glows, yellow while the offers are held back. The chore tick is the one surface that
writes to the service.

`Ctrl+Shift+F5` on a wall restarts Traker to load new code. The walls fall for the few seconds the
start takes, then rise again with the break's clock, an absence or `BREAK OVER` as they stood, what
was showing reopened and an attached session reattached. The state is saved in
`standing-break.json` beside the queue and MUST be taken within two minutes, or it is ignored.

## Break activities

Offers come in key order: the queue, the `[[strict_break.activities]]` entries, then one shelf per
subfolder of the media folder, `Media/` in the checkout unless `[strict_break.library]` names another.
A shelf lists its folder, the file opened last marked or, once that one ended, the next by name; the
list climbs to the media folder, and 0 returns from a file to it. `Ctrl+Home` returns from any depth,
a page and a session included, to the wall's readouts. The pointer is hidden on the walls except
over a web page. Each row of a list of decks or of a
folder carries a hint made from `hint_keys` less the chores' letters; typing it opens the row. The
queue is `rest-queue.m3u`, one path per line, so any process can append to it; `:rest` reads, extends
and prunes it. Positions are kept in `rest-positions.json`, so a film or a book spans several breaks.

A film needs the `video` extra and the system `libmpv` (`media-video/mpv` with `USE="libmpv"`), which
no lockfile carries; an EPUB, an Anki deck, a web page and a terminal need QtWebEngine, the `anki`
extra. Without them the screen displays `COULD NOT PLAY`, `COULD NOT READ`, `COULD NOT REVIEW` or
`COULD NOT OPEN`, and the break still holds.

A deck is reviewed by Anki's own reviewer through AnkiConnect at `anki_url`; a `deck` of `*` lists
every deck first. Anki MUST be running, its window MAY stay minimized, and its timebox MUST be 0.

A `url` opens as a web page that takes every key except `Esc` and `Ctrl+0`, which puts the wall back.
It stays loaded until the walls go, and Traker writes none of its storage to disk. A `sessions`
program runs its sessions in a terminal: the pane is xterm.js from `assets/xterm/` over a
pseudo-terminal that `setsid --ctty` (util-linux) makes the program's own, and a tap of `Esc` shorter
than `TAP_MS` reaches the session. The program's two calls are in the generated profile.

## Ambience

`[strict_break.ambience]` names a scene of the bank, the checkout's `Ambience` folder unless `path`
names another. A scene is a folder of recordings, each with its gain and the span that plays in
`scene.toml`; `scripts/fetch_ambience.py` downloads the curated scenes from Freesound once, with
their credits, and playback reads only these files. Each recording plays from places chosen at
random with 6 s crossfades, its level drifting between 50 % and 125 %, and `noise` is generated. The
Focus Timer tab's SOUND panel and `:sound` play a scene at any time, on through breaks until stopped.
The mix renders at 48 kHz on its own thread through Qt Multimedia, soxr resampling any recording at
another rate, and needs the `ambience` extra.

## Assistive Input Integration

`[hooks] state` is a shell command run each time what the break shows changes, with `{state}` replaced
by `focus`, `break`, `list`, `video`, `document`, `book`, `deck`, `page` or `terminal`. While an activity is open,
every other wall fades to a grey face with the time left by the minute, what is showing and its keys.
Each key names the libre-dictum inputs that send it, read from that program's display socket at
`LIBRE_DICTUM_HUD_SOCKET` or `$XDG_RUNTIME_DIR/libre-dictum/hud.sock`; another protocol names none.
When that socket returns after a loss, the hook hears the current state again, and a failing run is
retried for about a minute while its state is still the latest.

## Session verification

`scripts/check_desktop_integration.py` listens for a desktop switch; `--screens`, `--release`,
`--media`, `--idle` and `--notifications` check the outputs, a crashed break, the player, the idle
time and Do Not Disturb. The script MUST be re-run after a Plasma upgrade. Mechanism:
`docs/architecture/invariants.md` and `placing-the-window.md`.
