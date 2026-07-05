"""In-memory JSON file database. Keeps the whole dataset in memory and flushes on mutation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from nationseal.models import (
		DatabaseSchema,
		GuildState,
		Reviewer,
		Sanction,
		SanctionRequest,
		SanctionRequestStatus,
	)

DEFAULT_SCHEMA: DatabaseSchema = {
	"sanctionRequests": [],
	"sanctions": [],
	"reviewers": [],
	"guildStates": [],
}


class JsonDatabase:
	def __init__(self, file_path: str) -> None:
		self.file_path = Path(file_path)
		self.data: DatabaseSchema = {**DEFAULT_SCHEMA}
		self.loaded = False
		self.modified = False
		self._flush_promise: object | None = None

	async def connect(self) -> None:
		if self.loaded:
			return
		if self.file_path.exists():
			raw = self.file_path.read_text(encoding="utf-8")
			parsed = json.loads(raw)
			self.data = {**DEFAULT_SCHEMA, **parsed}
			self.modified = False
		else:
			self.data = {**DEFAULT_SCHEMA}
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
		record: Reviewer = {
			"id": user_id,
			"addedBy": added_by,
			"addedAt": _now_iso(),
		}
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

	def import_data(self, data: DatabaseSchema) -> None:
		self.data = {**DEFAULT_SCHEMA, **data}
		self.modified = True


def _now_iso() -> str:
	from datetime import datetime

	return datetime.now(UTC).isoformat()
