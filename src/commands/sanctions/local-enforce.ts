import { type CommandContext, createStringOption, Declare, Options, SubCommand } from "seyfert";
import { COMPONENTS_V2_FLAG, textOnlyContainer } from "../../lib/components";
import { guildState, sanctions } from "../../lib/db";
import { requireOwner } from "../../lib/permissions";
import { enforceAllSanctionsOnGuild } from "../../lib/sanctions";

const options = {
	guild: createStringOption({
		description: "The server ID to manually enforce the sanction list in",
		required: true,
		min_length: 17,
		max_length: 20,
	}),
};

@Declare({
	name: "local-enforce",
	description:
		"Manually push the shared sanction list into a server (bypasses anti-raid auto-block; owners only)",
})
@Options(options)
export default class LocalEnforceSubCommand extends SubCommand {
	async run(ctx: CommandContext<typeof options>) {
		await ctx.deferReply(true);

		if (!(await requireOwner(ctx))) return;

		const guildId = ctx.options.guild.trim();
		if (!/^\d{17,20}$/.test(guildId)) {
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"That doesn't look like a valid Discord server ID (must be 17-20 digits).",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
			return;
		}

		try {
			// Confirm the bot is actually in that guild — otherwise the
			// bulk-ban call will fail and waste a rate-limit slot.
			let guildName: string | undefined;
			try {
				const cached = await ctx.client.cache.guilds?.get(guildId);
				guildName = cached?.name;
			} catch {
				guildName = undefined;
			}
			if (!guildName) {
				await ctx.editOrReply({
					components: [
						textOnlyContainer(
							`I'm not in any server with ID \`${guildId}\`. The bot must be invited first.`,
						),
					],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			const total = (await sanctions.listAll()).length;
			if (total === 0) {
				await ctx.editOrReply({
					components: [
						textOnlyContainer("The shared sanction list is empty — nothing to enforce."),
					],
					flags: COMPONENTS_V2_FLAG,
				});
				return;
			}

			const { banned } = await enforceAllSanctionsOnGuild(ctx.client, guildId);
			await guildState.markEnforced(guildId);

			ctx.client.logger.info(
				`[nationseal] AUDIT localEnforce guild=${guildId} by=${ctx.author.id} banned=${banned}/${total}`,
			);

			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						[
							`Manual enforcement complete in **${guildName}** (\`${guildId}\`).`,
							`Banned **${banned}** of **${total}** active sanctions.`,
							"This guild is now marked as `manually_enforced` in the database.",
						].join("\n"),
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] local-enforce command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while enforcing sanctions in that server. Check the bot logs for the Discord error.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}
