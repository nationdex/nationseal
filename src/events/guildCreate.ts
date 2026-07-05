import { createEvent } from "seyfert";
import { config } from "../config";
import { maybeBlockForAntiraid } from "../lib/antiraid";
import { guildState } from "../lib/db";
import { buildAntiraidMessage, buildOwnerFallbackMessage, dmUsers } from "../lib/dm";
import { enforceAllSanctionsOnGuild } from "../lib/sanctions";

export default createEvent({
	data: { name: "guildCreate" },
	async run(guild, client) {
		const antiraid = await maybeBlockForAntiraid(client, {
			id: guild.id,
			name: guild.name,
			ownerId: guild.ownerId,
		});

		if (antiraid.blocked) {
			const ownerMention = guild.ownerId ? `<@${guild.ownerId}>` : "owner";
			const dmContent = buildAntiraidMessage({
				guildName: guild.name,
				guildId: guild.id,
				ownerMention,
				detectedBots: antiraid.detectedBots,
			});
			const recipients = [guild.ownerId, ...config.ownerIds].filter((id): id is string =>
				Boolean(id),
			);
			const outcomes = await dmUsers(client, recipients, dmContent);
			const ownerDelivered = outcomes.find((o) => o.recipient === guild.ownerId)?.delivered;

			// Always log a server-side message too, regardless of DM success.
			client.logger.warn(
				buildOwnerFallbackMessage({
					guildName: guild.name,
					guildId: guild.id,
					ownerId: guild.ownerId,
					ownerDmFailed: !ownerDelivered,
					detectedBots: antiraid.detectedBots,
				}),
			);
			return;
		}

		// Second line of defence: if a previous run marked this guild as
		// antiraid-blocked (e.g. the antiraid list was empty at startup but
		// a detection was recorded), still skip the auto-enforce.
		const existing = await guildState.get(guild.id);
		if (existing?.antiraidBlocked) {
			client.logger.info(
				`[nationseal] Skipping auto-enforce in ${guild.id} (${guild.name}) — anti-raid previously detected.`,
			);
			return;
		}

		const { banned, total } = await enforceAllSanctionsOnGuild(client, guild.id);
		client.logger.info(
			`[nationseal] Joined guild ${guild.id} (${guild.name}). Synced ${banned}/${total} active sanctions.`,
		);
	},
});
