# Traker test suite

No server and no display required.

```bash
uv run pytest                    # pytest.ini points at tests/ and puts the repo root on sys.path
uv run pytest tests/server       # one layer
uv run pytest -m accessibility   # one concern
uv run pytest -m perf -s         # the benchmarks, deselected by default; needs a seeded db
```

`conftest.py` forces `QT_QPA_PLATFORM=offscreen` before any Qt import; `TRAKER_TEST_QT_PLATFORM` overrides it (`wayland` to watch them).

Laid out by boundary, not by source tree. `tests/unit/` is pure logic and talks to nothing; `tests/server/` drives the Flask API over a temporary SQLite file; `tests/client/` drives `DatabaseClient` through a `requests` bridge into the test client; `tests/gui/` builds widgets against stubs and one `QApplication`; `tests/perf/` benchmarks against a real socket and a seeded ledger.

## Nothing here touches your data

Five redirects happen at conftest *import* time, because each target is created as an import side effect or read the moment a widget is built: `TRAKER_SERVER_CONFIG` — set first, so the two members are the suite's own and never the machine's — then `src.profile.PROFILE_PATH`, `server.config.DB_PATH`, `src.desktop.rest_queue.DEFAULT_PATH`, and `src.desktop.kwin_rules.DEFAULT_PATH` with `kde_config.KWINRC_PATH` beside it — the last two are the member's real window rules, which a break *writes*. Per-test isolation is layered on top by `profile_path` and `server_db`.

## The fixtures worth knowing

`user_profile` / `write_profile` (a `UserProfile` over a generated default, or over TOML you supply), `member_a` / `member_b` / `anon` (API clients for the two seeded members and an unauthenticated caller), `seeded_catalog`, `db_client` (a real `DatabaseClient` routed into the Flask test client), `offline_requests` (every `requests` verb raises), and in `tests/gui/`, `settled` (drains the pool, then delivers the queued signals) and `recording_db` (a client stand-in answering reads and recording writes).

Markers mirror the spec tags (`exact`, `accessibility`, `gap`), plus `gui` and `perf`, with `--strict-markers` on. **No `gap` test is open**: a `@gap` test is `xfail(strict=True)`, so fixing the defect turns it into a failure, which is the signal to drop the marker.

## A green suite is not a working app

The suite drains the pool the moment it starts work, so it never gives the cyclic collector the window a running event loop does — which is how a worker left collectable mid-flight segfaults every launch with the whole suite green. Nothing here runs against a real socket; the strongest check is `uv run python scripts/walk_the_app.py`.

## Conventions

- One assertion subject per test; the name is the sentence the spec states.
- Server behaviour is asserted through HTTP, never by reading SQLite — except about the schema.
- A test that triggers background work asserts *after* `settled()`.
- A paint test renders into a `QPixmap`: `repaint()` on a widget never shown does nothing.
- A stand-in answering a date-bounded read *honours* the bound and records it on `since_asked`.
- A double for the client boundary builds its rows through the real `from_server`, never by hand.
- Column positions are pinned server-side and client-side, so a reordered `SELECT` fails before a graph does.
- An unhandled exception in a Qt slot **aborts the interpreter**, so any render path reached from a worker result needs a test that drives it end to end.
