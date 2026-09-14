# Adding a tracking module

To add a domain (say sleep):

1. **Schema** — the table goes in `init_db()` in `server/database.py`. Per-user
   tables carry `user_id` with `ON DELETE CASCADE`; log→item references use
   `ON DELETE SET NULL`. A per-user domain spanning several tables carries
   `user_id` on **every** one of them, child rows included: `routes/records.py`
   edits a row of any registered table by id and decides whether to filter on
   the member from `is_catalog` alone, so a child without the column would have
   to register as a shared catalog — and then either member could rewrite the
   other's rows. `training_plans` / `plan_sessions` / `plan_movements` is the
   worked example.
2. **Registry** — one `_spec(...)` row in `server/tables.py`. Two columns that
   are alternative ways of saying one thing are declared as an `exclusive`
   group. For named sets, add a `<domain>_set_components` table (its own foreign
   key into its own catalog, **no** `ON DELETE` clause) and one `SetSpec` row in
   `server/sets.py`.
3. **Routes** — under `server/routes/`: `@require_auth`, connection from
   `get_db()`, `g.user_id` filtering for per-user data, body via
   `read_payload(*required)`, values via `checked_payload`, `rowcount` checked on
   anything that mutates, `?since=` through `_since_clause()`. Broadcast
   `catalog_updated` on catalog mutations only.
4. **Client** — methods on `DatabaseClient` returning a `NamedTuple` from
   `src/database/rows.py` and taking `since: str = None`. Anything derived goes
   in `DBAnalyticsMixin`, with the arithmetic itself in `src/domain/`.
5. **View** — subclass `BaseManagedView` with parallel
   `tables`/`headers`/`mappings` lists; writable columns follow from the
   mapping. Three tables: ledger, catalog, sets pane (the last two stacked 6:4
   in the right-hand column). Fewer is fine — `PlanView` hosts one, beside a
   hand-painted widget — and a view whose surface implies a write emits
   `command_requested` rather than writing, so the member confirms it in the
   bar. Group the ledger through `rows.grouped_by_set` and declare
   `SET_FIELD`/`NAME_FIELD`/`GROUP_FIELDS`/`HEADING_TOTALS` on the row type. A
   chart subclasses `BaseGraphView` instead.
6. **Tab** — add it to `tab_registry` in `MainWindow` and to `[windows]` in
   `_generate_default_profile()`. Register the domain in `src/gui/domains.py`:
   the tables in `TABLE_DOMAINS`, the tab key in `TAB_DOMAINS`. A tab left out
   refreshes on every write (slow but correct); a table left out is a write
   nothing invalidates (stale data).
7. **Command** — one `Command` row in `src/gui/commands.py`. Hints, completion,
   parsing, the view effect and which tabs go stale all derive from it.
8. **Filter aliases** — only if the new headers deserve shorthand; a field term
   already resolves a full header or an unambiguous prefix.
9. **Spec** — `specs/features/<domain>_logging.feature`, before or alongside the
   code.
