# Architecture

A PyQt6 client talks to a local Flask/Waitress service over HTTP; the service owns the SQLite
file. **The client holds no SQLite connection** — `self.db` in any view is an HTTP client.

Catalogs are shared by both members; logs, settings, telemetry and training plans are
`user_id`-scoped. **Chores are the one subject whose log is shared too** — the bins are taken
out by whoever got to them, and a per-member completion would leave the other still being
asked. Member tokens come from the household settings file, seeded into `users` on boot.

## Server

`tables.py` is the one registry: which tables the API exposes, catalog vs per-user log,
writable columns, non-negative columns, `exclusive` groups. Anything missing from it is
refused with 400; column types come from `PRAGMA table_info` via `coerce_value`.
`validation.py` is the one write gate. `app.py` holds the three error handlers so no route
answers for itself, and every error body is JSON because the client parses it.

## Client

`domain/` is the arithmetic — no Qt, no `requests` — and the only place a number that appears
in two readouts is computed. `database/rows.py` is the only place a server shape is named.
`desktop/` is everything that reaches KDE: two KWin scripts, two window rules, the night
filter, the switch guard, and the break's queue and positions.

## Named sets

One `item_sets` table with a `domain` column, plus one components table per domain — the
asymmetry is the foreign key, since a single components table would need a polymorphic item id
SQLite cannot constrain. Logging a set becomes one ordinary log row per component in one
transaction, each carrying `set_id`. A name is unique within its domain.

| Domain | Member's word | A component carries | Defined by | Logged by |
| --- | --- | --- | --- | --- |
| food | meal set | grams | `:mealset` | `:log` |
| beverage | drink set | servings | `:bevset` | `:bevlog` |
| supplement | stack | servings | `:suppset` | `:supplog` |
| mobility | routine set | minutes | `:mobset` | `:moblog` |
| exercise | workout | set scheme, load, effort | `:exset` | `:wlog` |

Exercise's component is not an amount, so it is not scaled by a multiplier and `:exlog`
refuses a workout's name rather than logging it with the typed numbers ignored.

## Chores and plans

A chore stores a **cadence**, never a next-due date: that is a function of the cadence and the
last completion, and storing it would be a rule a corrected completion could not re-run. A
plan session stores its **date**, because three readers in two processes need it. Plans are
deliberately not named sets — a cycle carries its own loads week by week, where seventeen weeks
of sets would be near-copies. Contracts: `specs/features/`.

## Where to look

| Question | File |
| --- | --- |
| What must the app do? | `specs/features/` (+ its README) |
| What breaks silently if I get it wrong? | `docs/architecture/invariants.md` |
| How do I configure and start the service, and what are the commands? | `docs/guides/running-the-service.md` |
| How is the suite laid out, and what does it sandbox? | `tests/README.md` |
| How do I add a tracked domain? | `docs/guides/adding-a-domain.md` |
| Which columns does a table show? | `docs/guides/arranging-columns.md` |
| Which mode am I in, and who says so? | `docs/guides/the-modality.md` |
| How does the Plans tab work? | `docs/guides/following-a-plan.md` |
| How does the timer work, and a break? | `docs/guides/enforcing-a-break.md` |
| Where does the window live, and the film? | `docs/guides/placing-the-window.md` |
| Why is my screen grey after eight? | `docs/guides/going-monochrome.md` |
| When is a chore next due? | `docs/guides/keeping-a-chore.md` |
| What is settled, and where do defects come from? | `docs/guides/reviewing.md` |
| What is known-broken or unmeasured? | `docs/status/known-drift.md` |
