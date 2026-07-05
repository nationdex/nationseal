function parseIds(value: string | undefined): string[] {
	if (!value) return [];
	return value
		.split(",")
		.map((id) => id.trim())
		.filter(Boolean);
}

function parseNumber(value: string | undefined, fallback: number): number {
	const parsed = Number(value);
	return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const config = {
	botToken: process.env.BOT_TOKEN ?? "",
	ownerIds: parseIds(process.env.OWNER_IDS),
	requiredApprovals: Math.max(1, parseNumber(process.env.REQUIRED_APPROVALS, 2)),
	banDeleteMessageSeconds: Math.min(
		604_800,
		Math.max(0, parseNumber(process.env.BAN_DELETE_MESSAGE_SECONDS, 0)),
	),
	databasePath: process.env.DATABASE_PATH ?? "./.data/data.json",
	antiraidBotIds: parseIds(process.env.ANTIRAID_BOT_IDS),
} as const;

if (!config.botToken) {
	throw new Error("[nationseal] BOT_TOKEN is not set in environment variables.");
}

if (config.ownerIds.length === 0) {
	throw new Error(
		"[nationseal] OWNER_IDS is empty. At least one owner is required to manage reviewers.",
	);
}
