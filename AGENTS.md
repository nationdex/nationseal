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

**Entry point**: `nationseal/main.py` — loads the JSON database, starts the bot, syncs slash commands globally.

**Key modules**:
- `nationseal/commands/sanctions.py` — all slash commands as a discord.py Cog
- `nationseal/components/paginator.py` — Component interaction handler (pagination buttons)
- `nationseal/components/builders.py` — Components v2 UI builders
- `nationseal/sanctions.py` — voting logic and cross-guild enforcement
- `nationseal/permissions.py` — owner/reviewer permission checks
- `nationseal/db.py` — async database collection wrappers
- `nationseal/jsondb.py` — in-memory JSON file database implementation

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

### JSON Database

Default mode stores all data in the JSON file at `DATABASE_PATH` (default `./.data/data.json`). It is loaded into memory on startup and flushed to disk after every mutating operation.

The `JsonDatabase` class uses a `modified` flag so shutdown flushes only happen when data has actually changed. This prevents an empty in-memory dataset from overwriting a valid data file on restart.

### DB Access Pattern

Collections accessed via exported objects in `nationseal/db.py`:
- `sanction_requests.create/get/update/list_by_status`
- `sanctions.get/upsert/remove/list_all`
- `reviewers.add/remove/list_all/is_reviewer`
- `guild_state.get/set/mark_enforced`

All IDs are stored as plain strings in the JSON file.

### Autocomplete

Commands with `id` options (`approve`, `decline`, `info`) use autocomplete to show pending submissions. The autocomplete callback:
- Fetches submissions from DB
- Filters by user input (matches ID, target user, or reason)
- Returns up to 25 choices with format: `[status] type target — reason`

## Style

- Tabs for indentation (configured in `pyproject.toml` under `[tool.ruff.format]`)
- Double quotes (configured in `pyproject.toml`)
- All responses are ephemeral (`defer(ephemeral=True)`)
- Use `_escape_markdown()` from `components/builders.py` for user-supplied text in markdown

## Gotchas

- **Module naming**: `nationseal/models.py` (not `types.py`) to avoid shadowing stdlib `types` module. This breaks `typing` imports if named `types.py`.
- **PM2 startup**: Use `pm2 start "uv run python -m nationseal" --name nationseal` (not `uv run nationseal`) because the package isn't installed in editable mode.
- **Environment loading**: `config.py` auto-loads `.env` from project root via `python-dotenv`, so PM2 picks up env vars without explicit configuration.
