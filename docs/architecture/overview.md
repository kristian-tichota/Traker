# Architecture

A PyQt6 client talks to a local Flask and Waitress service over HTTP, and the service owns the SQLite
file. The client holds no SQLite connection: `self.db` in any view is an HTTP client.

Catalogs are shared by both members, while logs, settings, telemetry and training plans are scoped by
`user_id`. Chores are the one subject whose log is shared as well, because a per-member completion
would continue to ask the other member for work already done. Member tokens come from the household
settings file and are seeded into `users` on boot. Required behaviour is in `specs/features/`,
constraints that fail silently are in `invariants.md`, and the guides are under `docs/guides/`.

## Server

`tables.py` is the single registry: which tables the API exposes, catalog against per-user log,
writable columns, non-negative columns, and `exclusive` groups. Anything absent from it is refused
with 400, and column types come from `PRAGMA table_info` through `coerce_value`. `validation.py` is
the single write gate. `app.py` holds the three error handlers, so no route answers for itself, and
every error body is JSON because the client parses it.

## Client

`domain/` holds the arithmetic, without Qt or `requests`, and is the only place a number appearing in
two readouts is computed. `database/rows.py` is the only place a server shape is named. `desktop/`
holds everything that reaches KDE: two KWin scripts, two window rules, the night filter, the switch
guard, and the break queue and positions.

## Named sets

One `item_sets` table carries a `domain` column, with one components table per domain. The asymmetry
is the foreign key, because a single components table would require a polymorphic item id that SQLite
cannot constrain. Logging a set produces one ordinary log row per component in one transaction, each
carrying `set_id`. A name is unique within its domain.

| Domain | Displayed term | Component carries | Defined by | Logged by |
| --- | --- | --- | --- | --- |
| food | meal set | grams | `:mealset` | `:log` |
| beverage | drink set | servings | `:bevset` | `:bevlog` |
| supplement | stack | servings | `:suppset` | `:supplog` |
| mobility | routine set | minutes | `:mobset` | `:moblog` |
| exercise | workout | set scheme, load, effort | `:exset` | `:wlog` |

An exercise component is not an amount, so it is not scaled by a multiplier, and `:exlog` refuses a
workout name rather than logging it with the typed numbers ignored.

## Chores and plans

A chore stores a cadence rather than a next-due date, because that date is a function of the cadence
and the last completion, and storing it would fix a rule that a corrected completion could not re-run.
A plan session stores its date, because three readers in two processes need it. Plans are not named
sets, because a cycle carries its own loads week by week where seventeen weeks of sets would be
near-copies.
