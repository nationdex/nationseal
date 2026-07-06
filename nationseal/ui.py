"""User interface layer: permissions, Components v2 builders, paginator, and all /sanctions commands."""

from __future__ import annotations

import logging
import math
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import discord
import discord.ui as ui
from discord import ButtonStyle, app_commands
from discord.ext import commands
from discord.ui import ActionRow, Button

import nationseal.data as data
from nationseal.data import (
	Reviewer,
	Sanction,
	SanctionRequest,
	SanctionRequestStatus,
)

if TYPE_CHECKING:
	from discord.ext.commands import Bot

logger = logging.getLogger("nationseal")

# ── Permissions ──────────────────────────────────────────────────────────


async def is_reviewer(user_id: int | str) -> bool:
	uid = str(user_id)
	# Owners are always treated as reviewers.
	if data.is_owner(uid):
		return True
	return await data.reviewers().is_reviewer(uid)


async def require_reviewer(interaction: discord.Interaction) -> bool:
	if await is_reviewer(interaction.user.id):
		return True
	await _reply_text(interaction, "Only trusted NationSeal reviewers can use this command.")
	return False


async def require_owner(interaction: discord.Interaction) -> bool:
	if data.is_owner(interaction.user.id):
		return True
	await _reply_text(interaction, "Only NationSeal owners can use this command.")
	return False


# ── Components v2 builders ──────────────────────────────────────────────

STATUS_COLOR: dict[str, int] = {
	"pending": 0xF1C40F,
	"approved": 0x2ECC71,
	"declined": 0xE74C3C,
}

STATUS_LABEL: dict[str, str] = {
	"pending": "Pending review",
	"approved": "Approved",
	"declined": "Declined",
}


def _escape_markdown(text: str) -> str:
	return "".join(f"\\{ch}" if ch in "\\*_`~|>" else ch for ch in text)


def _discord_timestamp(iso_string: str, *, fmt: str = "R") -> str:
	try:
		dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
		if dt.tzinfo is None:
			dt = dt.replace(tzinfo=UTC)
		return f"<t:{int(dt.timestamp())}:{fmt}>"
	except ValueError:
		return ""


def text_display(content: str) -> ui.TextDisplay:
	return ui.TextDisplay(content=content)


def text_only_container(content: str, *, accent_color: int | None = None) -> ui.Container:
	return ui.Container(text_display(content), accent_colour=accent_color)


def separator(*, visible: bool = True) -> ui.Separator:
	return ui.Separator(visible=visible)


def _format_request_body(request: SanctionRequest) -> str:
	lines = [
		f"## {'Ban' if request['type'] == 'ban' else 'Unban'} submission — {STATUS_LABEL[request['status']]}",
		f"Submission ID: `{request['id']}`",
		f"> **Target**\n<@{request['targetId']}> (`{_escape_markdown(request['targetTag'])}`, `{request['targetId']}`)",
		f"> **Reason**\n{_escape_markdown(request['reason'])}",
		f"**Approvals:** {len(request['approvals'])}/{request['requiredApprovals']}  •  **Declines:** {len(request['declines'])}/{request['requiredApprovals']}",
		f"**Submitted by** <@{request['submittedBy']}> (`{_escape_markdown(request['submittedByTag'])}`)",
	]
	if request.get("evidence"):
		lines.append(f"> **Evidence**\n{request['evidence']}")
	if request.get("declineReason"):
		lines.append(f"> **Decline reason**\n{_escape_markdown(request['declineReason'] or '')}")

	ts = _discord_timestamp(request["submittedAt"])
	if ts:
		lines.append(f"-# {ts}")

	return "\n".join(lines)


def build_request_container(request: SanctionRequest) -> ui.Container:
	return ui.Container(
		text_display(_format_request_body(request)),
		separator(),
		accent_colour=STATUS_COLOR[request["status"]],
	)


