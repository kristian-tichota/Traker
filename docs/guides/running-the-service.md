# Running the service

Nothing about a household is in the source. The service reads
`~/.config/traker/server.toml`; `TRAKER_SERVER_CONFIG` points somewhere else.

## First run

Start it once with no settings file and it writes a commented one, then stops
because it has no members. Name them and start again:

```toml
[server]
host = "127.0.0.1"
port = 6035
db_path = "data/traker_server.db"   # relative resolves against the repository

[[members]]
username = "alice"
```

A member with no `token` is given one, which is logged at WARNING and written
back beside that member. Paste it into that member's
`~/.config/traker/user_profile.toml` under `[server] token`. Rotating a token is
editing it here: `users.id` is preserved, so the logs that reference it survive.

**Writing back rewrites the file, and comments in it are lost.** Only values the
file itself carries are written — an environment override belongs to the run
that set it, never to the file.

## The three settings

`TRAKER_SERVER_HOST`, `TRAKER_SERVER_PORT` and `TRAKER_DB_PATH` beat the file,
which beats the built-in default.

`host` defaults to `127.0.0.1`, which is this machine only. A household whose
clients run elsewhere sets `0.0.0.0` — deliberately, and only on a network it
trusts. A token is the whole of the authentication: there is no TLS, and none of
this belongs on an address the internet can reach.

## The client half

`TRAKER_SERVER_URL` and `TRAKER_API_TOKEN` beat `[server]` in the member's
profile, which beats the built-in `http://127.0.0.1:6035`. **There is no built-in
token.** Without one every request is answered as unauthenticated and the status
line says the service refused it.

It also snapshots the database on **every start**, which is `backup.py` and not the
service: that one ignores `db_path`, looks in `data/` beside the repository, writes into
`data/backups/` and keeps the newest 30. A client on another machine finds nothing to
snapshot and says so at WARNING.

## Commands

Managed with **uv**, and `uv run` syncs from the lockfile first.

```bash
uv run python server/app.py        # this service; it must be up before the client starts
uv run python src/main.py          # the GUI client (installs its own .desktop entry)
uv sync --no-dev                   # minimal install: logging only; add --extra graphs / --extra video
uv run pytest                      # the whole suite, ~70 s; no server, no display
uv run pytest -m perf -s           # the benchmarks; deselected by default, needs a seeded db
uv run python scripts/walk_the_app.py   # the whole app end to end over a real socket, ~15 s
uv run python scripts/seed_dev_db.py    # a server-shaped database at realistic scale, for -m perf
uv run python scripts/import_training_plan.py plan.json --dry-run   # a cycle, checked then written
```

**Everything is pinned, and every pin is committed.** One server and two clients update
separately, so an unpinned resolve can leave them on different versions of one wire format:
`pyproject.toml` at `==`, `uv.lock` for the closure, `.python-version` for the interpreter. Add
with `uv add 'name==X.Y.Z'`. **Only logging is core** — the five graph tabs are the `graphs`
extra and the break's film is `video`; a tab whose extra is absent is skipped, not fatal, and a
plain `uv sync` pulls both through the dev group. **`libmpv` is the one dependency no lockfile
carries**; `enforcing-a-break.md` says what to install.

`src/` and `server/` are imported from the repository root rather than installed (`[tool.uv]
package = false`); `pytest.ini`'s `pythonpath = .` and each entry point's `sys.path` line are
what make that work. `TRAKER_LOG_LEVEL=DEBUG` raises verbosity.

What the suite sandboxes, and how: `tests/README.md`.
