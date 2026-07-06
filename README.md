# NationSeal

NationSeal is a shared, multi-server "sanctions" bot for Discord, inspired by the community-run ban-sharing systems used by large server networks. Server admins submit a user ID + reason to a shared list. A roster of trusted reviewers vote on the submission, and once enough approvals come in (a configurable "M of N" multi-sig, e.g. 2 approvals regardless of roster size) the bot automatically bans that user across **every server it's installed in** — even ones the user hasn't joined yet, since Discord allows banning by ID directly.

Built with [discord.py](https://discordpy.readthedocs.io/) and Python 3.12+.

## How it works

1. A server admin runs `/sanctions submit user:<user> reason:<text> evidence:<link>` to nominate someone for the shared ban list.
2. A trusted reviewer runs `/sanctions approve id:<id>` or `/sanctions decline id:<id>`. Once enough approvals are collected (`REQUIRED_APPROVALS`, default `2`), NationSeal:
   - Saves the entry to the shared `sanction` list in the JSON database.
   - Bans the user ID in every guild the bot currently sees, via Discord's ban endpoint — no need for the user to be a member.
3. Whenever NationSeal is invited to a **new** server, it automatically bulk-bans everyone already on the shared list in that server too.
4. If a ban was a mistake, an admin can run `/sanctions appeal` to request an un-ban, which goes through the same reviewer approval flow before the bot automatically unbans the user everywhere.

Reviewers are a small, explicitly managed roster (`/sanctions reviewer-add`, `reviewer-remove`, `reviewer-list`), controlled by the bot's **owners** (`OWNER_IDS` in `.env`) — the operators of the shared infrastructure, not individual server admins.

## Commands

| Command | Who | Description |
| --- | --- | --- |
| `/sanctions submit` | Anyone in the server | Submit a user for a network ban |
| `/sanctions appeal` | Anyone in the server | Request an un-ban for a sanctioned user |
| `/sanctions approve` | Trusted reviewers | Approve a pending submission |
| `/sanctions decline` | Trusted reviewers | Decline a pending submission |
| `/sanctions check` | Anyone in the server | Check if a user is currently sanctioned |
| `/sanctions info` | Anyone in the server | View a submission's details/vote tally |
| `/sanctions list` | Trusted reviewers | List recent submissions by status |
| `/sanctions reviewer-add` / `reviewer-remove` | NationSeal owners | Manage the reviewer roster |
| `/sanctions reviewer-list` | Anyone in the server | View the current reviewer roster |

All commands are **visible to everyone** in the server. If you try to run one you aren't allowed to use, NationSeal replies with a clear message explaining what permission or role you need.

## Permissions

NationSeal only ever requests the **Ban Members** permission — never Administrator. It needs:

- `bot` + `applications.commands` OAuth2 scopes.
- The **Ban Members** permission, to create/remove bans.
- The `Guilds` gateway intent only (non-privileged), just enough to know which servers it's in. No privileged intents (members, presences, etc.) are required, since sanctions are enforced by user ID directly through the REST API rather than by watching join events.

Invite URL template (replace `CLIENT_ID`):

```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=4&scope=bot%20applications.commands
```

(`permissions=4` is the numeric value of `Ban Members`.)

## Setup

1. Install dependencies with [uv](https://docs.astral.sh/uv/):

   ```bash
   uv sync
   ```

2. Copy `.env.example` to `.env` and fill in:
   - `BOT_TOKEN` — from the Discord Developer Portal.
   - `OWNER_IDS` — comma-separated Discord user IDs of the people who run the shared infrastructure and manage the reviewer roster.
   - `REQUIRED_APPROVALS` — how many reviewer approvals are needed (defaults to `2`).
   - `DATABASE_PATH` — path to the JSON file used for persistence (defaults to `./.data/data.json`).

3. Run the bot:

   ```bash
   uv run nationseal        # single run
   python -m nationseal     # equivalent
   ```

   On boot, NationSeal loads its JSON data file, then starts the Discord gateway connection and syncs its slash commands globally.

## Development

```bash
uv run ruff check .      # lint
uv run ruff check --fix . # auto-fix lint issues
uv run ty check nationseal # type check
uv run ruff check . && uv run ty check nationseal  # full check
```

## Project layout

```
pyproject.toml              UV project metadata and tool config
nationseal/
  __init__.py
  __main__.py
  bot.py
  data.py
  ui.py
```
