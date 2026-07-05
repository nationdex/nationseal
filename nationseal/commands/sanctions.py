"""All /sanctions slash commands."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands

from nationseal.components import (
	build_action_row,
	build_layout,
	build_request_container,
	build_request_list_components,
	build_reviewer_list_container,
	build_sanction_container,
	text_only_container,
)
from nationseal.db import reviewers, sanction_requests, sanctions
from nationseal.models import SanctionRequest, SanctionRequestStatus
from nationseal.permissions import is_reviewer, require_owner, require_reviewer
from nationseal.sanctions import (
	VoteError,
	cast_vote,
	enforce_all_sanctions_on_guild,
	submit_request,
)

if TYPE_CHECKING:
	from discord.ext.commands import Bot

logger = logging.getLogger("nationseal")

PER_PAGE = 1
LIST_CUSTOM_ID_PREFIX = "sanction_list"


def _respond(
	interaction: discord.Interaction, *items: object, ephemeral: bool = True
) -> Awaitable[object]:
	view = build_layout(*items)
	if interaction.response.is_done():
		return interaction.edit_original_response(view=view)
	return interaction.response.send_message(view=view, ephemeral=ephemeral)


async def _id_autocomplete(
	interaction: discord.Interaction, current: str, *, statuses: list[SanctionRequestStatus]
) -> list[app_commands.Choice[str]]:
	current_lower = current.lower()
	all_requests: list[SanctionRequest] = []
	for status in statuses:
		all_requests.extend(await sanction_requests.list_by_status(status, 25))

	choices: list[app_commands.Choice[str]] = []
	for req in all_requests:
		target = req["targetTag"] or req["targetId"]
		if (
			current_lower in str(req.get("id", "")).lower()
			or current_lower in str(target).lower()
			or current_lower in str(req.get("reason", "")).lower()
		):
			name = f"[{req.get('status')}] {'Ban' if req.get('type') == 'ban' else 'Unban'} {target} — {str(req.get('reason', ''))[:40]}"
			choices.append(app_commands.Choice(name=name[:100], value=str(req["id"])))
		if len(choices) >= 25:
			break
	return choices


async def _approve_autocomplete(
	interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
	return await _id_autocomplete(interaction, current, statuses=["pending"])


async def _decline_autocomplete(
	interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
	return await _id_autocomplete(interaction, current, statuses=["pending"])


async def _info_autocomplete(
	interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
	return await _id_autocomplete(interaction, current, statuses=["pending", "approved", "declined"])


class SanctionsCog(commands.Cog):
	def __init__(self, bot: Bot) -> None:
		self.bot = bot

	sanctions = app_commands.Group(
		name="sanctions",
		description="Manage the NationSeal shared sanction list",
		guild_only=True,
		default_permissions=discord.Permissions(ban_members=True),
	)

	@sanctions.command(
		name="submit",
		description="Submit a user for a network-wide ban. Requires reviewer approval before it takes effect.",
	)
	@app_commands.describe(
		user="The user to submit for a network-wide ban",
		reason="Why should this user be sanctioned? (e.g. raider, scammer)",
		evidence="Link to evidence (message link, screenshot URL, etc.)",
	)
	async def submit(
		self,
		interaction: discord.Interaction,
		user: discord.User,
		reason: str,
		evidence: str | None = None,
	) -> None:
		await interaction.response.defer(ephemeral=True)

		if user.bot:
			await _respond(interaction, text_only_container("Bots can't be added to the sanction list."))
			return
		if user.id == interaction.user.id:
			await _respond(
				interaction, text_only_container("You can't submit yourself for a network ban.")
			)
			return
		if await is_reviewer(user.id):
			await _respond(
				interaction,
				text_only_container(
					"Trusted NationSeal reviewers (and owners) can't be submitted for a network ban. "
					"Ask an owner to remove them from the reviewer roster first."
				),
			)
			return

		try:
			request = await submit_request(
				{
					"type": "ban",
					"targetId": str(user.id),
					"targetTag": f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name,
					"reason": reason,
					"evidence": evidence,
					"submittedBy": str(interaction.user.id),
					"submittedByTag": f"{interaction.user.name}#{interaction.user.discriminator}"
					if interaction.user.discriminator != "0"
					else interaction.user.name,
					"guildId": str(interaction.guild_id) if interaction.guild_id else "unknown",
				}
			)
			await _respond(
				interaction,
				text_only_container(
					"Submission received. A reviewer will need to approve it before the ban is enforced."
				),
				build_request_container(request),
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] submit command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while submitting the sanction. Please try again later."
				),
			)

	@sanctions.command(
		name="appeal",
		description="Request that an existing network-wide ban be lifted. Requires reviewer approval.",
	)
	@app_commands.describe(
		user="The sanctioned user this appeal is for",
		reason="Why should this sanction be lifted?",
	)
	async def appeal(
		self, interaction: discord.Interaction, user: discord.User, reason: str
	) -> None:
		await interaction.response.defer(ephemeral=True)

		existing = await sanctions.get(str(user.id))
		if not existing:
			await _respond(
				interaction,
				text_only_container(f"<@{user.id}> is not currently on the shared sanction list."),
			)
			return

		try:
			request = await submit_request(
				{
					"type": "unban",
					"targetId": str(user.id),
					"targetTag": f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name,
					"reason": reason,
					"evidence": None,
					"submittedBy": str(interaction.user.id),
					"submittedByTag": f"{interaction.user.name}#{interaction.user.discriminator}"
					if interaction.user.discriminator != "0"
					else interaction.user.name,
					"guildId": str(interaction.guild_id) if interaction.guild_id else "unknown",
				}
			)
			await _respond(
				interaction,
				text_only_container(
					"Appeal submitted. A reviewer will need to approve it before the ban is lifted."
				),
				build_request_container(request),
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] appeal command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while submitting the appeal. Please try again later."
				),
			)

	@sanctions.command(
		name="approve", description="Cast a reviewer approval vote on a pending submission"
	)
	@app_commands.describe(id="The submission ID to approve")
	@app_commands.autocomplete(id=_approve_autocomplete)
	async def approve(self, interaction: discord.Interaction, id: str) -> None:  # noqa: A002
		await interaction.response.defer(ephemeral=True)

		if not await require_reviewer(interaction):
			return

		try:
			result = await cast_vote(self.bot, id.strip(), interaction.user.id, "approve")
			request = result["request"]
			request = cast(SanctionRequest, result["request"])
			lines = [f"Vote recorded on `{request['id']}`."]
			if result.get("justResolved"):
				enforcement = result.get("enforcement")
				succeeded = getattr(enforcement, "guilds_succeeded", 0) if enforcement else 0
				attempted = getattr(enforcement, "guilds_attempted", 0) if enforcement else 0
				lines.append(
					f"✅ Threshold reached — {request['type']} enforced on {succeeded}/{attempted} servers."
				)
			await _respond(
				interaction,
				text_only_container("\n".join(lines)),
				build_request_container(request),  # type: ignore[arg-type]
			)
		except VoteError as exc:
			await _respond(interaction, text_only_container(str(exc)))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] approve command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while recording your vote. Please try again later."
				),
			)

	@sanctions.command(
		name="decline", description="Cast a reviewer decline vote on a pending submission"
	)
	@app_commands.describe(id="The submission ID to decline", reason="Why is this submission being declined?")
	@app_commands.autocomplete(id=_decline_autocomplete)
	async def decline(
		self, interaction: discord.Interaction, id: str, reason: str | None = None  # noqa: A002
	) -> None:
		await interaction.response.defer(ephemeral=True)

		if not await require_reviewer(interaction):
			return

		try:
			result = await cast_vote(self.bot, id.strip(), interaction.user.id, "decline", reason)
			request = result["request"]
			request = cast(SanctionRequest, result["request"])
			lines = [f"Vote recorded on `{request['id']}`."]
			if result.get("justResolved"):
				lines.append("❌ Threshold reached — submission declined.")
			await _respond(
				interaction,
				text_only_container("\n".join(lines)),
				build_request_container(request),  # type: ignore[arg-type]
			)
		except VoteError as exc:
			await _respond(interaction, text_only_container(str(exc)))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] decline command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while recording your vote. Please try again later."
				),
			)

	@sanctions.command(name="check", description="Check whether a user is on the shared sanction list")
	@app_commands.describe(user="The user to look up")
	async def check(self, interaction: discord.Interaction, user: discord.User) -> None:
		await interaction.response.defer(ephemeral=True)
		try:
			sanction = await sanctions.get(str(user.id))
			await _respond(interaction, build_sanction_container(sanction, str(user.id)))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] check command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while checking the sanction list. Please try again later."
				),
			)

	@sanctions.command(
		name="info", description="View the full details and vote tally of a submission"
	)
	@app_commands.describe(id="The submission ID to look up")
	@app_commands.autocomplete(id=_info_autocomplete)
	async def info(self, interaction: discord.Interaction, id: str) -> None:  # noqa: A002
		await interaction.response.defer(ephemeral=True)
		try:
			request = await sanction_requests.get(id.strip())
			if not request:
				await _respond(
					interaction, text_only_container(f"No submission found with id `{id}`.")
				)
				return
			await _respond(interaction, build_request_container(request))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] info command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while fetching that submission. Please try again later."
				),
			)

	@sanctions.command(
		name="list", description="List pending submissions waiting for approval (reviewers only)"
	)
	async def list_(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True)

		if not await require_reviewer(interaction):
			return

		try:
			status = "pending"
			all_requests = await sanction_requests.list_by_status(status, 200)
			main, approve, decline, back, next_, footer = build_request_list_components(
				all_requests,
				page=1,
				per_page=PER_PAGE,
				total=len(all_requests),
				status=status,
				custom_id_prefix=LIST_CUSTOM_ID_PREFIX,
			)
			await _respond(
				interaction,
				main,
				build_action_row(approve, decline),
				build_action_row(back, next_),
				footer,
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] list command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while listing submissions. Please try again later."
				),
			)

	@sanctions.command(
		name="enforce",
		description="Re-ban all sanctioned users across all servers (useful if automatic enforcement failed)",
	)
	async def enforce(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True)

		if not await require_reviewer(interaction):
			return

		try:
			active = await sanctions.list_all()
			if not active:
				await _respond(interaction, text_only_container("No active sanctions to enforce."))
				return

			total_banned = 0
			total_attempted = 0
			results: list[str] = []
			from nationseal.sanctions import ban_across_guilds

			for sanction in active:
				result = await ban_across_guilds(
					self.bot, sanction["id"], f"NationSeal enforcement: {sanction['reason']}"
				)
				total_banned += result.guilds_succeeded
				total_attempted += result.guilds_attempted
				results.append(
					f"• <@{sanction['id']}> — banned in {result.guilds_succeeded}/{result.guilds_attempted} servers"
				)

			summary = [
				"## Enforcement complete",
				f"**Total:** {len(active)} user(s) across {total_banned}/{total_attempted} server(s)",
				"",
				*results,
			]
			await _respond(interaction, text_only_container("\n".join(summary)))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] enforce command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while enforcing sanctions. Please try again later."
				),
			)

	@sanctions.command(
		name="local-enforce",
		description="Manually push the shared sanction list into a server (bypasses anti-raid auto-block; owners only)",
	)
	@app_commands.describe(guild="The server ID to manually enforce the sanction list in")
	async def local_enforce(self, interaction: discord.Interaction, guild: str) -> None:
		await interaction.response.defer(ephemeral=True)

		if not await require_owner(interaction):
			return

		guild_id = guild.strip()
		if not guild_id.isdigit() or not (17 <= len(guild_id) <= 20):
			await _respond(
				interaction,
				text_only_container(
					"That doesn't look like a valid Discord server ID (must be 17-20 digits)."
				),
			)
			return

		try:
			g = self.bot.get_guild(int(guild_id))
			if g is None:
				await _respond(
					interaction,
					text_only_container(
						f"I'm not in any server with ID `{guild_id}`. The bot must be invited first."
					),
				)
				return

			total = len(await sanctions.list_all())
			if total == 0:
				await _respond(
					interaction,
					text_only_container("The shared sanction list is empty — nothing to enforce."),
				)
				return

			result = await enforce_all_sanctions_on_guild(self.bot, guild_id)
			from nationseal.db import guild_state

			await guild_state.mark_enforced(guild_id)
			logger.info(
				"[nationseal] AUDIT localEnforce guild=%s by=%s banned=%d/%d",
				guild_id,
				interaction.user.id,
				result["banned"],
				total,
			)
			await _respond(
				interaction,
				text_only_container(
					"\n".join(
						[
							f"Manual enforcement complete in **{g.name}** (`{guild_id}`).",
							f"Banned **{result['banned']}** of **{total}** active sanctions.",
							"This guild is now marked as `manually_enforced` in the database.",
						]
					)
				),
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] local-enforce command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while enforcing sanctions in that server. Check the bot logs for the Discord error."
				),
			)

	@sanctions.command(
		name="reviewer-add", description="Add a trusted reviewer to the multi-sig roster (owners only)"
	)
	@app_commands.describe(user="The user to add as a trusted reviewer")
	async def reviewer_add(self, interaction: discord.Interaction, user: discord.User) -> None:
		await interaction.response.defer(ephemeral=True)

		if not await require_owner(interaction):
			return

		try:
			await reviewers.add(str(user.id), str(interaction.user.id))
			logger.info(
				"[nationseal] AUDIT reviewerAdd reviewer=%s by=%s", user.id, interaction.user.id
			)
			await _respond(interaction, text_only_container(f"<@{user.id}> is now a trusted reviewer."))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] reviewer-add command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while adding the reviewer. Please try again later."
				),
			)

	@sanctions.command(
		name="reviewer-remove",
		description="Remove a trusted reviewer from the multi-sig roster (owners only)",
	)
	@app_commands.describe(user="The reviewer to remove from the roster")
	async def reviewer_remove(self, interaction: discord.Interaction, user: discord.User) -> None:
		await interaction.response.defer(ephemeral=True)

		if not await require_owner(interaction):
			return

		try:
			await reviewers.remove(str(user.id))
			logger.info(
				"[nationseal] AUDIT reviewerRemove reviewer=%s by=%s", user.id, interaction.user.id
			)
			await _respond(
				interaction, text_only_container(f"<@{user.id}> is no longer a trusted reviewer.")
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] reviewer-remove command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while removing the reviewer. Please try again later."
				),
			)

	@sanctions.command(name="reviewer-list", description="List the current trusted reviewers")
	async def reviewer_list(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True)
		try:
			await _respond(interaction, build_reviewer_list_container(await reviewers.list_all()))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] reviewer-list command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while fetching the reviewer roster. Please try again later."
				),
			)


async def setup(bot: Bot) -> None:
	await bot.add_cog(SanctionsCog(bot))
