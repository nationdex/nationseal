import { createEvent } from "seyfert";

export default createEvent({
	data: { once: true, name: "botReady" },
	async run(user, client) {
		const guildIds = (await client.cache.guilds?.keys()) ?? [];
		client.logger.info(
			`[nationseal] ${user.username} is online, watching ${guildIds.length} server(s).`,
		);
	},
});
