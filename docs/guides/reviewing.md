# Reviewing a change here

A confident wrong finding costs more than a missed one. Read the relevant
`specs/features/*.feature` before deciding which of two disagreeing implementations is wrong —
it has settled it every time.

## Settled — not findings

Each was weighed against its alternative and chosen. Raising one again needs new evidence.

- Positional tuples on the wire; the `server/tables.py` registry; per-request connections; `read_payload` and the `BadRequest` family answered by one handler; `coerce_value`; the `rowcount` checks; `ConnectionStatus`; `run_in_background` wiring both signals; `src/domain/` holding the arithmetic; `BaseGraphView` unifying the five chart shells.
- **A 409 and a 404 are still built by the route that finds them** — they say something specific, and no two are alike. Only a refusal a route can *forget to convert* belongs in `BadRequest`.
- Binding *which table* in a receiver per table, and carrying what a receiver needs in the payload — a lambda there aborts the process.
- `Command.view_effect` being declarative; `?since=` optional; the completion cache keyed per catalog.
- `QAbstractTableModel` behind a `QSortFilterProxyModel`; `LogTableModel` holding the wire rows unreshaped; per-domain dirty tracking; `LedgerCache` having no TTL; pending columns rendering as `…`; the filter grammar being pure.
- `ChartCanvas` owning a `FigureCanvasAgg`; the render on a pool thread; the lock taken non-blocking; a hidden chart deferring. **Matplotlib is not up for replacement** — pyqtgraph and a hand-rolled `QPainter` were both weighed, the measured problem was *where* the render ran, and the aesthetics are the spec.
- Named sets expanding into ordinary log rows; a meal set's components in grams; the heading being a view construct that sorting drops; one namespace per log command; a set being flat; deleting an item a set uses being refused. One `item_sets` table with one components table per domain.
- `:wlog` being its own command, and `:exlog` refusing a workout's name.
- A food log storing whichever unit was typed; the estimate flag on the log row rather than the catalog item; `:quick` refusing a name that is already a food.
- The loading arc having a grace period, so it does not appear for most waits (a cache-served revisit is 18–74 ms).
- The legacy profile and database-path branches — they read files that exist on the household's machines.
- Three broad `except Exception`s, each with a one-line note. `scripts/` printing instead of logging.

## Where the bodies are

Ranked by what has actually broken this application.

1. **Anything reached from a worker result or a `paintEvent`** — an exception there is a core dump. Check the receiver is a named callable and that every attribute it touches survives teardown.
2. **Shutdown ordering.** Anything still in flight at the end is a crash.
3. **A number computed in two places.** Grep for the quantity.
4. **A write path added without the gate**, or a value computed after it.
5. **A test that drives no paint, or no event.** Two tests here passed for that reason while the code under them was wrong.
6. **A widget whose base class changed** — a dead QSS rule is not an error.
7. **A column added to a ledger, or reordered** — `headers` and `OptimisticRow.fields` fail silently.
8. **Reading Qt state back to decide what to do.**

## Checking a claim before writing it down

A defect MUST be reproduced before it is reported.

```bash
uv run pytest -q                                    # necessary, nowhere near sufficient
QT_QPA_PLATFORM=offscreen uv run python -c "..."    # a five-line repro settles most Qt claims
uv run python scripts/walk_the_app.py               # ~15 s, the strongest check there is
```

The walk runs a real server, client and window over a temp database. Two things to know before
adding to it: **a tab nobody has switched to is never refreshed**, so switch to the tab under
test first; and the status line races the sync stream's echo, so assert that "Fail" is absent
rather than on a confirmation's exact words.
