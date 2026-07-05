import type { UsingClient } from "seyfert";
import { config } from "../config";
import { sanctionRequests, sanctions } from "./db";
import type { SanctionRequest, SanctionRequestType } from "./types";

export interface SubmitRequestInput {
	type: SanctionRequestType;
	targetId: string;
	targetTag: string;
	reason: string;
	evidence: string | null;
	submittedBy: string;
	submittedByTag: string;
	guildId: string;
}

export async function submitRequest(input: SubmitRequestInput): Promise<SanctionRequest> {
	return sanctionRequests.create({
		...input,
		status: "pending",
		requiredApprovals: config.requiredApprovals,
		approvals: [],
		declines: [],
		declineReason: null,
		submittedAt: new Date().toISOString(),
		resolvedAt: null,
	});
}

export type VoteDecision = "approve" | "decline";

export interface VoteResult {
	request: SanctionRequest;
	/** Whether this vote just caused the request to resolve (approved/declined). */
	justResolved: boolean;
	enforcement?: EnforcementSummary;
}

export class VoteError extends Error {}

export async function castVote(
	client: UsingClient,
	requestId: string,
	reviewerId: string,
	decision: VoteDecision,
	declineReason?: string,
): Promise<VoteResult> {
	const request = await sanctionRequests.get(requestId);
	if (!request) throw new VoteError(`No submission found with id \`${requestId}\`.`);
	if (request.status !== "pending") {
		throw new VoteError(`That submission was already **${request.status}**.`);
	}

	const approvals = new Set(request.approvals);
	const declines = new Set(request.declines);

	if (decision === "approve") {
		declines.delete(reviewerId);
		approvals.add(reviewerId);
	} else {
		approvals.delete(reviewerId);
		declines.add(reviewerId);
	}

	const patch: Partial<SanctionRequest> = {
		approvals: [...approvals],
		declines: [...declines],
	};

	let justResolved = false;
	let enforcement: EnforcementSummary | undefined;

	if (approvals.size >= request.requiredApprovals) {
		patch.status = "approved";
		patch.resolvedAt = new Date().toISOString();
		justResolved = true;
	} else if (declines.size >= request.requiredApprovals) {
		patch.status = "declined";
		patch.resolvedAt = new Date().toISOString();
		patch.declineReason = declineReason ?? request.declineReason ?? null;
		justResolved = true;
	}

	const updated = await sanctionRequests.update(requestId, patch);

	if (justResolved && updated.status === "approved") {
		enforcement = await applyApprovedRequest(client, updated);
	}

	if (justResolved) {
		client.logger.info(
			`[nationseal] AUDIT submission=${updated.id} resolved=${updated.status} reviewers=${updated.approvals.length + updated.declines.length}`,
		);
	}

	return { request: updated, justResolved, enforcement };
}

export interface EnforcementSummary {
	guildsAttempted: number;
	guildsSucceeded: number;
}

/** Applies an approved submission: updates the shared list and enforces it live. */
async function applyApprovedRequest(
	client: UsingClient,
	request: SanctionRequest,
): Promise<EnforcementSummary> {
	if (request.type === "ban") {
		await sanctions.upsert(request.targetId, {
			reason: request.reason,
			requestId: request.id,
			addedBy: request.submittedBy,
			addedAt: new Date().toISOString(),
		});
		return banAcrossGuilds(client, request.targetId, `NationSeal sanction: ${request.reason}`);
	}

	await sanctions.remove(request.targetId);
	return unbanAcrossGuilds(client, request.targetId, "NationSeal sanction appeal approved");
}

/**
 * Returns the set of guild IDs the bot can currently see, while refusing to
 * ever ban the bot itself, the application owner, or any NationSeal owner.
 */
function isProtectedUser(userId: string, client: UsingClient): boolean {
	if (userId === client.botId) return true;
	if (config.ownerIds.includes(userId)) return true;
	return false;
}

async function getCachedGuildIds(client: UsingClient): Promise<string[]> {
	// Use the public `values()` API so we get fully-typed Guild objects with a
	// canonical `.id` field instead of scraping the cache's internal
	// `"<namespace>.<id>"` key encoding.
	const values = (await client.cache.guilds?.values()) ?? [];
	return values
		.map((guild) => guild?.id)
		.filter((id): id is string => typeof id === "string" && id.length > 0);
}

