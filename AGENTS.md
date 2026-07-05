# AGENTS.md

## Commands

```bash
bun run check          # typecheck + lint (run this after changes)
bun run dev            # watch mode
bun run start          # single run
bun run lint:fix       # auto-fix lint issues
```

## Architecture

Discord bot using Seyfert framework with a JSON file database. All commands live under `/sanctions` and use Components v2 for responses (Container/TextDisplay, never embeds).

**Entry point**: `src/index.ts` — loads the JSON database, starts bot, loads component handlers with absolute path via `client.loadComponents()`.

**Key directories**:
- `src/commands/sanctions/` — all slash commands as SubCommand classes
- `src/components/` — ComponentCommand handlers (pagination buttons)
- `src/lib/` — DB access (`db.ts`, `jsondb.ts`), permissions (`permissions.ts`), Components v2 builders (`components.ts`), voting logic (`sanctions.ts`)

## Critical Patterns

### Components v2 (Discord API)

**Never** send `content` together with `COMPONENTS_V2_FLAG`. Discord rejects this with `MESSAGE_CANNOT_USE_LEGACY_FIELDS_WITH_COMPONENTS_V2`.

For plain text responses:
```ts
await ctx.editOrReply({
  components: [textOnlyContainer("message")],
  flags: COMPONENTS_V2_FLAG,
});
```

For responses with detailed containers:
```ts
await ctx.editOrReply({
  components: [
    textOnlyContainer("summary line"),
    buildRequestContainer(request),
  ],
  flags: COMPONENTS_V2_FLAG,
});
```

### Permission Model

Commands are visible to everyone (no `defaultMemberPermissions` on parent command). Permission gates enforced in code:
- `submit`, `appeal`, `check`, `info` — public
- `approve`, `decline`, `list`, `enforce` — require reviewer (`requireReviewer()`)
- `reviewer-add`, `reviewer-remove` — require owner (`requireOwner()`)

### Sanctions List

The `/sanctions list` command only shows **pending** submissions waiting for approval. It displays one submission per page with:
- **Approve/Decline** buttons to vote on the current submission
- **Previous/Next** buttons to navigate between submissions (always visible, disabled at boundaries)

Custom ID format for pagination buttons:
- Navigation: `sanction_list|<pageNumber>`
- Vote: `sanction_list|<pageNumber>|<approve|decline>`

### Component Handler Loading

Component handlers in `src/components/` are loaded with an absolute path:
```ts
const componentsDir = path.join(process.cwd(), "src", "components");
await client.loadComponents(componentsDir);
```

Relative paths like `"src/components"` or `"./components"` fail because `magicImport()` in Seyfert expects absolute paths.

### JSON Database

Default mode stores all data in the JSON file at `DATABASE_PATH` (default `./.data/data.json`). It is loaded into memory on startup and flushed to disk after every mutating operation.

### DB Access Pattern

Collections accessed via exported objects in `src/lib/db.ts`:
- `sanctionRequests.create/get/update/listByStatus`
- `sanctions.get/upsert/remove/listAll`
- `reviewers.add/remove/list/isReviewer`
- `guildState.get/set/markEnforced`

All IDs are stored as plain strings in the JSON file.

### Autocomplete

Commands with `id` options (`approve`, `decline`, `info`) use autocomplete to show pending submissions. The autocomplete callback:
- Fetches submissions from DB
- Filters by user input (matches ID, target user, or reason)
- Returns up to 25 choices with format: `[status] type target — reason`

## Style

- Tabs for indentation (biome.json)
- Double quotes (biome.json)
- All responses are ephemeral (`deferReply(true)`)
- Use `escapeMarkdown()` from `components.ts` for user-supplied text in markdown
