"""Owner / reviewer permission helpers."""

from __future__ import annotations

import discord

from nationseal.config import config
from nationseal.db import reviewers


def is_owner(user_id: int | str) -> bool:
	return str(user_id) in config.owner_ids


async def is_reviewer(user_id: int | str) -> bool:
	uid = str(user_id)
	return is_owner(uid) or await reviewers.is_reviewer(uid)


async def has_administrator(member: discord.Member | None) -> bool:
	if member is None:
		return False
	return member.guild_permissions.administrator


async def require_reviewer(interaction: discord.Interaction) -> bool:
	if await is_reviewer(interaction.user.id):
		return True
	await _reply_text(interaction, "Only trusted NationSeal reviewers can use this command.")
	return False


async def require_owner(interaction: discord.Interaction) -> bool:
	if is_owner(interaction.user.id):
		return True
	await _reply_text(interaction, "Only NationSeal owners can use this command.")
	return False


async def _reply_text(interaction: discord.Interaction, text: str) -> None:
	from nationseal.components import build_layout, text_only_container

	view = build_layout(text_only_container(text))
	if interaction.response.is_done():
		await interaction.edit_original_response(view=view)
	else:
		await interaction.response.send_message(view=view, ephemeral=True)
