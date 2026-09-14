# Invariants

A violation of the constraints below fails silently, fatally, or both.

## Threading and lifetime
- No network call MUST run on the interface thread. Background work starts only through `run_in_background`, which wires `error` as well as `result` and holds the worker alive until `finished`. A worker's result receiver MUST be a named callable, never a lambda, because PyQt keeps a lambda's connection to a destroyed receiver and an exception in a slot or a `paintEvent` aborts the interpreter. Extra state MUST be bound in the payload or in a receiver per case; `tests/gui/test_main_window.py` walks the AST to enforce this.
- Shutdown order is `closeEvent`, listener `stop()`, view `shutdown()`, `waitForDone`, widgets. `stop_timers` reaches `QTimer` instances only, so `ChangeGlow` MUST be stopped first.
- `PausesWhenHidden` timers MUST be created in `__init__` and started in `showEvent`, because Qt sends no `hideEvent` to a widget never shown and a `QTabWidget` shows only its current tab. Qt state MUST NOT be read back to decide what to do, because `isVisible()` answers for the whole parent chain.

## Correctness
- There is one write gate, and any value derived on the way to the store MUST pass through it again. A write that matched no row returns 404. A route raises `BadPayload` or `BadValue` and MUST NOT build the answer itself. SQLite accepts `"12o"` in a `REAL` column, where `CHECK(x >= 0)` then passes, and stores `1e400` as `inf`; `coerce_value` refuses both at the boundary.
- A number that appears in two readouts MUST be one function in `src/domain/`, with a test asserting the two agree. Search for the quantity, not the function name.
- A food log stores whichever of `servings` or `grams` was entered. Storing servings unconditionally would rewrite the recorded mass.
- `CREATE TABLE IF NOT EXISTS` never alters an existing table, so a later column requires an explicit migration in `init_db`, in foreign-key order. Deleting a catalog item that a set uses returns 409; every other log-to-item reference is `ON DELETE SET NULL`.
- A break's two key ranges MUST NOT overlap: `Enter` and `1`-`9` are activity offers, `a`-`z` tick chores, and each list MUST leave an unused key unconsumed. A wall is identified by its title (`WALL_CAPTION`); walls receive `keepAbove` and the focus and the application's own window receives neither, because KWin stacks an active fullscreen window above a kept-above one. A break is requested by application id, and an incorrect id fails silently.

## Cache invalidation
- The object that owns a cache drops it, keyed by domain rather than table, because a catalog write invalidates that domain's log reads as well. A failed read MUST NOT be cached, and there is no TTL: the cache drops on a local write, a `catalog_updated` event, the service returning, and an explicit refresh.
- Only one unbounded read per domain MAY be cached. The second key is a `since` date bound rather than a free-form key, so two unbounded reads would share `(domain, None)` and answer each other with rows of the wrong shape.

## Modality
- `set_mode` is the only entry to a mode, `MODES` the only list of them, and a mode is entered by the transition rather than by a focus event. A mode MUST NOT outlive its tab; half-typed command text does.
- The readout is `mode_label`, never `status_bar`, because fourteen callers write the status line and none restores a mode. Leaving a mode also releases the keyboard, because `clearFocus()` leaves the window with no focus widget and `MainWindow` reads the tab keys.

## Compositor integration
- `w.output` is stale after a drag. `Window::setOutput` is the only emitter of `outputChanged`, and an interactive move ends in `sendToOutput(moveResizeOutput())`. Decide by frame geometry and watch `interactiveMoveResizeFinished`.
- No script-written desktop or activity property is applied on this Plasma, and a refused property write raises nothing, so every write MUST be read back. The pin is therefore a window rule; the output is a script, because KWin's rule for it is an index into a list rebuilt each boot.
- The application's rules MUST be first in `[General] rules=`, because `Rules::checkSetStop` means the first rule to set a value decides it. A rule matches on the window title, never the application, because every window of this application carries one class and a class-matched rule would reach a break's walls. `Workspace::reconfigure` debounces by 200 ms.
- A monitor switched off is a withdrawn output, and the returning monitor is a new `QScreen`. Anything holding the old one raises `RuntimeError` from a Qt slot. Release inside the signal, rebuild once the burst settles, and key a wall to the output name.

