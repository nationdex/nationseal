# AGENTS.md

## Commands

```bash
uv run ruff check .            # lint (run this after changes)
uv run ruff check --fix .      # auto-fix lint issues
uv run ty check nationseal     # type check
uv run nationseal              # run the bot
python -m nationseal           # equivalent entry point
```

Full verification:

```bash
uv run ruff check . && uv run ty check nationseal
```

## Architecture

Discord bot using **discord.py** with a JSON file database. All commands live under `/sanctions` and use Components v2 for responses (Container/TextDisplay, never embeds).

**Entry point**: `python -m nationseal` → `nationseal/__main__.py` → `nationseal.bot.main()`

**The whole codebase is 3 Python files**:

| File | Contents |
| --- | --- |
| `nationseal/bot.py` | Config, `NationSealBot` class, event handlers, run loop |
| `nationseal/data.py` | Domain types, `JsonDatabase`, collection wrappers, voting, ban/unban enforcement, anti-raid detection, DM helpers |
| `nationseal/ui.py` | Permissions, Components v2 builders, paginator Cog, all `/sanctions` slash commands |

Plus the required `nationseal/__init__.py` and `nationseal/__main__.py` (boilerplate only).

The data layer is initialized via `data.init_runtime(...)` in `bot.py`'s `setup_hook`; business-logic functions in `data.py` read config from module-level globals after that call. UI code accesses collections through `data.sanction_requests()`, `data.sanctions()`, etc.

## Critical Patterns

### Components v2 (Discord API)

**Never** send `content` together with the Components v2 flag. Discord rejects this with `MESSAGE_CANNOT_USE_LEGACY_FIELDS_WITH_COMPONENTS_V2`.

Components v2 messages are built with `discord.ui.LayoutView`, `Container`, `TextDisplay`, `Separator`, `ActionRow`, and `Button`. The `LayoutView` automatically sets the Components v2 flag when containers are present.

For plain text responses:

```python
view = build_layout(text_only_container("message"))
await interaction.response.send_message(view=view, ephemeral=True)
```

For responses with detailed containers:

```python
view = build_layout(
    text_only_container("summary line"),
    build_request_container(request),
)
await interaction.response.send_message(view=view, ephemeral=True)
```

### Permission Model

Commands are visible to everyone (no `default_permissions` on the parent group). Permission gates enforced in code:
- `submit`, `appeal`, `check`, `info` — public
- `approve`, `decline`, `list`, `enforce` — require reviewer (`require_reviewer()`)
- `reviewer-add`, `reviewer-remove` — require owner (`require_owner()`)

### Sanctions List

The `/sanctions list` command only shows **pending** submissions waiting for approval. It displays one submission per page with:
- **Approve/Decline** buttons to vote on the current submission
- **Previous/Next** buttons to navigate between submissions (always visible, disabled at boundaries)

Custom ID format for pagination buttons:
- Navigation: `sanction_list|<pageNumber>`
- Vote: `sanction_list|<pageNumber>|<approve|decline>`

The paginator Cog (`ComponentsCog` in `ui.py`) handles button clicks via `on_interaction`.

### JSON Database

Default mode stores all data in the JSON file at `DATABASE_PATH` (default `./.data/data.json`). It is loaded into memory on startup and flushed to disk after every mutating operation.

The `JsonDatabase` class uses a `modified` flag so shutdown flushes only happen when data has actually changed. This prevents an empty in-memory dataset from overwriting a valid data file on restart.

### DB Access Pattern

Access collections via the `data` module functions (singletons initialized at startup):
- `data.sanction_requests().create/get/update/list_by_status`
- `data.sanctions().get/upsert/remove/list_all`
- `data.reviewers().add/remove/list_all/is_reviewer`
- `data.guild_states().get/set/mark_enforced`

All IDs are stored as plain strings in the JSON file.

### Autocomplete

Commands with `id` options (`approve`, `decline`, `info`) use autocomplete to show pending submissions. The autocomplete callback:
- Fetches submissions from DB
- Filters by user input (matches ID, target user, or reason)
- Returns up to 25 choices with format: `[status] type target — reason`

`discord.py` requires autocomplete callbacks to be coroutine functions, not lambdas — see `_approve_autocomplete`/`_decline_autocomplete`/`_info_autocomplete` in `ui.py`.

## Style

- Tabs for indentation (configured in `pyproject.toml` under `[tool.ruff.format]`)
- Double quotes (configured in `pyproject.toml`)
- All responses are ephemeral (`defer(ephemeral=True)`)
- Use `_escape_markdown()` from `ui.py` for user-supplied text in markdown

## Gotchas

- **Package layout**: All code lives in `nationseal/`. There is no `src/` or `lib/` subdirectory, and no `main.py` at the repo root — the entry point is `python -m nationseal` (which runs `nationseal/__main__.py`).
- **PM2 startup**: Use `pm2 start "uv run python -m nationseal" --name nationseal` (not `uv run nationseal`) because the package isn't installed in editable mode. Without `-m`, Python can't find the `nationseal` package on `sys.path`.
- **Environment loading**: `bot.py` auto-loads `.env` from the project root via `python-dotenv`, so PM2 picks up env vars without explicit configuration. `config = Config()` is constructed at import time and validates `BOT_TOKEN` + `OWNER_IDS` immediately.
- **Config is loaded at import**: `nationseal.bot` instantiates `Config()` at module load. If you `import nationseal.ui` without `BOT_TOKEN` in env, the import will fail. Tests or scripts that just want to import the data layer need a token in env.
- **Runtime init order**: `setup_hook` must call `data.init_runtime(...)` before any command runs. The data layer's `_db` / collection singletons are `None` until that runs; calling them earlier raises `AssertionError`.
