# NationSeal

NationSeal is a shared, multi-server "sanctions" bot for Discord, inspired by
the community-run ban-sharing systems used by large server networks. Server
admins submit a user ID + reason to a shared list. A roster of trusted
reviewers vote on the submission, and once enough approvals come in (a
configurable "M of N" multi-sig, e.g. 2 approvals regardless of roster size)
the bot automatically bans that user across **every server it's installed
in** — even ones the user hasn't joined yet, since Discord allows banning by
ID directly.

Built with [Seyfert](https://seyfert.dev) (Discord gateway framework).

## How it works

1. A server admin (anyone with the **Ban Members** permission) runs
   `/sanction submit user:<user> reason:<text> evidence:<link>` to nominate
   someone for the shared ban list.
2. A trusted reviewer runs `/sanction approve id:<id>` or
   `/sanction decline id:<id>`. Once enough approvals are collected
   (`REQUIRED_APPROVALS`, default `2`), NationSeal:
   - Saves the entry to the shared `sanction` list in the JSON database.
   - Bans the user ID in every guild the bot currently has cached, via
     Discord's ban endpoint — no need for the user to be a member.
3. Whenever NationSeal is invited to a **new** server, it automatically
   bulk-bans everyone already on the shared list in that server too.
4. If a ban was a mistake, an admin can run `/sanction appeal` to request an
   un-ban, which goes through the same reviewer approval flow before the bot
   automatically unbans the user everywhere.

Reviewers are a small, explicitly managed roster (`/sanction reviewer-add`,
`reviewer-remove`, `reviewer-list`), controlled by the bot's **owners**
(`OWNER_IDS` in `.env`) — the operators of the shared infrastructure, not
individual server admins.

## Commands

| Command | Who | Description |
| --- | --- | --- |
| `/sanction submit` | Anyone in the server | Submit a user for a network ban |
| `/sanction appeal` | Anyone in the server | Request an un-ban for a sanctioned user |
| `/sanction approve` | Trusted reviewers | Approve a pending submission |
| `/sanction decline` | Trusted reviewers | Decline a pending submission |
| `/sanction check` | Anyone in the server | Check if a user is currently sanctioned |
| `/sanction info` | Anyone in the server | View a submission's details/vote tally |
| `/sanction list` | Trusted reviewers | List recent submissions by status |
| `/sanction reviewer-add` / `reviewer-remove` | NationSeal owners | Manage the reviewer roster |
| `/sanction reviewer-list` | Anyone in the server | View the current reviewer roster |

All commands are **visible to everyone** in the server. If you try to run one
you aren't allowed to use, NationSeal replies with a clear message explaining
what permission or role you need.

## Permissions

NationSeal only ever requests the **Ban Members** permission — never
Administrator. It needs:

- `bot` + `applications.commands` OAuth2 scopes.
- The **Ban Members** permission, to create/remove bans.
- The `Guilds` gateway intent only (non-privileged), just enough to know
  which servers it's in. No privileged intents (members, presences, etc.)
  are required, since sanctions are enforced by user ID directly through
  the REST API rather than by watching join events.

Invite URL template (replace `CLIENT_ID`):

```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=4&scope=bot%20applications.commands
```

(`permissions=4` is the numeric value of `Ban Members`.)

## Setup

1. Install dependencies:

   ```bash
   bun install
   ```

2. Copy `.env.example` to `.env` and fill in:
   - `BOT_TOKEN` — from the Discord Developer Portal.
    - `OWNER_IDS` — comma-separated Discord user IDs of the people who run
      the shared infrastructure and manage the reviewer roster.
    - `REQUIRED_APPROVALS` — how many reviewer approvals are needed (defaults
      to `2`).
    - `DATABASE_PATH` — path to the JSON file used for persistence
      (defaults to `./.data/data.json`).

3. Run the bot:

   ```bash
   bun run dev   # watch mode
   bun run start # single run
   ```

   On boot, NationSeal loads its JSON data file, then starts the Discord gateway
   connection and uploads its slash commands.

### Troubleshooting

**"Api Unauthorized 0" error:**
- Your `BOT_TOKEN` is invalid or missing. Get a valid token from the Discord Developer Portal.

**"OWNER_IDS is empty" error:**
- You must set at least one Discord user ID in `OWNER_IDS` so someone can manage reviewers.

**Commands are visible but I get "You need the Ban Members permission":**
- The `/sanction` tree is intentionally visible to everyone.
- `submit` and `appeal` are open to any member of the server.
- `approve`, `decline`, and `list` require being a trusted reviewer.
- `reviewer-add` and `reviewer-remove` require being a NationSeal owner.

**Data persistence:**
- All data is stored in the JSON file configured by `DATABASE_PATH`.
- Make sure this file is included in your backups if you want to preserve
  sanctions and reviewer rosters across reinstalls.

## Development

```bash
bun run typecheck # tsc --noEmit
bun run lint      # biome check .
bun run lint:fix  # biome check --write .
bun run check     # typecheck + lint
```

## Project layout

```
seyfert.config.mjs      Seyfert runtime configuration (intents, locations)
src/
  config.ts             Environment variable parsing
  index.ts               Entrypoint: loads the JSON database, starts the bot
  lib/
    db.ts                JSON database connection + table access helpers
    jsondb.ts            In-memory JSON file database implementation
    embeds.ts            Discord embed builders for submissions/sanctions
    permissions.ts       Owner/reviewer checks
    sanctions.ts         Core multi-sig voting + cross-guild ban enforcement
    types.ts             Shared domain types
  commands/sanction/     /sanction and its subcommands
  events/
    botReady.ts          Startup log
    guildCreate.ts       Syncs the shared sanction list into newly joined guilds
```

This project was bootstrapped with `bun init` in bun v1.3.14.
[Bun](https://bun.com) is a fast all-in-one JavaScript runtime.
