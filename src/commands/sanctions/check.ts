import { type CommandContext, createUserOption, Declare, Options, SubCommand } from "seyfert";
import {
	buildSanctionContainer,
	COMPONENTS_V2_FLAG,
	textOnlyContainer,
} from "../../lib/components";
import { sanctions } from "../../lib/db";

const options = {
	user: createUserOption({
		description: "The user to look up",
		required: true,
	}),
};

@Declare({
	name: "check",
	description: "Check whether a user is on the shared sanction list",
})
@Options(options)
export default class CheckSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		try {
			const { user } = ctx.options;
			const sanction = await sanctions.get(user.id);
			await ctx.editOrReply({
				components: [buildSanctionContainer(sanction, user.id)],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] check command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while checking the sanction list. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
