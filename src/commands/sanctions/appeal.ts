import {
	type CommandContext,
	createStringOption,
	createUserOption,
	Declare,
	Options,
	SubCommand,
} from "seyfert";
import { buildRequestContainer, COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { sanctions } from "../../lib/db";
import { submitRequest } from "../../lib/sanctions";

const options = {
	user: createUserOption({
		description: "The sanctioned user this appeal is for",
		required: true,
	}),
	reason: createStringOption({
		description: "Why should this sanction be lifted?",
		required: true,
		min_length: 3,
		max_length: 400,
	}),
};

@Declare({
	name: "appeal",
	description: "Request that an existing network-wide ban be lifted. Requires reviewer approval.",
})
@Options(options)
export default class AppealSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		try {
			const { user, reason } = ctx.options;

			const existing = await sanctions.get(user.id);
			if (!existing) {
				await ctx.editOrReply({
					components: [
						textOnlyContainer(`<@${user.id}> is not currently on the shared sanction list.`),
					],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			const request = await submitRequest({
				type: "unban",
				targetId: user.id,
				targetTag: user.tag,
				reason,
				evidence: null,
				submittedBy: ctx.author.id,
				submittedByTag: ctx.author.tag,
				guildId: ctx.guildId ?? "unknown",
			});

			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Appeal submitted. A reviewer will need to approve it before the ban is lifted.",
					),
					buildRequestContainer(request),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] appeal command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while submitting the appeal. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
