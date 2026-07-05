"""Core multi-sig voting and cross-guild ban enforcement."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import discord

from nationseal.config import config
from nationseal.db import sanction_requests, sanctions
from nationseal.models import Sanction

if TYPE_CHECKING:
	from discord import Client

	from nationseal.models import SanctionRequest

logger = logging.getLogger("nationseal")


class VoteError(Exception):
	pass


class EnforcementSummary:
	def __init__(self) -> None:
		self.guilds_attempted = 0
		self.guilds_succeeded = 0


def _now_iso() -> str:
	return datetime.now(UTC).isoformat()


async def submit_request(input_: dict[str, object]) -> SanctionRequest:
	return await sanction_requests.create(
		cast(
			SanctionRequest,
			{
				**input_,
				"status": "pending",
				"requiredApprovals": config.required_approvals,
				"approvals": [],
				"declines": [],
				"declineReason": None,
				"submittedAt": _now_iso(),
				"resolvedAt": None,
			},
		)
	)


async def cast_vote(
	client: Client,
	request_id: str,
	reviewer_id: int | str,
	decision: str,
	decline_reason: str | None = None,
) -> dict[str, object]:
	reviewer_id_str = str(reviewer_id)
	request = await sanction_requests.get(request_id)
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

	updated = await sanction_requests.update(request_id, patch)

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


async def _apply_approved_request(client: Client, request: SanctionRequest) -> EnforcementSummary:
	if request["type"] == "ban":
		await sanctions.upsert(
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
		return await ban_across_guilds(client, request["targetId"], f"NationSeal sanction: {request['reason']}")

	await sanctions.remove(request["targetId"])
	return await unban_across_guilds(client, request["targetId"], "NationSeal sanction appeal approved")


def _is_protected_user(user_id: int | str, client: Client) -> bool:
	uid = str(user_id)
	if client.user and uid == str(client.user.id):
		return True
	return uid in config.owner_ids


def _get_cached_guild_ids(client: Client) -> list[int]:
	return [guild.id for guild in client.guilds]


async def _ban_single_user_in_guild(
	client: Client, guild_id: int, user_id: int, reason: str
) -> bool:
	if _is_protected_user(user_id, client):
		logger.warning("[nationseal] Refusing to ban protected user %s in %s.", user_id, guild_id)
		return False

	guild = client.get_guild(guild_id)
	if guild is None:
		return False

	try:
		kwargs: dict[str, object] = {}
		if config.ban_delete_message_seconds > 0:
			kwargs["delete_message_seconds"] = config.ban_delete_message_seconds
		if config.ban_delete_message_seconds > 0:
			await guild.ban(
				discord.Object(id=user_id),
				reason=reason,
				delete_message_seconds=config.ban_delete_message_seconds,
			)
		else:
			await guild.ban(discord.Object(id=user_id), reason=reason)
		return True
	except Exception as exc:  # noqa: BLE001
		logger.warning("[nationseal] Could not ban %s in guild %s: %s", user_id, guild_id, exc)
		return False


async def ban_across_guilds(client: Client, user_id: int | str, reason: str) -> EnforcementSummary:
	uid = int(user_id)
	guild_ids = _get_cached_guild_ids(client)
	summary = EnforcementSummary()

	for guild_id in guild_ids:
		summary.guilds_attempted += 1
		if await _ban_single_user_in_guild(client, guild_id, uid, reason):
			summary.guilds_succeeded += 1

	return summary


async def unban_across_guilds(client: Client, user_id: int | str, reason: str) -> EnforcementSummary:
	uid = int(user_id)
	guild_ids = _get_cached_guild_ids(client)
	summary = EnforcementSummary()

	for guild_id in guild_ids:
		guild = client.get_guild(guild_id)
		if guild is None:
			continue
		summary.guilds_attempted += 1
		try:
			await guild.unban(discord.Object(id=uid), reason=reason)
			summary.guilds_succeeded += 1
		except Exception as exc:  # noqa: BLE001
			logger.warning("[nationseal] Could not unban %s in guild %s: %s", user_id, guild_id, exc)

	return summary


_in_flight_guild_syncs: set[int] = set()


async def enforce_all_sanctions_on_guild(client: Client, guild_id: int | str) -> dict[str, int]:
	gid = int(guild_id)
	if gid in _in_flight_guild_syncs:
		logger.info("[nationseal] Skipping duplicate guild sync for %s; already in progress.", gid)
		return {"banned": 0, "total": 0}

	_in_flight_guild_syncs.add(gid)
	try:
		all_active = await sanctions.list_all()
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
					delete_message_seconds=config.ban_delete_message_seconds or 86400,
				)
				banned += len(result.banned_users)  # type: ignore
			except Exception as exc:  # noqa: BLE001
				logger.warning("[nationseal] Could not bulk-sync sanctions to guild %s: %s", gid, exc)

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
