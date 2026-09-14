# Review criteria

A review MUST read the relevant `specs/features/*.feature` before deciding which of two disagreeing implementations is wrong, because the specification settles that question.

## Settled decisions

Each item below was weighed against its alternative and chosen. Reopening one requires new evidence, and none of them is a finding.

- Positional tuples on the wire; the `server/tables.py` registry; per-request connections; `read_payload` and the `BadRequest` family answered by one handler; `coerce_value`; the `rowcount` checks; `ConnectionStatus`; `run_in_background` wiring both signals; `src/domain/` holding the arithmetic; `BaseGraphView` unifying the five chart shells.
- A 409 and a 404 are built by the route that finds them, because each states something specific. Only a refusal a route can forget to convert belongs in `BadRequest`.
- Binding which table in a receiver per table, and carrying what a receiver needs in the payload, because a lambda there aborts the process.
- `Command.view_effect` being declarative; `?since=` optional; the completion cache keyed per catalog.
- `QAbstractTableModel` behind a `QSortFilterProxyModel`; `LogTableModel` holding the wire rows unreshaped; per-domain dirty tracking; `LedgerCache` having no TTL; pending columns rendering as `…`; the filter grammar being pure.
- `ChartCanvas` owning a `FigureCanvasAgg`; the render on a pool thread; the lock taken non-blocking; a hidden chart deferring. Matplotlib MUST NOT be replaced: pyqtgraph and a hand-rolled `QPainter` were both weighed, the measured problem was where the render ran, and the appearance is specified.
- Named sets expanding into ordinary log rows; a meal set's components in grams; the heading being a view construct that sorting drops; one namespace per log command; a set being flat; deleting an item a set uses being refused. One `item_sets` table with one components table per domain.
- `:wlog` being its own command, and `:exlog` refusing a workout name.
- A food log storing whichever unit was typed; the estimate flag on the log row rather than the catalog item; `:quick` refusing a name that is already a food.
- The loading arc having a grace period, so that it does not appear for most waits, a cache-served revisit being 18-74 ms.
- The legacy profile and database-path branches, which read files present on the household machines.
- Three broad `except Exception` handlers, each with a one-line note, and `scripts/` printing rather than logging.

## Highest-risk areas

Ranked by what has broken this application.

1. Anything reached from a worker result or a `paintEvent`, where an exception is a core dump. Check that the receiver is a named callable and that every attribute it touches survives teardown.
2. Shutdown ordering, because anything still in flight at the end is a crash.
3. A number computed in two places. Search for the quantity.
4. A write path added without the gate, or a value computed after it.
5. A test that drives no paint and no event, which can pass over incorrect code.
6. A widget whose base class changed, because a dead QSS rule is not an error.
7. A column added to a ledger or reordered, because `headers` and `OptimisticRow.fields` fail silently.
8. Reading Qt state back to decide what to do.

## Claim verification

A defect MUST be reproduced before it is reported.

```bash
uv run pytest -q                                    # necessary but not sufficient
QT_QPA_PLATFORM=offscreen uv run python -c "..."    # a five-line reproduction settles most Qt claims
uv run python scripts/walk_the_app.py               # the broadest check available
```

The walk runs a real server, client and window over a temporary database. Two constraints apply before adding to it: a tab nobody has switched to is never refreshed, so the test MUST switch to the tab under test first; and the status line races the sync stream's echo, so an assertion MUST check that `Fail` is absent rather than match a confirmation's exact words.
