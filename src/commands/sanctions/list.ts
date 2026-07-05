import { ActionRow, type CommandContext, Declare, SubCommand } from "seyfert";
import {
	buildRequestListContainers,
	COMPONENTS_V2_FLAG,
	textOnlyContainer,
} from "../../lib/components";
import { sanctionRequests } from "../../lib/db";
import { requireReviewer } from "../../lib/permissions";
import type { SanctionRequest } from "../../lib/types";

const PER_PAGE = 1;

export const LIST_CUSTOM_ID_PREFIX = "sanction_list";

@Declare({
	name: "list",
	description: "List pending submissions waiting for approval (reviewers only)",
})
export default class ListSubCommand extends SubCommand {
	async run(ctx: CommandContext) {
		await ctx.deferReply(true);

		if (!(await requireReviewer(ctx))) return;

		try {
			const status = "pending";
			const all = await sanctionRequests.listByStatus(status, 200);

			const customIdPrefix = LIST_CUSTOM_ID_PREFIX;
			const built = buildRequestListContainers(all, {
				page: 1,
				perPage: PER_PAGE,
				total: all.length,
				status,
				customIdPrefix,
			});

			const components: (
				| ReturnType<typeof buildRequestListContainers>["main"]
				| ActionRow
				| ReturnType<typeof buildRequestListContainers>["footer"]
			)[] = [
				built.main,
				new ActionRow().addComponents(built.approve, built.decline),
				new ActionRow().addComponents(built.back, built.next),
				built.footer,
			];

			await ctx.editOrReply({
				components,
				flags: COMPONENTS_V2_FLAG,
			});
		} catch (error) {
			ctx.client.logger.error("[nationseal] list command failed:", error);
			await ctx.editOrReply({
				components: [
					textOnlyContainer(
						"Something went wrong while listing submissions. Please try again later.",
					),
				],
				flags: COMPONENTS_V2_FLAG,
			});
		}
	}
}

export type ParsedListCustomId =
	| { kind: "invalid" }
	| { kind: "navigate"; page: number }
	| { kind: "vote"; page: number; action: "approve" | "decline" };

export function parseListCustomId(rawCustomId: string): ParsedListCustomId {
	const parts = rawCustomId.split("|");
	if (parts.length < 2 || parts[0] !== LIST_CUSTOM_ID_PREFIX) {
		return { kind: "invalid" };
	}

	const page = Number.parseInt(parts[1] ?? "", 10);
	if (!Number.isFinite(page) || page < 1) {
		return { kind: "invalid" };
	}

	if (parts.length === 3) {
		const action = parts[2];
		if (action === "approve" || action === "decline") {
			return { kind: "vote", page, action };
		}
		return { kind: "invalid" };
	}

	return { kind: "navigate", page };
}

export async function resolveRequestListPayload(
	page: number,
	customIdPrefix: string,
): Promise<{
	components: (
		| ReturnType<typeof buildRequestListContainers>["main"]
		| ActionRow
		| ReturnType<typeof buildRequestListContainers>["footer"]
	)[];
}> {
	const status = "pending";
	const all: SanctionRequest[] = await sanctionRequests.listByStatus(status, 200);
	const built = buildRequestListContainers(all, {
		page,
		perPage: PER_PAGE,
		total: all.length,
		status,
		customIdPrefix,
	});

	const components: (
		| ReturnType<typeof buildRequestListContainers>["main"]
		| ActionRow
		| ReturnType<typeof buildRequestListContainers>["footer"]
	)[] = [
		built.main,
		new ActionRow().addComponents(built.approve, built.decline),
		new ActionRow().addComponents(built.back, built.next),
		built.footer,
	];

	return { components };
}

export { PER_PAGE };
