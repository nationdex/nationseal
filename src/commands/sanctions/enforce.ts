import { type CommandContext, Declare, SubCommand } from "seyfert";
import { COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { sanctions } from "../../lib/db";
import { requireReviewer } from "../../lib/permissions";
import { banAcrossGuilds } from "../../lib/sanctions";

@Declare({
	name: "enforce",
	description:
		"Re-ban all sanctioned users across all servers (useful if automatic enforcement failed)",
})
export default class EnforceSubCommand extends SubCommand {
	async run(ctx: CommandContext) {
		await ctx.deferReply(true);

		if (!(await requireReviewer(ctx))) return;

		try {
			const activeSanctions = await sanctions.listAll();

			if (activeSanctions.length === 0) {
				await ctx.editOrReply({
					components: [textOnlyContainer("No active sanctions to enforce.")],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			let totalBanned = 0;
			let totalAttempted = 0;
			const results: string[] = [];

			for (const sanction of activeSanctions) {
				const result = await banAcrossGuilds(
					ctx.client,
					sanction.id,
					`NationSeal enforcement: ${sanction.reason}`,
				);
				totalBanned += result.guildsSucceeded;
				totalAttempted += result.guildsAttempted;
				results.push(
					`• <@${sanction.id}> — banned in ${result.guildsSucceeded}/${result.guildsAttempted} servers`,
				);
			}

			const summary = [
				`## Enforcement complete`,
				`**Total:** ${activeSanctions.length} user(s) across ${totalBanned}/${totalAttempted} server(s)`,
				"",
				...results,
			];

			await ctx.editOrReply({
				components: [textOnlyContainer(summary.join("\n"))],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] enforce command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while enforcing sanctions. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
