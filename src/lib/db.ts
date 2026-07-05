import { config } from "../config";
import { JsonDatabase } from "./jsondb";
import type { GuildState, Reviewer, Sanction, SanctionRequest } from "./types";

export const db = new JsonDatabase(config.databasePath);

/**
 * Loads the JSON database file into memory. Safe to call multiple times; the
 * file is only read on the first call.
 */
export async function connectDatabase(): Promise<void> {
	await db.connect();
}

export const sanctionRequests = {
	async create(data: Omit<SanctionRequest, "id">): Promise<SanctionRequest> {
		return db.createSanctionRequest(data);
	},

	async get(id: string): Promise<SanctionRequest | undefined> {
		return db.getSanctionRequest(id);
	},

	async update(id: string, patch: Partial<SanctionRequest>): Promise<SanctionRequest> {
		return db.updateSanctionRequest(id, patch);
	},

	async listByStatus(status: SanctionRequest["status"], limit = 10): Promise<SanctionRequest[]> {
		return db.listSanctionRequestsByStatus(status, limit);
	},
};

export const sanctions = {
	async get(targetId: string): Promise<Sanction | undefined> {
		return db.getSanction(targetId);
	},

	async upsert(targetId: string, data: Omit<Sanction, "id">): Promise<Sanction> {
		return db.upsertSanction(targetId, data);
	},

	async remove(targetId: string): Promise<void> {
		return db.removeSanction(targetId);
	},

	async listAll(): Promise<Sanction[]> {
		return db.listAllSanctions();
	},
};

export const reviewers = {
	async isReviewer(userId: string): Promise<boolean> {
		return db.isReviewer(userId);
	},

	async add(userId: string, addedBy: string): Promise<Reviewer> {
		return db.addReviewer(userId, addedBy);
	},

	async remove(userId: string): Promise<void> {
		return db.removeReviewer(userId);
	},

	async list(): Promise<Reviewer[]> {
		return db.listReviewers();
	},
};

export const guildState = {
	async get(guildId: string): Promise<GuildState | undefined> {
		return db.getGuildState(guildId);
	},

	async set(guildId: string, patch: Partial<Omit<GuildState, "id">>): Promise<GuildState> {
		return db.setGuildState(guildId, patch);
	},

	async markEnforced(guildId: string): Promise<void> {
		return db.markGuildEnforced(guildId);
	},
};

/** Flushes any pending writes and closes the database cleanly. */
export async function closeDatabase(): Promise<void> {
	await db.close();
}