## Rendering and tables
- A QSS type selector matches a class and its subclasses, so re-basing or renaming a widget can leave a rule matching nothing, without an error. `repaint()` on a widget never shown does nothing, so a paint test MUST render into a `QPixmap`; `show()` on a visible widget likewise sends no `showEvent`.
- A date column is coupled in two directions: the model renders ISO as Czech for `DATE_HEADERS`, and `on_cell_edited` reads Czech back off the same tuple. Rows keep ISO, because the sort reads the value.
- A column added to a ledger or reordered in one is coupled in four places, of which only two fail loudly: a view's `headers` and a `Command`'s `OptimisticRow.fields` fail silently.
- A column layout is a permutation of the header, never of the model, and the header is the state. A programmatic `moveSection` emits `sectionMoved`, so applying a stored layout MUST suppress the signal.
- The filter and the sort read the typed value, never the rendered string, because `"9.00" > "312.40"` is true. A chart's read, reset and draw run on a pool thread and may touch the figure; only `prepare_refresh` may touch a widget, and `ChartCanvas.render_lock` is taken without blocking.
- The first GL child of a window already on a screen causes Qt to destroy and recreate that window, which discards a `ForceTemporarily` rule with the window it matched. A wall therefore carries a hidden `QOpenGLWidget` from construction.
- A break plays through libmpv into a GL surface of the application's own window. The proc-address resolver MUST be held on the instance, and `update_cb` and `end-file` arrive on mpv threads, so both MUST cross by signal. A file is handed over only once `initializeGL` has run. Nothing a widget paints is visible over the picture, so every readout is on the walls beside the film, and a single-screen break places them in rows beneath it. A machine without libmpv MUST still hold a break, so `VideoPane` reports `COULD NOT PLAY` rather than raising.
- A `QPdfView` page requested before the document is laid out moves the page number rather than the view, so a resumed page MUST be requested again at every moment the view offers one.

## Command grammar
- An argument with a `default` may be omitted, so the Tab split MUST NOT use the declared argument count, and a required argument following an optional one MUST validate its own shape. A recogniser matches the shape, not the validity.
- A command with a `window_effect` never reaches `invoke`, because its subject is the visible tab, which only the window can resolve. `name_position(text)` is a function of the typed text rather than a property of the command.
- The menu and the greyed hint MUST rank once and read the same index. Tab MAY only append when the typed text is the name's own opening under `COLLATE NOCASE` folding.

## Conventions
- Solarized only. Widget code MUST NOT carry a literal hex value; `PALETTE` in `src/config.py` is the source. Matplotlib takes `facecolor=PALETTE['base3']`, with `base01` and `base2` for spines and grids.
- Dates are ISO at the API and the SQLite boundary, and Czech `DD.MM.YYYY` in anything displayed. `src/domain/clock.py` is the single conversion.
- PyQt6 only, because the Wayland overlays depend on `WA_TranslucentBackground`.
- GUI code MUST NOT contain raw SQL. A new query is a server route plus a `DatabaseClient` method, and arithmetic belongs in `src/domain/`. Use `logging` rather than `print`, through a module-scope `getLogger(__name__)` configured only by the two entry points; `scripts/` is exempt.
- Name the expected exception. Three broad `except Exception` handlers are sanctioned: `workers.py`, `commands.py:Param.parse` and `MainWindow.execute_command`. A fourth is a defect.
- No module docstrings and no comment essays. Docstrings are one-line PEP 257 only, and a comment is permitted only for a non-obvious workaround, on one line. Design rationale belongs under `docs/`.
- `specs/features/` is the authoritative behaviour specification. It MUST be read before implementing and updated in the same commit as a behaviour change; where the two disagree, the specification decides.
