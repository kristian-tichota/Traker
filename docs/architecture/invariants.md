# Invariants

Break one of these and the failure is silent, or fatal, or both.

## Threading and lifetime
- No network call on the interface thread; background work starts only through `run_in_background`, which wires `error` as well as `result` and holds the worker alive until `finished`.
- A worker's result receiver is a **named callable, never a lambda** — PyQt keeps a lambda's connection to a destroyed receiver, and an exception in a slot or a `paintEvent` aborts the interpreter. Bind extra state in the payload or in a receiver per case, never in a closure; `tests/gui/test_main_window.py` walks the AST to keep it true.
- Shutdown order: `closeEvent` → listener `stop()` → view `shutdown()` → `waitForDone` → widgets. `stop_timers` reaches `QTimer`s only, so `ChangeGlow` is stopped by hand first.
- `PausesWhenHidden`: create the timer in `__init__`, start it in `showEvent` — Qt sends no `hideEvent` to a widget never shown, and a `QTabWidget` shows only its current tab. Never read Qt state back to decide what to do either: `isVisible()` answers for the whole parent chain.

## Correctness
- One write gate, and anything *derived* on the way to the store goes back through it. A write that matched no row is a 404. A route raises `BadPayload`/`BadValue`; it does not build the answer.
- SQLite puts `"12o"` in a `REAL` column where `CHECK(x >= 0)` then passes, and stores `1e400` as `inf`. `coerce_value` refuses both at the boundary.
- A number that appears in two readouts is one function in `src/domain/`, with a test asserting they agree. Grep for the *quantity*, not the function name.
- A food log stores whichever of `servings`/`grams` the member typed; storing servings always would silently rewrite the mass they weighed.
- `CREATE TABLE IF NOT EXISTS` never alters an existing table, so anything added later needs an explicit migration in `init_db`, in foreign-key order. Deleting a catalog item a set uses is refused with 409; every other log→item reference is `ON DELETE SET NULL`, because orphaning history beats erasing it.
- A break's two key ranges may not overlap: `Enter`/`1`-`9` are activity offers, `a`-`z` tick chores, and each list must leave a key it has nothing behind unconsumed.
- A wall is a wall because of its title (`WALL_CAPTION`). Walls get `keepAbove` and the focus, the member's own window gets neither — KWin stacks an *active fullscreen* window above a kept-above one. A break is asked for by app id, and a wrong one is silent.

## Invalidation and cache
- The object that owns a cache drops it, keyed by domain rather than table — a catalog write drops that domain's *log* reads too, because a food's energy is what every food log's kcal derives from.
- A read that failed is never cached and there is no TTL: the cache drops on this member's own write, a `catalog_updated`, the service returning, and an explicit refresh.
- **Only one unbounded read per domain may be cached.** The second key is a `since` date bound, not a free-form key, so two of them share `(domain, None)` and answer each other — silently, with rows of the wrong shape.

## The modality
- `set_mode` is the only way into a mode, `MODES` the only list of them, and a mode is entered by the transition rather than by a focus event. A mode does not outlive its tab; half-typed command text does.
- The readout is `mode_label`, never `status_bar` — fourteen things write the status line and none puts a mode back. Leaving a mode takes the keyboard back too: `clearFocus()` leaves the window with no focus widget, and the tab keys are read by `MainWindow`.

## What the compositor lies about
- `w.output` is stale after a drag: `Window::setOutput` is the only emitter of `outputChanged`, and an interactive move ends in `sendToOutput(moveResizeOutput())`. Decide by frame geometry, and watch `interactiveMoveResizeFinished`.
- **Nothing a script writes for a desktop or an activity lands on this Plasma**, and a refused property write raises nothing. Read every write back. The pin is a window rule for that reason; the *output* is a script for the opposite one, because KWin's rule for it is an index into a list rebuilt each boot.
- Traker's rules go first in `[General] rules=`: `Rules::checkSetStop` means the first rule to set a value is the last word on it.
- A rule matches on the window's title, never the application — every Traker window carries one class, so a class-matched rule reaches a break's walls. And a rule is not instant: `Workspace::reconfigure` debounces by 200 ms.
- A monitor switched off is an output *withdrawn*, and the one that returns is a new `QScreen`; anything holding the old one raises `RuntimeError` from a Qt slot. Let go inside the signal, rebuild once the burst settles, key a wall to the output's name.

