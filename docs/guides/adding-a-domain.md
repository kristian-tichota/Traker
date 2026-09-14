# Adding a tracking domain

The steps below add one domain, such as sleep.

1. **Schema.** The table goes in `init_db()` in `server/database.py`. Per-user tables carry `user_id`
   with `ON DELETE CASCADE`, and log-to-item references use `ON DELETE SET NULL`. A per-user domain
   spanning several tables MUST carry `user_id` on every one of them, child rows included, because
   `routes/records.py` edits a row of any registered table by id and decides whether to filter on the
   member from `is_catalog` alone, so a child without the column would have to register as a shared
   catalog and either member could then rewrite the other's rows. `training_plans`, `plan_sessions`
   and `plan_movements` are the worked example.
2. **Registry.** Add one `_spec(...)` row in `server/tables.py`. Two columns that are alternative ways
   of stating one thing are declared as an `exclusive` group. For named sets, add a
   `<domain>_set_components` table, with its own foreign key into its own catalog and no `ON DELETE`
   clause, and one `SetSpec` row in `server/sets.py`.
3. **Routes.** Add them under `server/routes/`, using `@require_auth`, a connection from `get_db()`,
   `g.user_id` filtering for per-user data, a body through `read_payload(*required)`, values through
   `checked_payload`, a `rowcount` check on anything that mutates, and `?since=` through
   `_since_clause()`. Broadcast `catalog_updated` on catalog mutations only.
4. **Client.** Add methods on `DatabaseClient` returning a `NamedTuple` from `src/database/rows.py`
   and taking `since: str = None`. Anything derived goes in `DBAnalyticsMixin`, with the arithmetic
   itself in `src/domain/`.
5. **View.** Subclass `BaseManagedView` with parallel `tables`, `headers` and `mappings` lists, from
   which the writable columns follow. There are three tables: the ledger, the catalog and the sets
   pane, the last two stacked 6:4 in the right-hand column. Fewer is permitted, and `PlanView` hosts
   one beside a hand-painted widget. A view whose surface implies a write MUST emit
   `command_requested` rather than writing, so that the member confirms it in the bar. Group the
   ledger through `rows.grouped_by_set` and declare `SET_FIELD`, `NAME_FIELD`, `GROUP_FIELDS` and
   `HEADING_TOTALS` on the row type. A chart subclasses `BaseGraphView` instead.
6. **Tab.** Add it to `tab_registry` in `MainWindow` and to `[windows]` in
   `_generate_default_profile()`. Register the domain in `src/gui/domains.py`, with the tables in
   `TABLE_DOMAINS` and the tab key in `TAB_DOMAINS`. A tab left out refreshes on every write, which is
   slow but correct; a table left out is a write that nothing invalidates, which leaves stale data.
7. **Command.** Add one `Command` row in `src/gui/commands.py`. The hints, the completion, the
   parsing, the view effect and which tabs go stale all derive from it.
8. **Filter aliases.** Add them only where the new headers deserve shorthand, because a field term
   already resolves a full header or an unambiguous prefix.
9. **Specification.** Add `specs/features/<domain>_logging.feature`, before or alongside the code.
