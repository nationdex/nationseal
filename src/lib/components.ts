import {
	Button,
	Container,
	type ContainerBuilderComponents,
	Separator,
	TextDisplay,
} from "seyfert";
import { MessageFlags, Spacing } from "seyfert/lib/types";
import type { Reviewer, Sanction, SanctionRequest } from "./types";

/** Components v2 message flag. Required for messages built with Container/TextDisplay. */
export const COMPONENTS_V2_FLAG = MessageFlags.IsComponentsV2;

const STATUS_COLOR: Record<SanctionRequest["status"], number> = {
	pending: 0xf1c40f,
	approved: 0x2ecc71,
	declined: 0xe74c3c,
};

const STATUS_LABEL: Record<SanctionRequest["status"], string> = {
	pending: "Pending review",
	approved: "Approved",
	declined: "Declined",
};

/** Wraps a list of components inside a single Container — the root of a Components v2 message. */
export function v2Container(
	components: ContainerBuilderComponents[],
	options: { color?: number; spoiler?: boolean } = {},
): Container {
	const container = new Container();
	if (typeof options.color === "number") {
		container.setColor(options.color);
	}
	if (options.spoiler) {
		container.setSpoiler(true);
	}
	if (components.length > 0) container.addComponents(components);
	return container;
}

export function text(content: string): TextDisplay {
	return new TextDisplay().setContent(content);
}

/** Convenience wrapper for a simple Components v2 message containing only text. */
export function textOnlyContainer(content: string): Container {
	return v2Container([text(content)]);
}

export function divider(spacing: Spacing = Spacing.Small): Separator {
	return new Separator().setDivider(true).setSpacing(spacing);
}

export function spacer(spacing: Spacing = Spacing.Small): Separator {
	return new Separator().setDivider(false).setSpacing(spacing);
}

function escapeMarkdown(text: string): string {
	// Discord reserves * _ ` ~ | > for markdown, so neutralise them when the
	// user-supplied fields could be interpreted as formatting.
	return text.replace(/([*_`~|>])/g, "\\$1");
}

function formatRequestBody(request: SanctionRequest): string {
	const lines: string[] = [
		`## ${request.type === "ban" ? "Ban" : "Unban"} submission — ${STATUS_LABEL[request.status]}`,
		`Submission ID: \`${request.id}\``,
		`> **Target**\n<@${request.targetId}> (\`${escapeMarkdown(request.targetTag)}\`, \`${request.targetId}\`)`,
		`> **Reason**\n${escapeMarkdown(request.reason)}`,
		`**Approvals:** ${request.approvals.length}/${request.requiredApprovals}  •  **Declines:** ${request.declines.length}/${request.requiredApprovals}`,
		`**Submitted by** <@${request.submittedBy}> (\`${escapeMarkdown(request.submittedByTag)}\`)`,
	];

	if (request.evidence) {
		lines.push(`> **Evidence**\n${request.evidence}`);
	}
	if (request.declineReason) {
		lines.push(`> **Decline reason**\n${escapeMarkdown(request.declineReason)}`);
	}

	lines.push(`-# <t:${Math.floor(new Date(request.submittedAt).getTime() / 1000)}:R>`);
	return lines.join("\n");
}

/** Build a single submission as a Container payload (Components v2). */
export function buildRequestContainer(request: SanctionRequest): Container {
	return v2Container([text(formatRequestBody(request)), divider()], {
		color: STATUS_COLOR[request.status],
	});
}

/** Build the paginated view for sanction requests (one per page with approve/decline buttons). */
export function buildRequestListContainers(
	requests: SanctionRequest[],
	options: {
		page: number;
		perPage: number;
		total: number;
		status?: SanctionRequest["status"];
		customIdPrefix: string;
	},
): {
	main: Container;
	approve: Button;
	decline: Button;
	back: Button;
	next: Button;
	footer: TextDisplay;
} {
	const totalPages = Math.max(1, Math.ceil(options.total / options.perPage));
	const safePage = Math.min(Math.max(1, options.page), totalPages);
	const start = (safePage - 1) * options.perPage;
	const slice = requests.slice(start, start + options.perPage);
	const currentRequest = slice[0];

	const headerTitle = options.status
		? `Sanction submissions — ${STATUS_LABEL[options.status]}`
		: "Sanction submissions";

	const mainComponents: ContainerBuilderComponents[] = [];

	if (currentRequest) {
		mainComponents.push(text(formatRequestBody(currentRequest)));
		mainComponents.push(divider());
	} else {
		mainComponents.push(text(`## ${headerTitle}\nNo submissions found.`));
	}

	mainComponents.push(
		text(`Page **${safePage}** / **${totalPages}** — ${options.total} submission(s) total`),
	);

	const main = v2Container(mainComponents, {
		color: currentRequest ? STATUS_COLOR[currentRequest.status] : undefined,
	});

	const isPending = currentRequest?.status === "pending";

	const approve = new Button()
		.setCustomId(`${options.customIdPrefix}|${safePage}|approve`)
		.setStyle(3) // Success green
		.setLabel("Approve")
		.setDisabled(!isPending);

	const decline = new Button()
		.setCustomId(`${options.customIdPrefix}|${safePage}|decline`)
		.setStyle(4) // Danger red
		.setLabel("Decline")
		.setDisabled(!isPending);

	const back = new Button()
		.setCustomId(`${options.customIdPrefix}|${safePage - 1}`)
		.setStyle(2)
		.setLabel("Previous")
		.setDisabled(safePage <= 1);

	const next = new Button()
		.setCustomId(`${options.customIdPrefix}|${safePage + 1}`)
		.setStyle(2)
		.setLabel("Next")
		.setDisabled(safePage >= totalPages);

	const footer = text(
		"-# Use the buttons to vote or navigate. This message only updates for the user that triggered it.",
	);

	return { main, approve, decline, back, next, footer };
}

/** Build the container for the `/sanction check` command. */
export function buildSanctionContainer(sanction: Sanction | undefined, userId: string): Container {
	if (!sanction) {
		return v2Container(
			[
				text(
					`## No active sanction\n<@${userId}> (\`${userId}\`) is not on the shared sanction list.`,
				),
			],
			{ color: 0x2ecc71 },
		);
	}

	return v2Container(
		[
			text(
				[
					`## Active sanction`,
					`**User:** <@${sanction.id}> (\`${sanction.id}\`)`,
					`**Reason:** ${escapeMarkdown(sanction.reason)}`,
					`**Added by:** <@${sanction.addedBy}>`,
					`**Submission ID:** \`${sanction.requestId}\``,
					`-# <t:${Math.floor(new Date(sanction.addedAt).getTime() / 1000)}:R>`,
				].join("\n"),
			),
		],
		{ color: 0xe74c3c },
	);
}

/** Build the container for the `/sanction reviewer-list` command. */
export function buildReviewerListContainer(reviewerList: Reviewer[]): Container {
	const body =
		reviewerList.length === 0
			? "No reviewers configured yet. Ask an owner to add one with `/sanction reviewer-add`."
			: reviewerList
					.map(
						(reviewer) =>
							`• <@${reviewer.id}> — since <t:${Math.floor(new Date(reviewer.addedAt).getTime() / 1000)}:D>`,
					)
					.join("\n");

	return v2Container([text(`## NationSeal reviewers\n${body}`)], {
		color: 0x3498db,
	});
}
