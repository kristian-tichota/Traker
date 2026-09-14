# Running the service

No household detail is held in the source. The service reads `~/.config/traker/server.toml`, and
`TRAKER_SERVER_CONFIG` points elsewhere.

## First run

Started with no settings file, the service writes a commented one and then stops, because it has no
members. Add a `[[members]]` table naming each `username` and start it again. A member with no `token`
is given one, which is logged at WARNING and written back beside that member. That value belongs in
the member's `~/.config/traker/user_profile.toml` under `[server] token`. Rotating a token means
editing it here; `users.id` is preserved, so the logs referencing it survive. Writing back rewrites
the file and discards its comments. Only values the file itself carries are written, so an
environment override belongs to the run that set it and never to the file.

## Settings

`TRAKER_SERVER_HOST`, `TRAKER_SERVER_PORT` and `TRAKER_DB_PATH` override `[server] host`, `port` and
`db_path`, which override the built-in defaults. A relative `db_path` resolves against the repository.
`host` defaults to `127.0.0.1`, which is this machine only. A household whose clients run elsewhere
sets `0.0.0.0`, and only on a trusted network. A token is the whole of the authentication: there is no
TLS, and this service MUST NOT be exposed to a public address.

`TRAKER_SERVER_URL` and `TRAKER_API_TOKEN` override `[server]` in the member profile, which overrides
the built-in `http://127.0.0.1:6035`. There is no built-in token, and without one every request is
answered as unauthenticated and the status line reports the refusal.

The client also snapshots the database on every start. That is `backup.py` rather than the service: it
ignores `db_path`, reads `data/` beside the repository, writes into `data/backups/` and keeps the
newest 30. A client on another machine finds nothing to snapshot and reports this at WARNING.

## Commands

```bash
uv run python server/app.py        # the service; it must be up before the client starts
uv run python src/main.py          # the GUI client, which installs its own .desktop entry
uv sync --no-dev                   # minimal install: logging only; add --extra graphs / --extra video
uv run pytest                      # the whole suite; no server and no display
uv run pytest -m perf -s           # the benchmarks, deselected by default, against a seeded database
uv run python scripts/walk_the_app.py   # the whole app end to end over a real socket
uv run python scripts/seed_dev_db.py    # a server-shaped database at realistic scale, for -m perf
uv run python scripts/import_training_plan.py plan.json --dry-run   # a cycle, checked then written
```

Every dependency is pinned and every pin is committed, because one server and two clients update
separately and an unpinned resolve can leave them on different versions of one wire format.
`pyproject.toml` pins at `==`, `uv.lock` pins the closure, `.python-version` pins the interpreter, and
`uv add 'name==X.Y.Z'` adds one. Only logging is core: the five graph tabs are the `graphs` extra and
the break film is `video`, a tab whose extra is absent is skipped rather than fatal, and a plain
`uv sync` pulls both through the dev group. `libmpv` is the one dependency no lockfile carries, and
`enforcing-a-break.md` states what to install. `src/` and `server/` are imported from the repository
root rather than installed (`[tool.uv] package = false`), supported by `pythonpath = .` in
`pytest.ini` and a `sys.path` line in each entry point. `TRAKER_LOG_LEVEL=DEBUG` raises verbosity, and
the suite layout is in `tests/README.md`.
