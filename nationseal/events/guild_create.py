"""Guild create event handler."""

from __future__ import annotations

import logging

import discord

from nationseal.antiraid import maybe_block_for_antiraid
from nationseal.config import config
from nationseal.db import guild_state
from nationseal.dm import build_antiraid_message, build_owner_fallback_message, dm_users
from nationseal.sanctions import enforce_all_sanctions_on_guild

logger = logging.getLogger("nationseal")


async def on_guild_create(client: discord.Client, guild: discord.Guild) -> None:
	antiraid = await maybe_block_for_antiraid(client, guild)

	if antiraid.blocked:
		owner_mention = f"<@{guild.owner_id}>" if guild.owner_id else "owner"
		dm_content = build_antiraid_message(
			guild_name=guild.name,
			guild_id=guild.id,
			owner_mention=owner_mention,
			detected_bots=antiraid.detectedBots,
		)
		recipients = [uid for uid in [guild.owner_id, *config.owner_ids] if uid is not None]
		outcomes = await dm_users(client, recipients, dm_content)
		owner_delivered = next(
			(o.delivered for o in outcomes if o.recipient == str(guild.owner_id)), None
		)

		logger.warning(
			build_owner_fallback_message(
				guild_name=guild.name,
				guild_id=guild.id,
				owner_id=guild.owner_id,
				owner_dm_failed=not owner_delivered if owner_delivered is not None else True,
				detected_bots=antiraid.detectedBots,
			)
		)
		return

	existing = await guild_state.get(str(guild.id))
	if existing and existing.get("antiraidBlocked"):
		logger.info(
			"[nationseal] Skipping auto-enforce in %s (%s) — anti-raid previously detected.",
			guild.id,
			guild.name,
		)
		return

	result = await enforce_all_sanctions_on_guild(client, guild.id)
	logger.info(
		"[nationseal] Joined guild %s (%s). Synced %d/%d active sanctions.",
		guild.id,
		guild.name,
		result["banned"],
		result["total"],
	)