def build_request_list_components(
	requests: list[SanctionRequest],
	*,
	page: int,
	per_page: int,
	total: int,
	status: str | None = None,
	custom_id_prefix: str,
) -> tuple[ui.Container, Button, Button, Button, Button, ui.TextDisplay]:
	total_pages = max(1, math.ceil(total / per_page))
	safe_page = min(max(1, page), total_pages)
	start = (safe_page - 1) * per_page
	slice_ = requests[start : start + per_page]
	current = slice_[0] if slice_ else None

	header_title = (
		f"Sanction submissions — {STATUS_LABEL[status]}" if status else "Sanction submissions"
	)

	main_children: list[ui.Item] = []
	if current:
		main_children.append(text_display(_format_request_body(current)))
		main_children.append(separator())
	else:
		main_children.append(text_display(f"## {header_title}\nNo submissions found."))

	main_children.append(
		text_display(f"Page **{safe_page}** / **{total_pages}** — {total} submission(s) total")
	)

	main = ui.Container(
		*main_children,
		accent_colour=STATUS_COLOR[current["status"]] if current else None,
	)

	is_pending = current is not None and current["status"] == "pending"

	approve = Button(
		style=ButtonStyle.green,
		label="Approve",
		custom_id=f"{custom_id_prefix}|{safe_page}|approve",
		disabled=not is_pending,
	)
	decline = Button(
		style=ButtonStyle.red,
		label="Decline",
		custom_id=f"{custom_id_prefix}|{safe_page}|decline",
		disabled=not is_pending,
	)
	back = Button(
		style=ButtonStyle.secondary,
		label="Previous",
		custom_id=f"{custom_id_prefix}|{safe_page - 1}",
		disabled=safe_page <= 1,
	)
	next_btn = Button(
		style=ButtonStyle.secondary,
		label="Next",
		custom_id=f"{custom_id_prefix}|{safe_page + 1}",
		disabled=safe_page >= total_pages,
	)

	footer = text_display(
		"-# Use the buttons to vote or navigate. This message only updates for the user that triggered it."
	)

	return main, approve, decline, back, next_btn, footer


def build_sanction_container(sanction: Sanction | None, user_id: str) -> ui.Container:
	if not sanction:
		return text_only_container(
			f"## No active sanction\n<@{user_id}> (`{user_id}`) is not on the shared sanction list.",
			accent_color=0x2ECC71,
		)
	body = "\n".join(
		[
			"## Active sanction",
			f"**User:** <@{sanction['id']}> (`{sanction['id']}`)",
			f"**Reason:** {_escape_markdown(sanction['reason'])}",
			f"**Added by:** <@{sanction['addedBy']}>",
			f"**Submission ID:** `{sanction['requestId']}`",
			f"-# {_discord_timestamp(sanction['addedAt'])}",
		]
	)
	return text_only_container(body, accent_color=0xE74C3C)


def build_reviewer_list_container(reviewer_list: list[Reviewer]) -> ui.Container:
	if not reviewer_list:
		body = (
			"No reviewers configured yet. Ask an owner to add one with `/sanctions reviewer-add`."
		)
	else:
		body = "\n".join(
			f"• <@{r['id']}> — since {_discord_timestamp(r['addedAt'], fmt='D')}"
			for r in reviewer_list
		)
	return text_only_container(f"## NationSeal reviewers\n{body}", accent_color=0x3498DB)


def build_layout(*components: object) -> ui.LayoutView:
	view = ui.LayoutView()
	for component in components:
		view.add_item(component)  # type: ignore
	return view


def build_action_row(*buttons: Button) -> ActionRow:
	return ActionRow(*buttons)  # type: ignore[return-value]


async def _reply_text(interaction: discord.Interaction, message: str) -> None:
	view = build_layout(text_only_container(message))
	if interaction.response.is_done():
		await interaction.edit_original_response(view=view)
	else:
		await interaction.response.send_message(view=view, ephemeral=True)


# ── Pagination / button handler ─────────────────────────────────────────

PER_PAGE = 1
LIST_CUSTOM_ID_PREFIX = "sanction_list"
NOTIFY_CUSTOM_ID_PREFIX = "sanction_notify"


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


def _parse_notify_custom_id(
	custom_id: str,
) -> tuple[str, str] | None:
	"""Parse 'sanction_notify|<submission_id>|<approve|decline>'."""
	parts = custom_id.split("|")
	if len(parts) != 3 or parts[0] != NOTIFY_CUSTOM_ID_PREFIX:
		return None
	if parts[2] not in ("approve", "decline"):
		return None
	return parts[1], parts[2]


async def _send_submission_notification(bot: Bot, submission: SanctionRequest) -> None:
	"""Send a message to the reviewer channel pinging all reviewers."""
	channel_id = data.reviewer_channel_id()
	if channel_id is None:
		return
	channel = bot.get_channel(channel_id)
	if channel is None or not isinstance(channel, discord.abc.Messageable):
		logger.warning("[nationseal] Reviewer channel %s not found or not messageable.", channel_id)
		return

	reviewers = await data.reviewers().list_all()
	mentions = " ".join(f"<@{r['id']}>" for r in reviewers)
	header = f"## New {'ban' if submission['type'] == 'ban' else 'unban'} submission\n{mentions}"

	approve = Button(
		style=ButtonStyle.green,
		label="Approve",
		custom_id=f"{NOTIFY_CUSTOM_ID_PREFIX}|{submission['id']}|approve",
	)
	decline = Button(
		style=ButtonStyle.red,
		label="Decline",
		custom_id=f"{NOTIFY_CUSTOM_ID_PREFIX}|{submission['id']}|decline",
	)

	view = build_layout(
		ui.Container(text_display(header), accent_colour=STATUS_COLOR[submission["status"]]),
		build_request_container(submission),
		build_action_row(approve, decline),
	)
	try:
		await channel.send(view=view)
	except Exception as exc:  # noqa: BLE001
		logger.error("[nationseal] Failed to send submission notification: %s", exc)


