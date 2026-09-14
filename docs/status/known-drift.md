# Known drift

Everything here was reproduced before it was written down. Items are **removed** when closed
rather than struck through — if it is here, it is open. Last audited 2026-09-13.

## Correctness
- A member's own catalog confirmation is overwritten by the stream's echo of it. A race: the same walk shows `:suppset` keeping its confirmation and `:mealset` losing it. The broadcast should carry the originating user.
- **No desktop or activity write from the KWin script lands on this Plasma 6.** Every spelling is written and read back, each refused in silence, while `keepAbove` in the same pass lands. `kwin_rules.py` goes round it with a window rule, so the break is unaffected; the script's `holdEverywhere()` is dead weight here and its `follow()` is the fallback with the rule off. **This is the open blocker.**
- What a real KWin does with the walls when the break's rule is narrowed or pruned under them is unmeasured. The suite proves the file and the reconfigure, not the compositor's answer.
- `tests/gui/test_modality.py::test_switching_tabs_does_not_take_the_mode_away` flakes about one run in ten *while another pytest competes for the machine*: `activeThreadCount()` can be non-zero the instant after `waitForDone` returns. The fix is in what `settled()` waits for.
- KWin's own **Screen** window rule cannot be used, and this is upstream: `checkOutput` is an index into a list rebuilt every boot, and an out-of-range index falls back silently. `WindowScreen` uses `sendClientToScreen` instead.
- `SyncListener.stop()` joins best-effort — `iter_lines` can sit on a closed socket, so the daemon thread may outlive the window. Deliberate; the bridge is disconnected first.

## Scale and performance
- **The live database is empty.** Benchmark against `scripts/seed_dev_db.py`, never the live database.
- The log tables download the whole ledger — ~5,900 rows, ~300 ms on the first visit to Food at projected scale, linear from there. Paging (`?limit=`/`?before=` behind `canFetchMore`) is the answer and is a behaviour change.
- A chart takes 143–576 ms on a worker thread. **Text is where it goes**: the calendar's 92 squares cost 12 ms as a `PatchCollection`, its 184 `ax.text` artists cost 178 ms. Hand-paint with `QPainter`, or update artists in place and lose the reset/draw split.
- The first `/` on a large table still folds on the interface thread if the warm has not landed.
- The tab reveal polls the thread pool rather than being told; a `refresh_finished` signal on `BaseManagedView` is the shape.
- `pomodoro_heartbeats.mode` is written by the route's default and read by nothing, and `pomodoro_*` is still the name in the store for a tab called the Focus Timer. Both are migrations for no behaviour.

## Missing, deliberate for now
- A set can be created and pruned from the GUI but not extended or renamed — there is no components POST. An `:setadd`/`:setrm` pair is the shape. All five domains, and cycles too.
- A meal set cannot be logged by mass: a recipe declares no total mass, so a mass could only be read as a proportion of one.
- An ad-hoc food's serving is nominally 100 g and the ledger shows that — noise rather than a lie, and the row is marked `~`.
- Only one training cycle is reachable: the one today falls in, otherwise the newest. A `:plan <name>` command is the shape.
- The Plans tab re-reads its cycle on every exercise write; its two per-plan reads are deliberately uncached because the cache's second key is a date bound.
- A filter is dropped on a tab change rather than remembered per tab.
- A chore cannot be anchored to a date in the month — the cadence is whole days, so "the last Sunday" cannot be said. A 28-day chore is the workaround.
- The tab strip does not fit: thirteen tabs with icons want 1951 px against the window's 1350. Shorter labels or less tab padding; neither changes anything a keyboard reaches.

## What the suite does not cover
- Nothing in the default suite runs against a live service — a defect needing a real socket is invisible to it. `tests/perf/` uses a real port but is deselected, and `scripts/walk_the_app.py` is run by hand.
- No benchmark runs in CI; no test asserts what a member *sees* on a chart. The appearance check is manual: render against a fixed seeded database, `git stash`, render again, compare PNGs — two runs of the *same* code differ by a few hundred pixels.
- **No test proves a real KWin honours the strict-break script.** The suite has no session bus; the script's own decisions run in `QJSEngine` against a stub session, which is the engine KWin uses but is not KWin. A wrong guess is no longer silent — the script reads each write back and prints one `holding '<caption>' wall=… everyDesktop=…` line per window. `scripts/check_desktop_integration.py` is how that gets checked, and it must be re-run after a Plasma upgrade.
- **Nothing proves this session answers how long the member has been idle.** The timer's absence handling is tested against an injected source; whether `org.freedesktop.ScreenSaver` answers `GetSessionIdleTime` on a real Plasma is `check_desktop_integration.py --idle`, by hand.
- Nothing proves the walls end up above the member's own window on a real break, that a second screen's wall is held, that KRunner and the panels stay behind one, or that the warning is audible.
- Which wall the keyboard starts on is a guess about where the member is: `_member_screen()` answers the output holding Traker's window, which is the closest a Wayland client gets.
- **Playing a video is not proved anywhere.** The panes are built and driven against a real PDF, and mpv's failure path against a missing file, but no test decodes a frame — the repository ships no media. Whether it *sounds* right was settled on the member's own desktop, 12.09.2026, and nowhere else. mpv's full GL path also errors on a software renderer and needs `gpu-dumb-mode`.
- What a break's screen looks like is proved on X11, not Wayland: the offscreen plugin answers for neither stacking nor geometry.
- A break does not survive a restart — nothing persists "holding until T", so killing the client mid-break is an exit with no debt recorded. `pkill`, a VT switch and logout all still end one.
- The command bar cannot be typed into during a break, and a key sheet left open stays open behind the wall. Both deliberate; both are capabilities that went.
- A profile written for the old launcher loses its standing entries, with the only notice in the log.
- Nothing pins how the sets panes, the chore panel or the tab icons *look*; only the Food ledger's headings have a pixel test.
- `walk_the_app.py`'s chore commands are load-sensitive — under a competing `pytest` the walk occasionally reads back too early.
- The chore board is read whole, every time: `GET /api/chores` takes no `?since=`.
- `test_command_parser.py` has 131 tests for one pure module. Not wrong, but it is where the marginal test has been going.
