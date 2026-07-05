import { Embed } from "seyfert";
import type { Reviewer, Sanction, SanctionRequest } from "./types";

const STATUS_COLOR: Record<SanctionRequest["status"], `#${string}`> = {
	pending: "#f1c40f",
	approved: "#2ecc71",
	declined: "#e74c3c",
};

const STATUS_LABEL: Record<SanctionRequest["status"], string> = {
	pending: "Pending review",
	approved: "Approved",
	declined: "Declined",
};

export function buildRequestEmbed(request: SanctionRequest): Embed {
	const embed = new Embed()
		.setTitle(
			`${request.type === "ban" ? "Ban" : "Unban"} submission — ${STATUS_LABEL[request.status]}`,
		)
		.setColor(STATUS_COLOR[request.status])
		.setDescription(`Submission ID: \`${request.id}\``)
		.addFields(
			{
				name: "Target",
				value: `<@${request.targetId}> (\`${request.targetTag}\`, \`${request.targetId}\`)`,
			},
			{ name: "Reason", value: request.reason },
			{
				name: "Approvals",
				value: `${request.approvals.length}/${request.requiredApprovals}`,
				inline: true,
			},
			{
				name: "Declines",
				value: `${request.declines.length}/${request.requiredApprovals}`,
				inline: true,
			},
			{
				name: "Submitted by",
				value: `<@${request.submittedBy}> (\`${request.submittedByTag}\`)`,
			},
		)
		.setTimestamp(request.submittedAt);

	if (request.evidence) embed.addFields({ name: "Evidence", value: request.evidence });
	if (request.declineReason)
		embed.addFields({ name: "Decline reason", value: request.declineReason });

	return embed;
}

export function buildSanctionEmbed(sanction: Sanction | undefined, userId: string): Embed {
	if (!sanction) {
		return new Embed()
			.setTitle("No active sanction")
			.setColor("#2ecc71")
			.setDescription(`<@${userId}> (\`${userId}\`) is not on the shared sanction list.`);
	}

	return new Embed()
		.setTitle("Active sanction")
		.setColor("#e74c3c")
		.addFields(
			{ name: "User", value: `<@${sanction.id}> (\`${sanction.id}\`)` },
			{ name: "Reason", value: sanction.reason },
			{ name: "Added by", value: `<@${sanction.addedBy}>` },
			{ name: "Submission ID", value: `\`${sanction.requestId}\`` },
		)
		.setTimestamp(sanction.addedAt);
}

export function buildReviewerListEmbed(reviewerList: Reviewer[]): Embed {
	const embed = new Embed().setTitle("NationSeal reviewers").setColor("#3498db");

	if (reviewerList.length === 0) {
		embed.setDescription(
			"No reviewers configured yet. Ask an owner to add one with `/sanction reviewer-add`.",
		);
		return embed;
	}

	embed.setDescription(
		reviewerList
			.map(
				(reviewer) =>
					`<@${reviewer.id}> — since <t:${Math.floor(new Date(reviewer.addedAt).getTime() / 1000)}:D>`,
			)
			.join("\n"),
	);
	return embed;
}
