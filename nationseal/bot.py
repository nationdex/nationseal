"""Bot client setup and event handlers."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from nationseal.commands.sanctions import SanctionsCog
from nationseal.components.paginator import ComponentsCog
from nationseal.config import config
from nationseal.db import close_database, connect_database
from nationseal.events.guild_create import on_guild_create

logger = logging.getLogger("nationseal")


class NationSealBot(commands.Bot):
	def __init__(self) -> None:
		super().__init__(
			command_prefix=commands.when_mentioned,
			intents=discord.Intents(guilds=True),
			allowed_mentions=discord.AllowedMentions.none(),
		)
		self.tree.on_error = self._on_tree_error  # type: ignore

	async def setup_hook(self) -> None:
		await connect_database()
		await self.add_cog(SanctionsCog(self))
		await self.add_cog(ComponentsCog(self))
		# Sync commands globally.
		await self.tree.sync()

	async def on_ready(self) -> None:
		user = self.user
		if user is None:
			return
		logger.info("[nationseal] %s is online, watching %d server(s).", user.name, len(self.guilds))

	async def on_guild_join(self, guild: discord.Guild) -> None:
		await on_guild_create(self, guild)

	async def close(self) -> None:
		await super().close()
		await close_database()

	async def _on_tree_error(
		self, interaction: discord.Interaction, error: app_commands.AppCommandError
	) -> None:
		logger.error("[nationseal] Command error: %s", error)
		try:
			from nationseal.components import build_layout, text_only_container

			view = build_layout(text_only_container("An unexpected error occurred. Please try again later."))
			if interaction.response.is_done():
				await interaction.edit_original_response(view=view)
			else:
				await interaction.response.send_message(view=view, ephemeral=True)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] Failed to send error response: %s", exc)


def run_bot() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	)

	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	bot = NationSealBot()

	try:
		loop.run_until_complete(bot.start(config.bot_token))
	except KeyboardInterrupt:
		logger.info("[nationseal] KeyboardInterrupt received, shutting down...")
	finally:
		loop.run_until_complete(bot.close())
		loop.close()


__all__ = ["NationSealBot", "run_bot"]
