import { config } from "seyfert";

export default config.bot({
	token: process.env.BOT_TOKEN ?? "",
	intents: ["Guilds"],
	locations: {
		base: "src",
		commands: "commands",
		events: "events",
	},
});
