"""Shared domain types. Mirrors the JSON schema used by the TS implementation."""

from typing import Literal, TypedDict

SanctionRequestType = Literal["ban", "unban"]
SanctionRequestStatus = Literal["pending", "approved", "declined"]
GuildEnforcementStatus = Literal["auto_enforced", "antiraid_blocked", "manually_enforced"]


class SanctionRequest(TypedDict):
	id: str
	type: SanctionRequestType
	targetId: str
	targetTag: str
	reason: str
	evidence: str | None
	status: SanctionRequestStatus
	submittedBy: str
	submittedByTag: str
	guildId: str
	requiredApprovals: int
	approvals: list[str]
	declines: list[str]
	declineReason: str | None
	submittedAt: str
	resolvedAt: str | None


class Sanction(TypedDict):
	id: str
	reason: str
	requestId: str
	addedBy: str
	addedAt: str


class Reviewer(TypedDict):
	id: str
	addedBy: str
	addedAt: str


class GuildState(TypedDict):
	id: str
	antiraidBlocked: bool
	antiraidBots: list[str]
	enforcementStatus: GuildEnforcementStatus
	antiraidNotifiedAt: str | None
	lastEnforcementAt: str | None


class DatabaseSchema(TypedDict):
	sanctionRequests: list[SanctionRequest]
	sanctions: list[Sanction]
	reviewers: list[Reviewer]
	guildStates: list[GuildState]
