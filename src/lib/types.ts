export type SanctionRequestType = "ban" | "unban";

export type SanctionRequestStatus = "pending" | "approved" | "declined";

export interface SanctionRequest {
	id: string;
	type: SanctionRequestType;
	targetId: string;
	targetTag: string;
	reason: string;
	evidence: string | null;
	status: SanctionRequestStatus;
	submittedBy: string;
	submittedByTag: string;
	guildId: string;
	requiredApprovals: number;
	approvals: string[];
	declines: string[];
	declineReason: string | null;
	submittedAt: string;
	resolvedAt: string | null;
}

export interface Sanction {
	id: string;
	reason: string;
	requestId: string;
	addedBy: string;
	addedAt: string;
}

export interface Reviewer {
	id: string;
	addedBy: string;
	addedAt: string;
}

export type GuildEnforcementStatus = "auto_enforced" | "antiraid_blocked" | "manually_enforced";

export interface GuildState {
	id: string;
	antiraidBlocked: boolean;
	antiraidBots: string[];
	enforcementStatus: GuildEnforcementStatus;
	antiraidNotifiedAt: string | null;
	lastEnforcementAt: string | null;
}
