"""Bot client, configuration, and entry point."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from discord import Intents, app_commands
from discord.ext import commands
from dotenv import load_dotenv

import nationseal.data as data
from nationseal.ui import ComponentsCog, SanctionsCog, build_layout, text_only_container

# Load .env from the project root (one level above this file).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _parse_ids(value: str | None) -> list[str]:
	if not value:
		return []
	return [item.strip() for item in value.split(",") if item.strip()]


def _parse_number(value: str | None, fallback: int) -> int:
	if not value:
		return fallback
	try:
		parsed = int(value)
	except ValueError:
		return fallback
	return parsed if parsed > 0 else fallback


class Config:
	def __init__(self) -> None:
		self.bot_token: str = os.getenv("BOT_TOKEN", "")
		self.owner_ids: list[str] = _parse_ids(os.getenv("OWNER_IDS"))
		self.required_approvals: int = max(1, _parse_number(os.getenv("REQUIRED_APPROVALS"), 2))
		self.ban_delete_message_seconds: int = min(
			604_800, max(0, _parse_number(os.getenv("BAN_DELETE_MESSAGE_SECONDS"), 0))
		)
		self.database_path: str = os.getenv("DATABASE_PATH", "./.data/data.json")
		self.antiraid_bot_ids: list[str] = _parse_ids(os.getenv("ANTIRAID_BOT_IDS"))

		if not self.bot_token:
			raise RuntimeError("[nationseal] BOT_TOKEN is not set in environment variables.")
		if not self.owner_ids:
			raise RuntimeError(
				"[nationseal] OWNER_IDS is empty. At least one owner is required to manage reviewers."
			)


config = Config()


logger = logging.getLogger("nationseal")


class NationSealBot(commands.Bot):
	def __init__(self) -> None:
		super().__init__(
			command_prefix=commands.when_mentioned,
			intents=Intents(guilds=True),
			allowed_mentions=None,
		)
		self.tree.on_error = self._on_tree_error  # type: ignore

	async def setup_hook(self) -> None:
		data.init_runtime(
			database_path=config.database_path,
			required_approvals=config.required_approvals,
			ban_delete_message_seconds=config.ban_delete_message_seconds,
			owner_ids=config.owner_ids,
			antiraid_bot_ids=config.antiraid_bot_ids,
		)
		await data.connect_database()
		await self.add_cog(SanctionsCog(self))
		await self.add_cog(ComponentsCog(self))
		await self.tree.sync()

	async def on_ready(self) -> None:
		user = self.user
		if user is None:
			return
		logger.info(
			"[nationseal] %s is online, watching %d server(s).", user.name, len(self.guilds)
		)

	async def on_guild_join(self, guild) -> None:
		antiraid = await data.maybe_block_for_antiraid(self, guild)

		if antiraid.blocked:
			owner_mention = f"<@{guild.owner_id}>" if guild.owner_id else "owner"
			dm_content = data.build_antiraid_message(
				guild_name=guild.name,
				guild_id=guild.id,
				owner_mention=owner_mention,
				detected_bots=antiraid.detectedBots,
			)
			recipients = [uid for uid in [guild.owner_id, *config.owner_ids] if uid is not None]
			outcomes = await data.dm_users(self, recipients, dm_content)
			owner_delivered = next(
				(o.delivered for o in outcomes if o.recipient == str(guild.owner_id)), None
			)

			logger.warning(
				data.build_owner_fallback_message(
					guild_name=guild.name,
					guild_id=guild.id,
					owner_id=guild.owner_id,
					owner_dm_failed=not owner_delivered if owner_delivered is not None else True,
					detected_bots=antiraid.detectedBots,
				)
			)
			return

		existing = await data.guild_states().get(str(guild.id))
		if existing and existing.get("antiraidBlocked"):
			logger.info(
				"[nationseal] Skipping auto-enforce in %s (%s) — anti-raid previously detected.",
				guild.id,
				guild.name,
			)
			return

		result = await data.enforce_all_sanctions_on_guild(self, guild.id)
		logger.info(
			"[nationseal] Joined guild %s (%s). Synced %d/%d active sanctions.",
			guild.id,
			guild.name,
			result["banned"],
			result["total"],
		)

	async def close(self) -> None:
		await super().close()
		await data.close_database()

	async def _on_tree_error(self, interaction, error: app_commands.AppCommandError) -> None:
		logger.error("[nationseal] Command error: %s", error)
		try:
			view = build_layout(
				text_only_container("An unexpected error occurred. Please try again later.")
			)
			if interaction.response.is_done():
				await interaction.edit_original_response(view=view)
			else:
				await interaction.response.send_message(view=view, ephemeral=True)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] Failed to send error response: %s", exc)


def main() -> None:
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


if __name__ == "__main__":
	main()
