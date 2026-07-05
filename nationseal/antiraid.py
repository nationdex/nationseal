"""Anti-raid bot detection using REST member fetch."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import TYPE_CHECKING

import discord

from nationseal.config import config
from nationseal.db import guild_state

if TYPE_CHECKING:
	from discord import Client

logger = logging.getLogger("nationseal")


async def detect_antiraid_bots(client: Client, guild_id: int | str) -> list[str]:
	if not config.antiraid_bot_ids:
		return []
	gid = int(guild_id)
	present: list[str] = []

	for bot_id in config.antiraid_bot_ids:
		try:
			guild = client.get_guild(gid)
			if guild is None:
				present.append(bot_id)
				continue
			await guild.fetch_member(int(bot_id))
			present.append(bot_id)
		except discord.NotFound:
			continue
		except Exception as exc:  # noqa: BLE001
			logger.warning("[nationseal] Could not check antiraid bot %s in %s: %s", bot_id, gid, exc)
			present.append(bot_id)

	return present


class AntiraidBlockResult:
	def __init__(self, blocked: bool, detected_bots: list[str]) -> None:
		self.blocked = blocked
		self.detectedBots = detected_bots


async def maybe_block_for_antiraid(
	client: Client,
	guild: discord.Guild,
) -> AntiraidBlockResult:
	gid = int(guild.id)
	gname = getattr(guild, "name", str(gid))
	detected = await detect_antiraid_bots(client, gid)

	if not detected:
		existing = await guild_state.get(str(gid))
		if existing and existing.get("antiraidBlocked"):
			await guild_state.set(
				str(gid),
				{
					"antiraidBlocked": False,
					"antiraidBots": [],
					"enforcementStatus": "auto_enforced",
				},
			)
		return AntiraidBlockResult(False, [])

	existing = await guild_state.get(str(gid))
	now = _now_iso()
	await guild_state.set(
		str(gid),
		{
			"antiraidBlocked": True,
			"antiraidBots": detected,
			"enforcementStatus": "antiraid_blocked",
			"antiraidNotifiedAt": existing.get("antiraidNotifiedAt") if existing else now,
		},
	)

	logger.warning(
		"[nationseal] Auto-ban SKIPPED in %s (%s); antiraid bot(s) detected: %s. Owner has been DM'd.",
		gid,
		gname,
		", ".join(detected),
	)
	return AntiraidBlockResult(True, detected)


def _now_iso() -> str:
	from datetime import datetime

	return datetime.now(UTC).isoformat()
