import { type CommandContext, createStringOption, Declare, Options, SubCommand } from "seyfert";
import { buildRequestContainer, COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { sanctionRequests } from "../../lib/db";

const options = {
	id: createStringOption({
		description: "The submission ID to look up",
		required: true,
		autocomplete: async (interaction) => {
			const all = [
				...(await sanctionRequests.listByStatus("pending", 25)),
				...(await sanctionRequests.listByStatus("approved", 25)),
				...(await sanctionRequests.listByStatus("declined", 25)),
			];
			const input = interaction.getInput().toLowerCase();
			const choices = all
				.filter((req) => {
					const target = req.targetTag || req.targetId;
					return (
						req.id.toLowerCase().includes(input) ||
						target.toLowerCase().includes(input) ||
						req.reason.toLowerCase().includes(input)
					);
				})
				.slice(0, 25)
				.map((req) => ({
					name: `[${req.status}] ${req.type === "ban" ? "Ban" : "Unban"} ${req.targetTag || req.targetId} — ${req.reason.slice(0, 40)}`,
					value: req.id,
				}));
			await interaction.respond(choices);
		},
	}),
};

@Declare({
	name: "info",
	description: "View the full details and vote tally of a submission",
})
@Options(options)
export default class InfoSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		try {
			const request = await sanctionRequests.get(ctx.options.id.trim());

			if (!request) {
				await ctx.editOrReply({
					components: [textOnlyContainer(`No submission found with id \`${ctx.options.id}\`.`)],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			await ctx.editOrReply({
				components: [buildRequestContainer(request)],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] info command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while fetching that submission. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
