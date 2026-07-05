import { type CommandContext, createStringOption, Declare, Options, SubCommand } from "seyfert";
import { buildRequestContainer, COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { sanctionRequests } from "../../lib/db";
import { requireReviewer } from "../../lib/permissions";
import { castVote, VoteError } from "../../lib/sanctions";

const options = {
	id: createStringOption({
		description: "The submission ID to decline",
		required: true,
		autocomplete: async (interaction) => {
			const pending = await sanctionRequests.listByStatus("pending", 25);
			const input = interaction.getInput().toLowerCase();
			const choices = pending
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
					name: `${req.type === "ban" ? "Ban" : "Unban"} ${req.targetTag || req.targetId} — ${req.reason.slice(0, 50)}`,
					value: req.id,
				}));
			await interaction.respond(choices);
		},
	}),
	reason: createStringOption({
		description: "Why is this submission being declined?",
		required: false,
		max_length: 400,
	}),
};

@Declare({
	name: "decline",
	description: "Cast a reviewer decline vote on a pending submission",
})
@Options(options)
export default class DeclineSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		if (!(await requireReviewer(ctx))) return;

		try {
			const { request, justResolved } = await castVote(
				ctx.client,
				ctx.options.id.trim(),
				ctx.author.id,
				"decline",
				ctx.options.reason,
			);

			const lines = [`Vote recorded on \`${request.id}\`.`];
			if (justResolved) lines.push("❌ Threshold reached — submission declined.");

			await ctx.editOrReply({
				components: [textOnlyContainer(lines.join("\n")), buildRequestContainer(request)],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] decline command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						error instanceof VoteError
							? error.message
							: "Something went wrong while recording your vote. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
