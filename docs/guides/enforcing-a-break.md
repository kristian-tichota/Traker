# The timer, enforcing a break, and leaving one

One split, all day: **30 minutes of focus, 30 of break**, with a **60-minute break you can queue twice a day**. No timer modes. `:break long` makes the next break the long one, `:break cancel` takes it back, `:break` says how many the day has left; it applies to the *next* break and is spent when that one begins. Contract: `specs/features/pomodoro_timer.feature`.

**Walking away is not focus, and a stop is not a click.** Both are `[timer]` keys, and both apply
whether or not breaks take the screens. After `idle_pause_secs` (300, `0` off) with neither a key
nor the mouse, the interval stops itself and the window that proved it is stored again as *rest*
overtime — the one thing that rewrites a minute already stored. Touching anything carries the
interval on from where it stopped, the break behind it with it, and nothing lands while you are
gone. Stopping a running interval by hand is `stop_hold_secs` (10) held on the play button rather
than clicked, and that time is focus overtime like any other pause.

**`strict` is off in a generated profile.** Everything below is what `strict = true` buys.

## For a member
- It **does not let you go**: a desktop or activity switch is put straight back, by Traker over D-Bus and by the KWin script where one loaded. `refuse_switch = false` leaves the older answer, where the break merely *follows* you.
- It **is already there when you get there** — each wall is put on every desktop and activity by a KWin *window rule*, the one form of the request KWin applies itself instead of refusing in silence. The desktops come out of it the moment the break runs out; the rest of it goes with the walls.
- It is **every screen**, and none of them is Traker: your own window stays where you had it, behind the walls. The keyboard starts on the wall covering the screen Traker is on.
- **Closing it is not an exit.** A wall refuses `Alt+F4` and the application refuses to quit. Killing the process still works, and nothing here pretends otherwise.
- **Switching a monitor off is not a way out** — the walls are rebuilt a fraction of a second after the screens settle; a wall you did not touch is left alone, so a film on it is undisturbed.
- **Pause and skip are refused**, and the screen says why. **Sixty seconds before it lands you hear about it**, as an ordinary notification with a sound.
- **Hold `Esc` for ten seconds** to leave. The break is then abandoned, not postponed, and the time left on it is recorded as `overridden_break`.
- **When it runs out the walls stay and stop holding anything** — they say `BREAK OVER` and the one key to press, and they stay in front of every screen while they say it. The desktops go back, the switch is not put back, the focus is yours; the view is not. A screen that cleared itself would be you back at work without deciding to be.
- It shows **today's session**, **the chores that are due** (and takes the tick — the one break surface that writes), and, after `away_secs` of nothing, **something you told it to show**.

| Key | Default | What it changes |
| --- | --- | --- |
| `warn_secs` | `60` | Seconds of audible warning; `0` off |
| `release_hold_secs` | `10` | How long `Esc` must be held; clamped 1–60 |
| `away_secs` | `300` | Seconds before anything is offered, proportional to the break's length |
| `sound_name` / `sound_file` | `dialog-warning` / — | The warning's sound; a file wins over a name |
| `app_id` | `""` | What KWin calls Traker's windows; empty asks Qt |
| `media_screen` | `""` | Output a file opens on; empty follows `[window] screen`, then Qt's primary |
| `refuse_switch` / `pin_with_rule` | `true` | Whether a switch is put back; whether a rule pins the walls |
| `activities` / `queue.path` | none / `""` | Standing entries and their keys; where the queue file is |

A number that cannot be read as one costs a warning in the log and the default, not the tab.

## Something to do while it holds

Only what you wrote down, and only when you press its key. The **first offer is `Enter`**, the rest `1`–`9`; a key with no offer is left alone. While something is showing: `Space` pauses or turns the page, `←`/`→` step 30 seconds or a page, `↑`/`↓` are volume or scroll, `0` gives the wall back. A card in the corner of the *other* walls names them — never over the picture.

```toml
[[strict_break.activities]]
name = "Reading"
path = "~/Documents/reading.pdf"       # a PDF is read; anything else is played
```

Two videos you found this morning go in the **queue** instead — `rest-queue.m3u`, one path per line, so anything can append to it. `:rest <path>` queues, `:rest` reads it back, `:rest rm 2` drops one, `:rest clear` empties it. An item stays queued until you remove it, and the queue is read once when a break begins. The header is a dotted key: `[strict_break.queue]`.

**Where you stopped is remembered** in `rest-positions.json` — a position for a video, a page for a PDF, and the length, so a forty-minute film spans three breaks. A film needs both the `video` extra (`uv sync --extra video`) and `libmpv`, a system library (`media-video/mpv` with `USE="libmpv"`) that no lockfile carries; without either, a break still holds the screens and the screen that would show a film says `COULD NOT PLAY`.

## Checking your own session

```bash
uv run python scripts/check_desktop_integration.py            # listen, then switch desktop
uv run python scripts/check_desktop_integration.py --screens  # outputs, and what a switch does
uv run python scripts/check_desktop_integration.py --release  # after a crash mid-break
uv run python scripts/check_desktop_integration.py --media    # what this machine gives the player
uv run python scripts/check_desktop_integration.py --idle     # whether it says how long you have been away
```

`journalctl --user -b -g 'traker:'` prints one `holding '<caption>' wall=… everyDesktop=…` line per window. Re-run the script after a Plasma upgrade. Mechanism and the upstream refusals: `docs/architecture/invariants.md`, `docs/guides/placing-the-window.md`, `docs/status/known-drift.md`.