async function banSingleUserInGuild(
	client: UsingClient,
	guildId: string,
	userId: string,
	reason: string,
): Promise<boolean> {
	if (isProtectedUser(userId, client)) {
		client.logger.warn(`[nationseal] Refusing to ban protected user ${userId} in ${guildId}.`);
		return false;
	}
	try {
		await client.bans.create(
			guildId,
			userId,
			config.banDeleteMessageSeconds > 0
				? { delete_message_seconds: config.banDeleteMessageSeconds }
				: {},
			reason,
		);
		return true;
	} catch (error) {
		client.logger.warn(`[nationseal] Could not ban ${userId} in guild ${guildId}:`, error);
		return false;
	}
}

export async function banAcrossGuilds(
	client: UsingClient,
	userId: string,
	reason: string,
): Promise<EnforcementSummary> {
	const guildIds = await getCachedGuildIds(client);
	let succeeded = 0;

	for (const guildId of guildIds) {
		if (await banSingleUserInGuild(client, guildId, userId, reason)) {
			succeeded++;
		}
	}

	return { guildsAttempted: guildIds.length, guildsSucceeded: succeeded };
}

export async function unbanAcrossGuilds(
	client: UsingClient,
	userId: string,
	reason: string,
): Promise<EnforcementSummary> {
	const guildIds = await getCachedGuildIds(client);
	let succeeded = 0;

	for (const guildId of guildIds) {
		try {
			await client.bans.remove(guildId, userId, reason);
			succeeded++;
		} catch (error) {
			client.logger.warn(`[nationseal] Could not unban ${userId} in guild ${guildId}:`, error);
		}
	}

	return { guildsAttempted: guildIds.length, guildsSucceeded: succeeded };
}

// Per-guild in-flight guards so that a burst of `guildCreate` events (e.g. a
// bot shard reconnect, or a server farm inviting the bot many times in a
// short window) can't trigger overlapping ban syncs in the same guild.
const inFlightGuildSyncs = new Set<string>();

/** Applies every currently active sanction to a single guild, used when the bot joins a new server. */
export async function enforceAllSanctionsOnGuild(
	client: UsingClient,
	guildId: string,
): Promise<{ banned: number; total: number }> {
	if (inFlightGuildSyncs.has(guildId)) {
		client.logger.info(
			`[nationseal] Skipping duplicate guild sync for ${guildId}; already in progress.`,
		);
		return { banned: 0, total: 0 };
	}
	inFlightGuildSyncs.add(guildId);

	try {
		const allActive = await sanctions.listAll();
		if (allActive.length === 0) return { banned: 0, total: 0 };

		// Never include protected users (the bot itself, owners) in a bulk
		// ban sync — Discord would reject these anyway, but skipping them
		// here also keeps the audit log clean.
		const botId = client.botId;
		const eligible = allActive.filter((s) => !isProtectedUser(s.id, client) && s.id !== botId);
		if (eligible.length === 0) return { banned: 0, total: allActive.length };

		const BATCH_SIZE = 200;
		let banned = 0;

		for (let i = 0; i < eligible.length; i += BATCH_SIZE) {
			const batch = eligible.slice(i, i + BATCH_SIZE);
			try {
				const result = await client.bans.bulkCreate(
					guildId,
					{
						user_ids: batch.map((sanction) => sanction.id),
						...(config.banDeleteMessageSeconds > 0
							? { delete_message_seconds: config.banDeleteMessageSeconds }
							: {}),
					},
					"NationSeal: syncing shared sanction list",
				);
				banned += result.banned_users.length;
			} catch (error) {
				client.logger.warn(
					`[nationseal] Could not bulk-sync sanctions to guild ${guildId}:`,
					error,
				);
			}
		}

		client.logger.info(
			`[nationseal] AUDIT guildSync guild=${guildId} synced=${banned}/${eligible.length} (skipped ${allActive.length - eligible.length} protected)`,
		);

		return { banned, total: allActive.length };
	} finally {
		inFlightGuildSyncs.delete(guildId);
	}
}
