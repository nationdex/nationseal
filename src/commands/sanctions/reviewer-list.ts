import { type CommandContext, Declare, SubCommand } from "seyfert";
import {
	buildReviewerListContainer,
	COMPONENTS_V2_FLAG,
	textOnlyContainer,
} from "../../lib/components";
import { reviewers } from "../../lib/db";

@Declare({
	name: "reviewer-list",
	description: "List the current trusted reviewers",
})
export default class ReviewerListSubCommand extends SubCommand {
	async run(ctx: CommandContext) {
		await ctx.deferReply(true);

		try {
			const list = await reviewers.list();
			await ctx.editOrReply({
				components: [buildReviewerListContainer(list)],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] reviewer-list command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while fetching the reviewer roster. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
