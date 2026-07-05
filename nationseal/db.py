"""Database access layer. Exports the JSON-backed collections."""

from __future__ import annotations

from nationseal.config import config
from nationseal.jsondb import JsonDatabase
from nationseal.models import (
	DatabaseSchema,
	GuildState,
	Reviewer,
	Sanction,
	SanctionRequest,
	SanctionRequestStatus,
)

db = JsonDatabase(config.database_path)


async def connect_database() -> None:
	await db.connect()


async def close_database() -> None:
	await db.close()


class _SanctionRequests:
	@staticmethod
	async def create(data: SanctionRequest) -> SanctionRequest:
		return await db.create_sanction_request(data)

	@staticmethod
	async def get(request_id: str) -> SanctionRequest | None:
		return await db.get_sanction_request(request_id)

	@staticmethod
	async def update(request_id: str, patch: dict[str, object]) -> SanctionRequest:
		return await db.update_sanction_request(request_id, patch)

	@staticmethod
	async def list_by_status(status: SanctionRequestStatus, limit: int = 10) -> list[SanctionRequest]:
		return await db.list_sanction_requests_by_status(status, limit)


class _Sanctions:
	@staticmethod
	async def get(target_id: str) -> Sanction | None:
		return await db.get_sanction(target_id)

	@staticmethod
	async def upsert(target_id: str, data: Sanction) -> Sanction:
		return await db.upsert_sanction(target_id, data)

	@staticmethod
	async def remove(target_id: str) -> None:
		return await db.remove_sanction(target_id)

	@staticmethod
	async def list_all() -> list[Sanction]:
		return await db.list_all_sanctions()


class _Reviewers:
	@staticmethod
	async def is_reviewer(user_id: str) -> bool:
		return await db.is_reviewer(user_id)

	@staticmethod
	async def add(user_id: str, added_by: str) -> Reviewer:
		return await db.add_reviewer(user_id, added_by)

	@staticmethod
	async def remove(user_id: str) -> None:
		return await db.remove_reviewer(user_id)

	@staticmethod
	async def list_all() -> list[Reviewer]:
		return await db.list_reviewers()


class _GuildState:
	@staticmethod
	async def get(guild_id: str) -> GuildState | None:
		return await db.get_guild_state(guild_id)

	@staticmethod
	async def set(guild_id: str, patch: dict[str, object]) -> GuildState:
		return await db.set_guild_state(guild_id, patch)

	@staticmethod
	async def mark_enforced(guild_id: str) -> None:
		return await db.mark_guild_enforced(guild_id)


sanction_requests = _SanctionRequests()
sanctions = _Sanctions()
reviewers = _Reviewers()
guild_state = _GuildState()

__all__ = [
	"connect_database",
	"close_database",
	"sanction_requests",
	"sanctions",
	"reviewers",
	"guild_state",
	"db",
	"DatabaseSchema",
]
