"""DM helpers and message builders for anti-raid notifications."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from nationseal.config import config

if TYPE_CHECKING:
	from discord import Client

logger = logging.getLogger("nationseal")


class DmOutcome:
	def __init__(self, recipient: str, delivered: bool, reason: str | None = None) -> None:
		self.recipient = recipient
		self.delivered = delivered
		self.reason = reason


async def _open_dm(client: Client, user_id: int) -> discord.DMChannel | None:
	try:
		user = await client.fetch_user(user_id)
		return await user.create_dm()
	except Exception:  # noqa: BLE001
		return None


async def _send_dm(client: Client, user_id: int, content: str) -> DmOutcome:
	channel = await _open_dm(client, user_id)
	if channel is None:
		return DmOutcome(
			recipient=str(user_id),
			delivered=False,
			reason="Could not open DM channel (DMs closed or user not reachable).",
		)
	try:
		await channel.send(content)
		return DmOutcome(recipient=str(user_id), delivered=True)
	except Exception as exc:  # noqa: BLE001
		return DmOutcome(
			recipient=str(user_id),
			delivered=False,
			reason=str(exc),
		)


async def dm_users(client: Client, user_ids: list[int | str], content: str) -> list[DmOutcome]:
	unique = list(dict.fromkeys(str(uid) for uid in user_ids if uid))
	results: list[DmOutcome] = []
	for uid in unique:
		results.append(await _send_dm(client, int(uid), content))
	return results


def build_antiraid_message(
	*, guild_name: str, guild_id: int | str, owner_mention: str, detected_bots: list[str]
) -> str:
	bot_list = ", ".join(f"`{bot_id}`" for bot_id in detected_bots)
	return (
		f"Hi {owner_mention} — NationSeal was just added to **{guild_name}** (`{guild_id}`).\n\n"
		f"I detected the following anti-raid / anti-nuke bot(s) in the server: {bot_list}.\n\n"
		"To avoid a flag-spam war, NationSeal will **not** auto-ban the shared sanction list on this server. "
		"To enable enforcement, please add NationSeal to the anti-raid bot's whitelist (most use a `/whitelist add` or similar command) "
		"and then ask a NationSeal owner to run `/sanctions local-enforce`.\n\n"
		"If you don't want NationSeal on this server, you can simply kick it — no data has been written yet."
	)


def build_owner_fallback_message(
	*,
	guild_name: str,
	guild_id: int | str,
	owner_id: int | str | None,
	owner_dm_failed: bool,
	detected_bots: list[str],
) -> str:
	bot_list = ", ".join(f"`{bot_id}`" for bot_id in detected_bots)
	owner_line = f"Guild owner: <@{owner_id}>." if owner_id else "Guild owner ID unknown."
	dm_line = (
		"Could not DM the guild owner (DMs closed). A NationSeal owner needs to follow up."
		if owner_dm_failed
		else "Guild owner has been DM'd with whitelisting instructions."
	)
	owners = ", ".join(f"`{oid}`" for oid in config.owner_ids) or "(none configured)"
	return (
		f"[nationseal] Auto-ban blocked in **{guild_name}** (`{guild_id}`).\n"
		f"Anti-raid bot(s) detected: {bot_list}.\n"
		f"{owner_line}\n"
		f"{dm_line}\n"
		f"Run `/sanctions local-enforce guild:{guild_id}` once NationSeal is whitelisted.\n"
		f"Owners notified: {owners}."
	)
