import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { GuildState, Reviewer, Sanction, SanctionRequest } from "./types";

interface DatabaseSchema {
	sanctionRequests: SanctionRequest[];
	sanctions: Sanction[];
	reviewers: Reviewer[];
	guildStates: GuildState[];
}

const DEFAULT_SCHEMA: DatabaseSchema = {
	sanctionRequests: [],
	sanctions: [],
	reviewers: [],
	guildStates: [],
};

/**
 * Simple JSON-file database for NationSeal. It keeps the entire dataset in
 * memory and flushes to disk after every mutating operation.
 *
 * This is intentionally small-scale: a single-process bot that stores
 * sanctions, reviewer rosters, and guild metadata. For production loads
 * beyond thousands of records, switch back to a real database.
 */
export class JsonDatabase {
	private filePath: string;
	private data: DatabaseSchema = { ...DEFAULT_SCHEMA };
	private flushPromise: Promise<void> | null = null;
	private loaded = false;
	private modified = false;

	constructor(filePath: string) {
		this.filePath = filePath;
	}

	async connect(): Promise<void> {
		if (this.loaded) return;
		try {
			const raw = await readFile(this.filePath, "utf-8");
			const parsed = JSON.parse(raw) as Partial<DatabaseSchema>;
			this.data = { ...DEFAULT_SCHEMA, ...parsed };
			this.modified = false;
		} catch (error) {
			if (typeof error === "object" && error && "code" in error && error.code === "ENOENT") {
				this.data = { ...DEFAULT_SCHEMA };
				this.modified = false;
				await this.flush();
			} else {
				throw error;
			}
		}
		this.loaded = true;
	}

	private async flush(): Promise<void> {
		if (!this.modified) return;
		// Chain writes so two concurrent mutations can't interleave and
		// produce a torn JSON file.
		this.flushPromise = (this.flushPromise ?? Promise.resolve()).then(async () => {
			if (!this.modified) return;
			await mkdir(dirname(this.filePath), { recursive: true });
			await writeFile(this.filePath, JSON.stringify(this.data, null, "\t"), "utf-8");
			this.modified = false;
		});
		await this.flushPromise;
	}

	private touch(): void {
		this.modified = true;
	}

	// Sanction requests

	async createSanctionRequest(data: Omit<SanctionRequest, "id">): Promise<SanctionRequest> {
		const id = crypto.randomUUID();
		const record = { ...data, id } as unknown as SanctionRequest;
		this.data.sanctionRequests.push(record);
		this.touch();
		await this.flush();
		return record;
	}

	async getSanctionRequest(id: string): Promise<SanctionRequest | undefined> {
		return this.data.sanctionRequests.find((r) => r.id === id);
	}

	async updateSanctionRequest(
		id: string,
		patch: Partial<SanctionRequest>,
	): Promise<SanctionRequest> {
		const index = this.data.sanctionRequests.findIndex((r) => r.id === id);
		if (index === -1) {
			throw new Error(`Sanction request ${id} not found`);
		}
		const updated = { ...this.data.sanctionRequests[index], ...patch, id };
		this.data.sanctionRequests[index] = updated as SanctionRequest;
		this.touch();
		await this.flush();
		return updated as SanctionRequest;
	}

	async listSanctionRequestsByStatus(
		status: SanctionRequest["status"],
		limit: number,
	): Promise<SanctionRequest[]> {
		return this.data.sanctionRequests
			.filter((r) => r.status === status)
			.sort((a, b) => new Date(b.submittedAt).getTime() - new Date(a.submittedAt).getTime())
			.slice(0, limit);
	}

	// Sanctions

	async getSanction(targetId: string): Promise<Sanction | undefined> {
		return this.data.sanctions.find((s) => s.id === targetId);
	}

	async upsertSanction(targetId: string, data: Omit<Sanction, "id">): Promise<Sanction> {
		const index = this.data.sanctions.findIndex((s) => s.id === targetId);
		const record = { ...data, id: targetId } as Sanction;
		if (index === -1) {
			this.data.sanctions.push(record);
		} else {
			this.data.sanctions[index] = record;
		}
		this.touch();
		await this.flush();
		return record;
	}

	async removeSanction(targetId: string): Promise<void> {
		this.data.sanctions = this.data.sanctions.filter((s) => s.id !== targetId);
		this.touch();
		await this.flush();
	}

	async listAllSanctions(): Promise<Sanction[]> {
		return [...this.data.sanctions];
	}

	// Reviewers

	async isReviewer(userId: string): Promise<boolean> {
		return this.data.reviewers.some((r) => r.id === userId);
	}

	async addReviewer(userId: string, addedBy: string): Promise<Reviewer> {
		const existing = this.data.reviewers.find((r) => r.id === userId);
		if (existing) return existing;
		const record: Reviewer = {
			id: userId,
			addedBy,
			addedAt: new Date().toISOString(),
		};
		this.data.reviewers.push(record);
		this.touch();
		await this.flush();
		return record;
	}

	async removeReviewer(userId: string): Promise<void> {
		this.data.reviewers = this.data.reviewers.filter((r) => r.id !== userId);
		this.touch();
		await this.flush();
	}

	async listReviewers(): Promise<Reviewer[]> {
		return [...this.data.reviewers];
	}

	// Guild state

	async getGuildState(guildId: string): Promise<GuildState | undefined> {
		return this.data.guildStates.find((g) => g.id === guildId);
	}

	async setGuildState(
		guildId: string,
		patch: Partial<Omit<GuildState, "id">>,
	): Promise<GuildState> {
		const index = this.data.guildStates.findIndex((g) => g.id === guildId);
		let record: GuildState;
		if (index === -1) {
			record = {
				id: guildId,
				antiraidBlocked: false,
				antiraidBots: [],
				enforcementStatus: "auto_enforced",
				antiraidNotifiedAt: null,
				lastEnforcementAt: null,
				...patch,
			} as GuildState;
			this.data.guildStates.push(record);
		} else {
			record = { ...this.data.guildStates[index], ...patch, id: guildId } as GuildState;
			this.data.guildStates[index] = record;
		}
		this.touch();
		await this.flush();
		return record;
	}

	async markGuildEnforced(guildId: string): Promise<void> {
		const index = this.data.guildStates.findIndex((g) => g.id === guildId);
		const patch: Partial<GuildState> = {
			enforcementStatus: "manually_enforced",
			lastEnforcementAt: new Date().toISOString(),
		};
		if (index === -1) {
			this.data.guildStates.push({
				id: guildId,
				antiraidBlocked: false,
				antiraidBots: [],
				enforcementStatus: "manually_enforced",
				antiraidNotifiedAt: null,
				lastEnforcementAt: new Date().toISOString(),
			});
		} else {
			this.data.guildStates[index] = {
				...this.data.guildStates[index],
				...patch,
				id: guildId,
			} as GuildState;
		}
		this.touch();
		await this.flush();
	}

	async close(): Promise<void> {
		if (this.loaded) {
			await this.flush();
		}
	}

	/** Internal helper for one-off migrations: replaces the whole dataset. */
	importData(data: DatabaseSchema): void {
		this.data = { ...DEFAULT_SCHEMA, ...data };
		this.modified = true;
	}
}
