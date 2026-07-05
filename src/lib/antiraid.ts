import type { UsingClient } from "seyfert";
import { config } from "../config";
import { guildState } from "./db";

/**
 * Returns the subset of `config.antiraidBotIds` that are currently members
 * of the given guild. Uses the REST API (no Members intent required) and
 * treats "member not found" as "not present" — anything else is logged
 * and treated as "unknown" (i.e. we err on the side of caution and assume
 * the anti-raid bot is present, so we still skip the auto-ban).
 */
export async function detectAntiraidBots(client: UsingClient, guildId: string): Promise<string[]> {
	if (config.antiraidBotIds.length === 0) return [];
	const present: string[] = [];

	for (const botId of config.antiraidBotIds) {
		try {
			await client.members.fetch(guildId, botId);
			present.push(botId);
		} catch (error) {
			// Discord returns 404 when the member isn't in the guild.
			// Anything else is an unexpected error — log it and treat the
			// bot as "present" so we don't accidentally auto-ban over it.
			const status =
				typeof error === "object" && error && "rawError" in error
					? (error as { rawError?: { status?: number } }).rawError?.status
					: undefined;
			if (status === 404) continue;
			client.logger.warn(
				`[nationseal] Could not check antiraid bot ${botId} in ${guildId}:`,
				error,
			);
			present.push(botId);
		}
	}
	return present;
}

export interface AntiraidBlockResult {
	blocked: boolean;
	detectedBots: string[];
}

/**
 * Checks the configured anti-raid bots and, if any are present in the
 * given guild, records the state in the DB and returns the list of
 * detected bots so the caller can DM the guild owner.
 */
export async function maybeBlockForAntiraid(
	client: UsingClient,
	guild: { id: string; name: string; ownerId?: string },
): Promise<AntiraidBlockResult> {
	const detected = await detectAntiraidBots(client, guild.id);
	if (detected.length === 0) {
		// Make sure any prior "blocked" state is cleared if the anti-raid
		// bot was removed.
		const existing = await guildState.get(guild.id);
		if (existing?.antiraidBlocked) {
			await guildState.set(guild.id, {
				antiraidBlocked: false,
				antiraidBots: [],
				enforcementStatus: "auto_enforced",
			});
		}
		return { blocked: false, detectedBots: [] };
	}

	const existing = await guildState.get(guild.id);
	const now = new Date().toISOString();
	await guildState.set(guild.id, {
		antiraidBlocked: true,
		antiraidBots: detected,
		enforcementStatus: "antiraid_blocked",
		antiraidNotifiedAt: existing?.antiraidNotifiedAt ?? now,
	});

	client.logger.warn(
		`[nationseal] Auto-ban SKIPPED in ${guild.id} (${guild.name}); antiraid bot(s) detected: ${detected.join(", ")}. Owner has been DM'd.`,
	);
	return { blocked: true, detectedBots: detected };
}
