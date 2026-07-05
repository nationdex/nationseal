import type { UsingClient } from "seyfert";
import { config } from "../config";

export interface DmTarget {
	userId: string;
	channel: Awaited<ReturnType<UsingClient["users"]["createDM"]>>;
}

export interface DmOutcome {
	recipient: string;
	delivered: boolean;
	reason?: string;
}

/**
 * Try to open a DM channel with a given user. Returns `null` if the bot
 * can't reach the user (DMs closed, mutual-guild requirement not met,
 * etc.). We swallow the error because the only thing the caller can do is
 * fall back to logging.
 */
async function openDm(client: UsingClient, userId: string): Promise<DmTarget["channel"] | null> {
	try {
		return await client.users.createDM(userId);
	} catch {
		return null;
	}
}

async function sendDm(client: UsingClient, userId: string, content: string): Promise<DmOutcome> {
	const channel = await openDm(client, userId);
	if (!channel) {
		return {
			recipient: userId,
			delivered: false,
			reason: "Could not open DM channel (DMs closed or user not reachable).",
		};
	}
	try {
		await client.messages.write(channel.id, { content });
		return { recipient: userId, delivered: true };
	} catch (error) {
		return {
			recipient: userId,
			delivered: false,
			reason: error instanceof Error ? error.message : String(error),
		};
	}
}

/**
 * Sends the same message to a list of users. Used for "DM the guild owner
 * + DM the NationSeal owners as a backup" so a NationSeal operator is
 * always aware when an anti-raid bot has been detected.
 */
export async function dmUsers(
	client: UsingClient,
	userIds: string[],
	content: string,
): Promise<DmOutcome[]> {
	const unique = [...new Set(userIds.filter(Boolean))];
	return Promise.all(unique.map((id) => sendDm(client, id, content)));
}

export function buildAntiraidMessage(input: {
	guildName: string;
	guildId: string;
	ownerMention: string;
	detectedBots: string[];
}): string {
	const botList = input.detectedBots.map((id) => `\`${id}\``).join(", ");
	return [
		`Hi ${input.ownerMention} — NationSeal was just added to **${input.guildName}** (\`${input.guildId}\`).`,
		"",
		`I detected the following anti-raid / anti-nuke bot(s) in the server: ${botList}.`,
		"",
		"To avoid a flag-spam war, NationSeal will **not** auto-ban the shared sanction list on this server. To enable enforcement, please add NationSeal to the anti-raid bot's whitelist (most use a `/whitelist add` or similar command) and then ask a NationSeal owner to run `/sanctions local-enforce`.",
		"",
		"If you don't want NationSeal on this server, you can simply kick it — no data has been written yet.",
	].join("\n");
}

export function buildOwnerFallbackMessage(input: {
	guildName: string;
	guildId: string;
	ownerId: string | undefined;
	ownerDmFailed: boolean;
	detectedBots: string[];
}): string {
	const botList = input.detectedBots.map((id) => `\`${id}\``).join(", ");
	return [
		`[nationseal] Auto-ban blocked in **${input.guildName}** (\`${input.guildId}\`).`,
		`Anti-raid bot(s) detected: ${botList}.`,
		input.ownerId ? `Guild owner: <@${input.ownerId}>.` : "Guild owner ID unknown.",
		input.ownerDmFailed
			? "Could not DM the guild owner (DMs closed). A NationSeal owner needs to follow up."
			: "Guild owner has been DM'd with whitelisting instructions.",
		`Run \`/sanctions local-enforce guild:${input.guildId}\` once NationSeal is whitelisted.`,
		`Owners notified: ${config.ownerIds.map((id) => `\`${id}\``).join(", ") || "(none configured)"}.`,
	].join("\n");
}
