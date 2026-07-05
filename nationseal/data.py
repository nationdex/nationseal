"""Data layer: models, JSON database, and business logic (voting, enforcement)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict, cast

import discord

# ── Domain types ───────────────────────────────────────────────────────────

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


# ── Runtime state (initialized by init_runtime()) ─────────────────────────

_db: JsonDatabase | None = None
_sanction_requests: SanctionRequests | None = None
_sanctions: Sanctions | None = None
_reviewers: Reviewers | None = None
_guild_states: GuildStateCollection | None = None
_required_approvals: int = 2
_ban_delete_message_seconds: int = 0
_owner_ids: list[str] = []
_reviewer_channel_id: int | None = None


def init_runtime(
	database_path: str,
	required_approvals: int,
	ban_delete_message_seconds: int,
	owner_ids: list[str],
	reviewer_channel_id: int | None,
) -> None:
	"""Wire the global DB + config used by the business-logic functions below."""
	global _db, _sanction_requests, _sanctions, _reviewers, _guild_states
	global _required_approvals, _ban_delete_message_seconds, _owner_ids, _reviewer_channel_id

	_db = JsonDatabase(database_path)
	_sanction_requests = SanctionRequests(_db)
	_sanctions = Sanctions(_db)
	_reviewers = Reviewers(_db)
	_guild_states = GuildStateCollection(_db)
	_required_approvals = required_approvals
	_ban_delete_message_seconds = ban_delete_message_seconds
	_owner_ids = owner_ids
	_reviewer_channel_id = reviewer_channel_id


def _now_iso() -> str:
	return datetime.now(UTC).isoformat()


# ── Database ──────────────────────────────────────────────────────────────


class JsonDatabase:
	def __init__(self, file_path: str) -> None:
		self.file_path = Path(file_path)
		self.data: DatabaseSchema = {
			"sanctionRequests": [],
			"sanctions": [],
			"reviewers": [],
			"guildStates": [],
		}
		self.loaded = False
		self.modified = False

	async def connect(self) -> None:
		if self.loaded:
			return
		if self.file_path.exists():
			raw = self.file_path.read_text(encoding="utf-8")
			parsed = json.loads(raw)
			self.data = {**self.data, **parsed}
			self.modified = False
		else:
			self.data = {**self.data}
			self.modified = False
			self.flush()
		self.loaded = True

	def flush(self) -> None:
		if not self.modified:
			return
		self.file_path.parent.mkdir(parents=True, exist_ok=True)
		self.file_path.write_text(json.dumps(self.data, indent="\t"), encoding="utf-8")
		self.modified = False

	def touch(self) -> None:
		self.modified = True

	# Sanction requests

	async def create_sanction_request(self, data: SanctionRequest) -> SanctionRequest:
		record: SanctionRequest = {**data, "id": str(uuid.uuid4())}
		self.data["sanctionRequests"].append(record)
		self.touch()
		self.flush()
		return record

	async def get_sanction_request(self, request_id: str) -> SanctionRequest | None:
		for request in self.data["sanctionRequests"]:
			if request["id"] == request_id:
				return request
		return None

	async def update_sanction_request(
		self, request_id: str, patch: dict[str, object]
	) -> SanctionRequest:
		for index, request in enumerate(self.data["sanctionRequests"]):
			if request["id"] == request_id:
				updated: SanctionRequest = {**request, **patch, "id": request_id}  # type: ignore[typeddict-item]
				self.data["sanctionRequests"][index] = updated
				self.touch()
				self.flush()
				return updated
		raise ValueError(f"Sanction request {request_id} not found")

	async def list_sanction_requests_by_status(
		self, status: SanctionRequestStatus, limit: int
	) -> list[SanctionRequest]:
		filtered = [r for r in self.data["sanctionRequests"] if r["status"] == status]
		filtered.sort(key=lambda r: r["submittedAt"], reverse=True)
		return filtered[:limit]

	# Sanctions

	async def get_sanction(self, target_id: str) -> Sanction | None:
		for sanction in self.data["sanctions"]:
			if sanction["id"] == target_id:
				return sanction
		return None

	async def upsert_sanction(self, target_id: str, data: Sanction) -> Sanction:
		record: Sanction = {**data, "id": target_id}
		for index, sanction in enumerate(self.data["sanctions"]):
			if sanction["id"] == target_id:
				self.data["sanctions"][index] = record
				self.touch()
				self.flush()
				return record
		self.data["sanctions"].append(record)
		self.touch()
		self.flush()
		return record

	async def remove_sanction(self, target_id: str) -> None:
		self.data["sanctions"] = [s for s in self.data["sanctions"] if s["id"] != target_id]
		self.touch()
		self.flush()

	async def list_all_sanctions(self) -> list[Sanction]:
		return list(self.data["sanctions"])

	# Reviewers

	async def is_reviewer(self, user_id: str) -> bool:
		return any(r["id"] == user_id for r in self.data["reviewers"])

	async def add_reviewer(self, user_id: str, added_by: str) -> Reviewer:
		existing = next((r for r in self.data["reviewers"] if r["id"] == user_id), None)
		if existing:
			return existing
		record: Reviewer = {"id": user_id, "addedBy": added_by, "addedAt": _now_iso()}
		self.data["reviewers"].append(record)
		self.touch()
		self.flush()
		return record

	async def remove_reviewer(self, user_id: str) -> None:
		self.data["reviewers"] = [r for r in self.data["reviewers"] if r["id"] != user_id]
		self.touch()
		self.flush()

	async def list_reviewers(self) -> list[Reviewer]:
		return list(self.data["reviewers"])

	# Guild state

	async def get_guild_state(self, guild_id: str) -> GuildState | None:
		for state in self.data["guildStates"]:
			if state["id"] == guild_id:
				return state
		return None

	async def set_guild_state(self, guild_id: str, patch: dict[str, object]) -> GuildState:
		for index, state in enumerate(self.data["guildStates"]):
			if state["id"] == guild_id:
				updated: GuildState = {**state, **patch, "id": guild_id}  # type: ignore[typeddict-item]
				self.data["guildStates"][index] = updated
				self.touch()
				self.flush()
				return updated
		record: GuildState = {
			"id": guild_id,
			"antiraidBlocked": False,
			"antiraidBots": [],
			"enforcementStatus": "auto_enforced",
			"antiraidNotifiedAt": None,
			"lastEnforcementAt": None,
			**patch,  # type: ignore[typeddict-item]
		}
		self.data["guildStates"].append(record)
		self.touch()
		self.flush()
		return record

	async def mark_guild_enforced(self, guild_id: str) -> None:
		now = _now_iso()
		for index, state in enumerate(self.data["guildStates"]):
			if state["id"] == guild_id:
				updated: GuildState = {
					**state,
					"enforcementStatus": "manually_enforced",
					"lastEnforcementAt": now,
					"id": guild_id,
				}
				self.data["guildStates"][index] = updated
				self.touch()
				self.flush()
				return
		record: GuildState = {
			"id": guild_id,
			"antiraidBlocked": False,
			"antiraidBots": [],
			"enforcementStatus": "manually_enforced",
			"antiraidNotifiedAt": None,
			"lastEnforcementAt": now,
		}
		self.data["guildStates"].append(record)
		self.touch()
		self.flush()

	async def close(self) -> None:
		if self.loaded:
			self.flush()


# ── Collection wrappers ──────────────────────────────────────────────────


class SanctionRequests:
	def __init__(self, db: JsonDatabase) -> None:
		self.db = db

	async def create(self, data: SanctionRequest) -> SanctionRequest:
		return await self.db.create_sanction_request(data)

	async def get(self, request_id: str) -> SanctionRequest | None:
		return await self.db.get_sanction_request(request_id)

	async def update(self, request_id: str, patch: dict[str, object]) -> SanctionRequest:
		return await self.db.update_sanction_request(request_id, patch)

	async def list_by_status(
		self, status: SanctionRequestStatus, limit: int = 10
	) -> list[SanctionRequest]:
		return await self.db.list_sanction_requests_by_status(status, limit)


class Sanctions:
	def __init__(self, db: JsonDatabase) -> None:
		self.db = db

	async def get(self, target_id: str) -> Sanction | None:
		return await self.db.get_sanction(target_id)

	async def upsert(self, target_id: str, data: Sanction) -> Sanction:
		return await self.db.upsert_sanction(target_id, data)

	async def remove(self, target_id: str) -> None:
		await self.db.remove_sanction(target_id)

	async def list_all(self) -> list[Sanction]:
		return await self.db.list_all_sanctions()


class Reviewers:
	def __init__(self, db: JsonDatabase) -> None:
		self.db = db

	async def is_reviewer(self, user_id: str) -> bool:
		return await self.db.is_reviewer(user_id)

	async def add(self, user_id: str, added_by: str) -> Reviewer:
		return await self.db.add_reviewer(user_id, added_by)

	async def remove(self, user_id: str) -> None:
		await self.db.remove_reviewer(user_id)

	async def list_all(self) -> list[Reviewer]:
		return await self.db.list_reviewers()


class GuildStateCollection:
	def __init__(self, db: JsonDatabase) -> None:
		self.db = db

	async def get(self, guild_id: str) -> GuildState | None:
		return await self.db.get_guild_state(guild_id)

	async def set(self, guild_id: str, patch: dict[str, object]) -> GuildState:
		return await self.db.set_guild_state(guild_id, patch)

	async def mark_enforced(self, guild_id: str) -> None:
		await self.db.mark_guild_enforced(guild_id)


# Singleton accessors (callers don't need to pass collection objects around).


def db() -> JsonDatabase:
	assert _db is not None, "init_runtime() must be called before using the database"
	return _db


def sanction_requests() -> SanctionRequests:
	assert _sanction_requests is not None, "init_runtime() must be called first"
	return _sanction_requests


def sanctions() -> Sanctions:
	assert _sanctions is not None, "init_runtime() must be called first"
	return _sanctions


def reviewers() -> Reviewers:
	assert _reviewers is not None, "init_runtime() must be called first"
	return _reviewers


def guild_states() -> GuildStateCollection:
	assert _guild_states is not None, "init_runtime() must be called first"
	return _guild_states


# ── Voting + enforcement ────────────────────────────────────────────────

logger = logging.getLogger("nationseal")


class VoteError(Exception):
	pass


class EnforcementSummary:
	def __init__(self) -> None:
		self.guilds_attempted = 0
		self.guilds_succeeded = 0


def _is_protected_user(user_id: int | str, client: discord.Client) -> bool:
	uid = str(user_id)
	if client.user and uid == str(client.user.id):
		return True
	return uid in _owner_ids


def _get_cached_guild_ids(client: discord.Client) -> list[int]:
	return [guild.id for guild in client.guilds]


async def _ban_single_user_in_guild(
	client: discord.Client, guild_id: int, user_id: int, reason: str
) -> bool:
	if _is_protected_user(user_id, client):
		logger.warning("[nationseal] Refusing to ban protected user %s in %s.", user_id, guild_id)
		return False

	guild = client.get_guild(guild_id)
	if guild is None:
		return False

	try:
		if _ban_delete_message_seconds > 0:
			await guild.ban(
				discord.Object(id=user_id),
				reason=reason,
				delete_message_seconds=_ban_delete_message_seconds,
			)
		else:
			await guild.ban(discord.Object(id=user_id), reason=reason)
		return True
	except Exception as exc:  # noqa: BLE001
		logger.warning("[nationseal] Could not ban %s in guild %s: %s", user_id, guild_id, exc)
		return False


async def ban_across_guilds(
	client: discord.Client, user_id: int | str, reason: str
) -> EnforcementSummary:
	uid = int(user_id)
	summary = EnforcementSummary()

	for guild_id in _get_cached_guild_ids(client):
		summary.guilds_attempted += 1
		if await _ban_single_user_in_guild(client, guild_id, uid, reason):
			summary.guilds_succeeded += 1

	return summary


async def unban_across_guilds(
	client: discord.Client, user_id: int | str, reason: str
) -> EnforcementSummary:
	uid = int(user_id)
	summary = EnforcementSummary()

	for guild_id in _get_cached_guild_ids(client):
		guild = client.get_guild(guild_id)
		if guild is None:
			continue
		summary.guilds_attempted += 1
		try:
			await guild.unban(discord.Object(id=uid), reason=reason)
			summary.guilds_succeeded += 1
		except Exception as exc:  # noqa: BLE001
			logger.warning(
				"[nationseal] Could not unban %s in guild %s: %s", user_id, guild_id, exc
			)

	return summary


_in_flight_guild_syncs: set[int] = set()


async def enforce_all_sanctions_on_guild(
	client: discord.Client, guild_id: int | str
) -> dict[str, int]:
	gid = int(guild_id)
	if gid in _in_flight_guild_syncs:
		logger.info("[nationseal] Skipping duplicate guild sync for %s; already in progress.", gid)
		return {"banned": 0, "total": 0}

	_in_flight_guild_syncs.add(gid)
	try:
		all_active = await sanctions().list_all()
		if not all_active:
			return {"banned": 0, "total": 0}

		eligible = [s for s in all_active if not _is_protected_user(s["id"], client)]
		if not eligible:
			return {"banned": 0, "total": len(all_active)}

		guild = client.get_guild(gid)
		if guild is None:
			return {"banned": 0, "total": len(all_active)}

		banned = 0
		batch_size = 200
		for i in range(0, len(eligible), batch_size):
			batch = eligible[i : i + batch_size]
			try:
				result = await guild.bulk_ban(
					[discord.Object(id=int(s["id"])) for s in batch],
					reason="NationSeal: syncing shared sanction list",
					delete_message_seconds=_ban_delete_message_seconds or 86400,
				)
				banned += len(result.banned_users)  # type: ignore
			except Exception as exc:  # noqa: BLE001
				logger.warning(
					"[nationseal] Could not bulk-sync sanctions to guild %s: %s", gid, exc
				)

		logger.info(
			"[nationseal] AUDIT guildSync guild=%s synced=%d/%d (skipped %d protected)",
			gid,
			banned,
			len(eligible),
			len(all_active) - len(eligible),
		)

		return {"banned": banned, "total": len(all_active)}
	finally:
		_in_flight_guild_syncs.discard(gid)


async def submit_request(input_: dict[str, object]) -> SanctionRequest:
	return await sanction_requests().create(
		cast(
			SanctionRequest,
			{
				**input_,
				"status": "pending",
				"requiredApprovals": _required_approvals,
				"approvals": [],
				"declines": [],
				"declineReason": None,
				"submittedAt": _now_iso(),
				"resolvedAt": None,
			},
		)
	)


async def cast_vote(
	client: discord.Client,
	request_id: str,
	reviewer_id: int | str,
	decision: str,
	decline_reason: str | None = None,
) -> dict[str, object]:
	reviewer_id_str = str(reviewer_id)
	request = await sanction_requests().get(request_id)
	if not request:
		raise VoteError(f"No submission found with id `{request_id}`.")
	if request["status"] != "pending":
		raise VoteError(f"That submission was already **{request['status']}**.")

	approvals = set(request["approvals"])
	declines = set(request["declines"])

	if decision == "approve":
		declines.discard(reviewer_id_str)
		approvals.add(reviewer_id_str)
	else:
		approvals.discard(reviewer_id_str)
		declines.add(reviewer_id_str)

	patch: dict[str, object] = {
		"approvals": list(approvals),
		"declines": list(declines),
	}

	just_resolved = False
	enforcement: EnforcementSummary | None = None

	if len(approvals) >= request["requiredApprovals"]:
		patch["status"] = "approved"
		patch["resolvedAt"] = _now_iso()
		just_resolved = True
	elif len(declines) >= request["requiredApprovals"]:
		patch["status"] = "declined"
		patch["resolvedAt"] = _now_iso()
		patch["declineReason"] = decline_reason or request.get("declineReason") or None
		just_resolved = True

	updated = await sanction_requests().update(request_id, patch)

	if just_resolved and updated["status"] == "approved":
		enforcement = await _apply_approved_request(client, updated)

	if just_resolved:
		logger.info(
			"[nationseal] AUDIT submission=%s resolved=%s reviewers=%d",
			updated["id"],
			updated["status"],
			len(updated["approvals"]) + len(updated["declines"]),
		)

	return {
		"request": updated,
		"justResolved": just_resolved,
		"enforcement": enforcement,
	}


async def _apply_approved_request(
	client: discord.Client, request: SanctionRequest
) -> EnforcementSummary:
	if request["type"] == "ban":
		await sanctions().upsert(
			request["targetId"],
			cast(
				Sanction,
				{
					"id": request["targetId"],
					"reason": request["reason"],
					"requestId": request["id"],
					"addedBy": request["submittedBy"],
					"addedAt": _now_iso(),
				},
			),
		)
		return await ban_across_guilds(
			client, request["targetId"], f"NationSeal sanction: {request['reason']}"
		)

	await sanctions().remove(request["targetId"])
	return await unban_across_guilds(
		client, request["targetId"], "NationSeal sanction appeal approved"
	)


# ── Database lifecycle helpers ──────────────────────────────────────────


async def connect_database() -> None:
	assert _db is not None, "init_runtime() must be called first"
	await _db.connect()


async def close_database() -> None:
	if _db is not None:
		await _db.close()


# ── Config accessors used by the UI layer ───────────────────────────────


def is_owner(user_id: int | str) -> bool:
	return str(user_id) in _owner_ids


def owner_ids() -> list[str]:
	return list(_owner_ids)


def reviewer_channel_id() -> int | None:
	return _reviewer_channel_id