async def _build_list_view(page: int) -> ui.LayoutView:
	all_requests = await data.sanction_requests().list_by_status("pending", 200)
	main, approve, decline, back, next_btn, footer = build_request_list_components(
		all_requests,
		page=page,
		per_page=PER_PAGE,
		total=len(all_requests),
		status="pending",
		custom_id_prefix=LIST_CUSTOM_ID_PREFIX,
	)
	return build_layout(
		main,
		build_action_row(approve, decline),
		build_action_row(back, next_btn),
		footer,
	)


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

		# Handle notification buttons (reviewer channel messages).
		notify = _parse_notify_custom_id(custom_id)
		if notify is not None:
			await self._handle_notify_vote(interaction, notify[0], notify[1])
			return

		parsed = _parse_custom_id(custom_id)
		if parsed.kind == "invalid":
			return

		if not await is_reviewer(interaction.user.id):
			await interaction.response.send_message(
				view=build_layout(
					text_only_container(
						"Only trusted NationSeal reviewers can interact with this list."
					)
				),
				ephemeral=True,
			)
			return

		if parsed.kind == "vote":
			await self._handle_vote(interaction, parsed.page, parsed.action)
		else:
			await self._handle_navigation(interaction, parsed.page)

	async def _handle_notify_vote(
		self, interaction: discord.Interaction, submission_id: str, action: str
	) -> None:
		try:
			result = await data.cast_vote(self.bot, submission_id, interaction.user.id, action)
			request = cast(SanctionRequest, result["request"])
			lines = [f"Vote recorded on `{request['id']}` ({action})."]
			if result.get("justResolved"):
				enforcement = result.get("enforcement")
				succeeded = getattr(enforcement, "guilds_succeeded", 0) if enforcement else 0
				attempted = getattr(enforcement, "guilds_attempted", 0) if enforcement else 0
				lines.append(
					f"✅ Threshold reached — {request['type']} enforced on {succeeded}/{attempted} servers."
				)
			await interaction.response.edit_message(
				view=build_layout(
					text_only_container("\n".join(lines)),
					build_request_container(request),
				)
			)
		except data.VoteError as exc:
			await interaction.response.send_message(
				view=build_layout(text_only_container(str(exc))),
				ephemeral=True,
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] notify vote failed: %s", exc)

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
			all_requests = await data.sanction_requests().list_by_status("pending", 200)
			index = (page - 1) * PER_PAGE
			request = all_requests[index] if index < len(all_requests) else None

			if request is None:
				await interaction.response.edit_message(
					view=build_layout(text_only_container("No submission found at this position."))
				)
				return

			result = await data.cast_vote(self.bot, request["id"], interaction.user.id, action)  # type: ignore

			lines = [f"Vote recorded on `{request['id']}` ({action})."]
			if result.get("justResolved"):
				enforcement = result.get("enforcement")
				succeeded = getattr(enforcement, "guilds_succeeded", 0) if enforcement else 0
				attempted = getattr(enforcement, "guilds_attempted", 0) if enforcement else 0
				lines.append(
					f"✅ Threshold reached — {request['type']} enforced on {succeeded}/{attempted} servers."
				)

			list_view = await _build_list_view(page)
			summary = text_only_container("\n".join(lines))
			items = [summary, *list_view.children]
			await interaction.response.edit_message(view=build_layout(*items))
		except data.VoteError as exc:
			await interaction.response.edit_message(
				view=build_layout(text_only_container(str(exc)))
			)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] sanction list vote failed: %s", exc)
			await interaction.response.edit_message(
				view=build_layout(text_only_container("An error occurred while voting."))
			)


# ── Slash commands ─────────────────────────────────────────────────────


async def _id_autocomplete(
	interaction: discord.Interaction,
	current: str,
	*,
	statuses: list[SanctionRequestStatus],
) -> list[app_commands.Choice[str]]:
	current_lower = current.lower()
	all_requests: list[SanctionRequest] = []
	for status in statuses:
		all_requests.extend(await data.sanction_requests().list_by_status(status, 25))

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


def _user_tag(user: discord.abc.User) -> str:
	return f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name


def _respond(
	interaction: discord.Interaction, *items: object, ephemeral: bool = True
) -> Awaitable[object]:
	view = build_layout(*items)
	if interaction.response.is_done():
		return interaction.edit_original_response(view=view)
	return interaction.response.send_message(view=view, ephemeral=ephemeral)


