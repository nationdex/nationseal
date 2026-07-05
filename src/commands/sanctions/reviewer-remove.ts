import { type CommandContext, createUserOption, Declare, Options, SubCommand } from "seyfert";
import { COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { reviewers } from "../../lib/db";
import { requireOwner } from "../../lib/permissions";

const options = {
	user: createUserOption({
		description: "The reviewer to remove from the roster",
		required: true,
	}),
};

@Declare({
	name: "reviewer-remove",
	description: "Remove a trusted reviewer from the multi-sig roster (owners only)",
})
@Options(options)
export default class ReviewerRemoveSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		if (!(await requireOwner(ctx))) return;

		try {
			const { user } = ctx.options;
			await reviewers.remove(user.id);
			ctx.client.logger.info(
				`[nationseal] AUDIT reviewerRemove reviewer=${user.id} by=${ctx.author.id}`,
			);
			await ctx.editOrReply({
				components: [textOnlyContainer(`<@${user.id}> is no longer a trusted reviewer.`)],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] reviewer-remove command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while removing the reviewer. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