## Rendering and the table
- A `QSS` type selector matches a class *and its subclasses*, so re-basing or renaming a widget can leave a rule matching nothing, with no error.
- A date column is coupled in two directions: the model renders ISO as Czech for `DATE_HEADERS` and `on_cell_edited` reads Czech back off the same tuple. Rows keep ISO, because the sort reads the value.
- A column added to a ledger, or reordered in one, is coupled in four places and only two fail loudly — a view's `headers` and a `Command`'s `OptimisticRow.fields` are silent.
- A column layout is a permutation of the **header**, never of the model, and the header *is* the state. A programmatic `moveSection` emits `sectionMoved`, so applying a stored layout would store it again unless suppressed.
- The filter and the sort read the typed value, never the rendered string — `"9.00" > "312.40"` is true. A chart's read/reset/draw run on a pool thread and may touch the figure; only `prepare_refresh` may touch a widget, and `ChartCanvas.render_lock` is taken without blocking.
- `repaint()` on a widget never shown does nothing, so a paint test written that way asserts nothing — render into a `QPixmap`. Likewise `show()` on a visible widget sends no `showEvent`.
- **The first GL child of a window already on a screen has Qt destroy and recreate that window** — a frame of bare desktop, and a `ForceTemporarily` rule discarded with the window it matched. A wall carries a hidden `QOpenGLWidget` from birth so the film's is never the first.
- A break plays through **libmpv**, into a GL surface of our own window: the proc-address resolver must be held on the instance, and `update_cb`/`end-file` arrive on mpv's threads so both cross by signal. A file is handed over only once `initializeGL` has run.
- **Nothing a widget paints is visible over the picture** — every readout is on the walls beside the film, and a break with one screen keeps them in rows under it. A machine without libmpv must still hold a break, so `VideoPane` says `COULD NOT PLAY` rather than raising.
- A `QPdfView` page asked for before the document is laid out moves the page *number* and not the picture, so a resumed page is re-asked at every moment the view offers one.

## The command grammar
- An argument with a `default` may be left out, so the Tab split cannot use the declared argument count and a required argument after an optional one must validate its own shape. A recogniser matches the shape, not the validity: recognise loosely, refuse precisely.
- A command with a `window_effect` never reaches `invoke` — its subject is the tab in front of the member, which only the window can resolve. `name_position(text)` is a function of what was typed, not a property of the command.
- The menu and the greyed hint rank once and read the same index, or Tab writes a command the member can see is not the one picked. Tab may only *append* when what was typed is the name's own opening under `COLLATE NOCASE` folding.

## Conventions
- **Solarized only**, and no literal hex in widget code — `PALETTE` in `src/config.py`. Matplotlib takes `facecolor=PALETTE['base3']`, with `base01`/`base2` for spines and grids.
- **Dates:** ISO at the API and the SQLite boundary, Czech `DD.MM.YYYY` in anything a member sees. `src/domain/clock.py` is the conversion, once.
- **PyQt6 only.** The Wayland overlays depend on `WA_TranslucentBackground`.
- **No raw SQL in GUI code.** A new query is a server route plus a `DatabaseClient` method, and arithmetic goes in `src/domain/`, not the view that needed it first.
- **`logging`, not `print`** — a module-scope `getLogger(__name__)`, configured only by the two entry points. `scripts/` is exempt.
- **Name the exception you expect.** Three broad `except Exception` handlers survive — `workers.py`, `commands.py:Param.parse` and `MainWindow.execute_command` — and a fourth is a bug.
- **No module docstrings and no comment essays.** One-line PEP 257 docstrings only, where a name and a type hint cannot say it; a comment only for a non-obvious workaround, one line. Why a design is the way it is belongs under `docs/`, said once.
- `specs/features/` is the authoritative behaviour spec. Read the relevant one before implementing and update it in the same commit as a behaviour change; where the two disagree, the spec settles it.
