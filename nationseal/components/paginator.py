"""Button interaction handler for /sanctions list pagination and voting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from nationseal.commands.sanctions import LIST_CUSTOM_ID_PREFIX, PER_PAGE
from nationseal.components import (
	build_action_row,
	build_layout,
	build_request_list_components,
	text_only_container,
)
from nationseal.db import sanction_requests
from nationseal.permissions import is_reviewer
from nationseal.sanctions import VoteError, cast_vote

if TYPE_CHECKING:
	from discord.ext.commands import Bot

logger = logging.getLogger("nationseal")


class _ParsedCustomId:
	def __init__(self, kind: str, page: int, action: str | None = None) -> None:
		self.kind = kind
		self.page = page
		self.action = action


def _parse_custom_id(custom_id: str) -> _ParsedCustomId:
	parts = custom_id.split("|")
	if len(parts) < 2 or parts[0] != LIST_CUSTOM_ID_PREFIX:
		return _ParsedCustomId("invalid", 0)
	try:
		page = int(parts[1])
	except ValueError:
		return _ParsedCustomId("invalid", 0)
	if page < 1:
		return _ParsedCustomId("invalid", 0)
	if len(parts) == 3 and parts[2] in ("approve", "decline"):
		return _ParsedCustomId("vote", page, parts[2])
	if len(parts) == 2:
		return _ParsedCustomId("navigate", page)
	return _ParsedCustomId("invalid", 0)


class ComponentsCog(commands.Cog):
	def __init__(self, bot: Bot) -> None:
		self.bot = bot

	@commands.Cog.listener()
	async def on_interaction(self, interaction: discord.Interaction) -> None:
		if interaction.type != discord.InteractionType.component:
			return
		if interaction.data is None:
			return
		custom_id = interaction.data.get("custom_id", "")
		parsed = _parse_custom_id(custom_id)
		if parsed.kind == "invalid":
			return

		if not await is_reviewer(interaction.user.id):
			await interaction.response.send_message(
				view=build_layout(
					text_only_container("Only trusted NationSeal reviewers can interact with this list.")
				),
				ephemeral=True,
			)
			return

		if parsed.kind == "vote":
			await self._handle_vote(interaction, parsed.page, parsed.action)
		else:
			await self._handle_navigation(interaction, parsed.page)

	async def _handle_navigation(self, interaction: discord.Interaction, page: int) -> None:
		try:
			view = await _build_list_view(page)
			await interaction.response.edit_message(view=view)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] sanction list paginate failed: %s", exc)

	async def _handle_vote(
		self, interaction: discord.Interaction, page: int, action: str | None
	) -> None:
		try:
			all_requests = await sanction_requests.list_by_status("pending", 200)
			index = (page - 1) * PER_PAGE
			request = all_requests[index] if index < len(all_requests) else None

			if request is None:
				await interaction.response.edit_message(
					view=build_layout(text_only_container("No submission found at this position."))
				)
				return

			result = await cast_vote(self.bot, request["id"], interaction.user.id, action)  # type: ignore

			lines = [f"Vote recorded on `{request['id']}` ({action})."]
			if result.get("justResolved"):
				enforcement = result.get("enforcement")
				succeeded = getattr(enforcement, "guilds_succeeded", 0) if enforcement else 0
				attempted = getattr(enforcement, "guilds_attempted", 0) if enforcement else 0
				lines.append(
					f"✅ Threshold reached — {request['type']} enforced on {succeeded}/{attempted} servers."
				)

			list_view = await _build_list_view(page)
			# Rebuild view with the summary container prepended.
			summary = text_only_container("\n".join(lines))
			items = [summary, *list_view.children]
			await interaction.response.edit_message(view=build_layout(*items))
		except VoteError as exc:
			await interaction.response.edit_message(
				view=build_layout(text_only_container(str(exc)))
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] sanction list vote failed: %s", exc)
			await interaction.response.edit_message(
				view=build_layout(text_only_container("An error occurred while voting."))
			)


async def _build_list_view(page: int) -> discord.ui.LayoutView:
	status = "pending"
	all_requests = await sanction_requests.list_by_status(status, 200)
	main, approve, decline, back, next_, footer = build_request_list_components(
		all_requests,
		page=page,
		per_page=PER_PAGE,
		total=len(all_requests),
		status=status,
		custom_id_prefix=LIST_CUSTOM_ID_PREFIX,
	)
	return build_layout(
		main,
		build_action_row(approve, decline),
		build_action_row(back, next_),
		footer,
	)


async def setup(bot: Bot) -> None:
	await bot.add_cog(ComponentsCog(bot))