# Per-command autocomplete wrappers (discord.py requires coroutine functions,
# not lambdas, and we need different status filters per command).
async def _info_autocomplete(
	interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
	return await _id_autocomplete(
		interaction, current, statuses=["pending", "approved", "declined"]
	)


class SanctionsCog(commands.Cog):
	def __init__(self, bot: Bot) -> None:
		self.bot = bot

	sanctions = app_commands.Group(
		name="sanctions",
		description="Manage the NationSeal shared sanction list",
		guild_only=True,
		default_permissions=discord.Permissions(ban_members=True),
	)

	# ── submit ─────────────────────────────────────────────────────────

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
			await _respond(
				interaction, text_only_container("Bots can't be added to the sanction list.")
			)
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
			request = await data.submit_request(
				{
					"type": "ban",
					"targetId": str(user.id),
					"targetTag": _user_tag(user),
					"reason": reason,
					"evidence": evidence,
					"submittedBy": str(interaction.user.id),
					"submittedByTag": _user_tag(interaction.user),
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
			await _send_submission_notification(self.bot, request)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] submit command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while submitting the sanction. Please try again later."
				),
			)

	# ── appeal ────────────────────────────────────────────────────────

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

		existing = await data.sanctions().get(str(user.id))
		if not existing:
			await _respond(
				interaction,
				text_only_container(f"<@{user.id}> is not currently on the shared sanction list."),
			)
			return

		try:
			request = await data.submit_request(
				{
					"type": "unban",
					"targetId": str(user.id),
					"targetTag": _user_tag(user),
					"reason": reason,
					"evidence": None,
					"submittedBy": str(interaction.user.id),
					"submittedByTag": _user_tag(interaction.user),
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
			await _send_submission_notification(self.bot, request)
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] appeal command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while submitting the appeal. Please try again later."
				),
			)

	# ── check / info ─────────────────────────────────────────────────

	@sanctions.command(
		name="check", description="Check whether a user is on the shared sanction list"
	)
	@app_commands.describe(user="The user to look up")
	async def check(self, interaction: discord.Interaction, user: discord.User) -> None:
		await interaction.response.defer(ephemeral=True)
		try:
			sanction = await data.sanctions().get(str(user.id))
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
			request = await data.sanction_requests().get(id.strip())
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

	# ── list / enforce / local-enforce ───────────────────────────────

	@sanctions.command(
		name="list", description="List pending submissions waiting for approval (reviewers only)"
	)
	async def list_(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True)
		if not await require_reviewer(interaction):
			return

		try:
			all_requests = await data.sanction_requests().list_by_status("pending", 200)
			main, approve, decline, back, next_btn, footer = build_request_list_components(
				all_requests,
				page=1,
				per_page=PER_PAGE,
				total=len(all_requests),
				status="pending",
				custom_id_prefix=LIST_CUSTOM_ID_PREFIX,
			)
			await _respond(
				interaction,
				main,
				build_action_row(approve, decline),
				build_action_row(back, next_btn),
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
			active = await data.sanctions().list_all()
			if not active:
				await _respond(interaction, text_only_container("No active sanctions to enforce."))
				return

			total_banned = 0
			total_attempted = 0
			results: list[str] = []
			for sanction in active:
				result = await data.ban_across_guilds(
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
		description="Manually push the shared sanction list into a server (owners only)",
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

			total = len(await data.sanctions().list_all())
			if total == 0:
				await _respond(
					interaction,
					text_only_container("The shared sanction list is empty — nothing to enforce."),
				)
				return

			result = await data.enforce_all_sanctions_on_guild(self.bot, guild_id)
			await data.guild_states().mark_enforced(guild_id)
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

	# ── reviewer roster ─────────────────────────────────────────────

	@sanctions.command(
		name="reviewer-add",
		description="Add a trusted reviewer to the multi-sig roster (owners only)",
	)
	@app_commands.describe(user="The user to add as a trusted reviewer")
	async def reviewer_add(self, interaction: discord.Interaction, user: discord.User) -> None:
		await interaction.response.defer(ephemeral=True)
		if not await require_owner(interaction):
			return

		try:
			await data.reviewers().add(str(user.id), str(interaction.user.id))
			logger.info(
				"[nationseal] AUDIT reviewerAdd reviewer=%s by=%s", user.id, interaction.user.id
			)
			await _respond(
				interaction, text_only_container(f"<@{user.id}> is now a trusted reviewer.")
			)
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
			await data.reviewers().remove(str(user.id))
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
			reviewers = await data.reviewers().list_all()
			await _respond(interaction, build_reviewer_list_container(reviewers))
		except Exception as exc:  # noqa: BLE001
			logger.error("[nationseal] reviewer-list command failed: %s", exc)
			await _respond(
				interaction,
				text_only_container(
					"Something went wrong while fetching the reviewer roster. Please try again later."
				),
			)
