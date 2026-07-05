import {
	type CommandContext,
	createStringOption,
	createUserOption,
	Declare,
	Options,
	SubCommand,
} from "seyfert";
import { buildRequestContainer, COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { isReviewer } from "../../lib/permissions";
import { submitRequest } from "../../lib/sanctions";

const options = {
	user: createUserOption({
		description: "The user to submit for a network-wide ban",
		required: true,
	}),
	reason: createStringOption({
		description: "Why should this user be sanctioned? (e.g. raider, scammer)",
		required: true,
		min_length: 3,
		max_length: 400,
	}),
	evidence: createStringOption({
		description: "Link to evidence (message link, screenshot URL, etc.)",
		required: false,
		max_length: 400,
	}),
};

@Declare({
	name: "submit",
	description:
		"Submit a user for a network-wide ban. Requires reviewer approval before it takes effect.",
})
@Options(options)
export default class SubmitSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		try {
			const { user, reason, evidence } = ctx.options;

			if (user.bot) {
				await ctx.editOrReply({
					components: [textOnlyContainer("Bots can't be added to the sanction list.")],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			// Reject self-submissions. A user trying to nominate themselves
			// is either griefing (forcing reviewers to spend quorum on a
			// nonsense request) or attempting social engineering.
			if (user.id === ctx.author.id) {
				await ctx.editOrReply({
					components: [textOnlyContainer("You can't submit yourself for a network ban.")],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			// Reject submissions targeting any NationSeal reviewer (or owner).
			// Reviewers run the multi-sig and so should be removable from it
			// only by an owner via /sanctions reviewer-remove, not by being
			// out-voted by a coalition of other reviewers.
			if (await isReviewer(user.id)) {
				await ctx.editOrReply({
					components: [
						textOnlyContainer(
							"Trusted NationSeal reviewers (and owners) can't be submitted for a network ban. Ask an owner to remove them from the reviewer roster first.",
						),
					],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			const request = await submitRequest({
				type: "ban",
				targetId: user.id,
				targetTag: user.tag,
				reason,
				evidence: evidence ?? null,
				submittedBy: ctx.author.id,
				submittedByTag: ctx.author.tag,
				guildId: ctx.guildId ?? "unknown",
			});

			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Submission received. A reviewer will need to approve it before the ban is enforced.",
					),
					buildRequestContainer(request),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] submit command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while submitting the sanction. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
