import { ComponentCommand, type ComponentContext } from "seyfert";
import {
	LIST_CUSTOM_ID_PREFIX,
	PER_PAGE,
	parseListCustomId,
	resolveRequestListPayload,
} from "../commands/sanctions/list";
import { COMPONENTS_V2_FLAG, textOnlyContainer } from "../lib/components";
import { sanctionRequests } from "../lib/db";
import { isReviewer } from "../lib/permissions";
import { castVote, VoteError } from "../lib/sanctions";

/**
 * Handles the "Previous", "Next", "Approve", and "Decline" buttons emitted by the
 * `/sanctions list` command. The customId formats are:
 *
 *   Navigation: sanction_list|<pageNumber>
 *   Vote:       sanction_list|<pageNumber>|<approve|decline>
 */
export default class SanctionListPaginator extends ComponentCommand {
	override componentType = "Button" as const;

	override filter(ctx: ComponentContext<"Button">): boolean {
		return parseListCustomId(ctx.customId).kind !== "invalid";
	}

	override async run(ctx: ComponentContext<"Button">): Promise<unknown> {
		const parsed = parseListCustomId(ctx.customId);
		if (parsed.kind === "invalid") return;

		if (!(await isReviewer(ctx.author.id))) {
			return ctx.write({
				components: [
					textOnlyContainer("Only trusted NationSeal reviewers can interact with this list."),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}

		if (parsed.kind === "vote") {
			return this.handleVote(ctx, parsed.page, parsed.action);
		}

		return this.handleNavigation(ctx, parsed.page);
	}

	private async handleNavigation(ctx: ComponentContext<"Button">, page: number): Promise<void> {
		try {
			const payload = await resolveRequestListPayload(page, LIST_CUSTOM_ID_PREFIX);

			await ctx.update({
				components: payload.components,
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] sanction list paginate failed:", error);
		}
	}

	private async handleVote(
		ctx: ComponentContext<"Button">,
		page: number,
		action: "approve" | "decline",
	): Promise<void> {
		try {
			const all = await sanctionRequests.listByStatus("pending", 200);

			const index = (page - 1) * PER_PAGE;
			const request = all[index];

			if (!request) {
				return ctx.update({
					components: [textOnlyContainer("No submission found at this position.")],
					flags: COMPONENTS_V2_FLAG,
				});
			}

			const result = await castVote(ctx.client, request.id, ctx.author.id, action);

			const lines = [`Vote recorded on \`${request.id}\` (${action}).`];
			if (result.justResolved) {
				lines.push(
					`✅ Threshold reached — ${result.request.type === "ban" ? "ban" : "unban"} enforced on ${result.enforcement?.guildsSucceeded ?? 0}/${result.enforcement?.guildsAttempted ?? 0} servers.`,
				);
			}

			const payload = await resolveRequestListPayload(page, LIST_CUSTOM_ID_PREFIX);

			await ctx.update({
				components: [textOnlyContainer(lines.join("\n")), ...payload.components],
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] sanction list vote failed:", error);
			const message =
				error instanceof VoteError ? error.message : "An error occurred while voting.";
			await ctx.update({
				components: [textOnlyContainer(message)],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}

export { PER_PAGE };
