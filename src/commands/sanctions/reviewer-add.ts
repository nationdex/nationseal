import { type CommandContext, createUserOption, Declare, Options, SubCommand } from "seyfert";
import { COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { reviewers } from "../../lib/db";
import { requireOwner } from "../../lib/permissions";

const options = {
	user: createUserOption({
		description: "The user to add as a trusted reviewer",
		required: true,
	}),
};

@Declare({
	name: "reviewer-add",
	description: "Add a trusted reviewer to the multi-sig roster (owners only)",
})
@Options(options)
export default class ReviewerAddSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		if (!(await requireOwner(ctx))) return;

		try {
			const { user } = ctx.options;
			await reviewers.add(user.id, ctx.author.id);
			ctx.client.logger.info(
				`[nationseal] AUDIT reviewerAdd reviewer=${user.id} by=${ctx.author.id}`,
			);
			await ctx.editOrReply({
				components: [textOnlyContainer(`<@${user.id}> is now a trusted reviewer.`)],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] reviewer-add command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while adding the reviewer. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
