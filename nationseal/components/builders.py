"""Components v2 builders using discord.ui LayoutView primitives."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import discord.ui as ui
from discord import ButtonStyle
from discord.ui import ActionRow, Button

from nationseal.models import Reviewer, Sanction, SanctionRequest

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
	return "".join(f"\\{ch}" if ch in "*_`~|>" else ch for ch in text)


def _discord_timestamp(iso_string: str) -> str:
	try:
		dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
		if dt.tzinfo is None:
			dt = dt.replace(tzinfo=UTC)
		return f"<t:{int(dt.timestamp())}:R>"
	except ValueError:
		return ""


def text_display(content: str) -> ui.TextDisplay:
	return ui.TextDisplay(content=content)


def text_only_container(content: str, *, accent_color: int | None = None) -> ui.Container:
	return ui.Container(text_display(content), accent_colour=accent_color)


def separator(*, visible: bool = True) -> ui.Separator:
	return ui.Separator(visible=visible)


def spacer() -> ui.Separator:
	return ui.Separator(visible=False)


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

	header_title = f"Sanction submissions — {STATUS_LABEL[status]}" if status else "Sanction submissions"

	main_children: list[ui.Item] = []
	if current:
		main_children.append(text_display(_format_request_body(current)))
		main_children.append(separator())
	else:
		main_children.append(text_display(f"## {header_title}\nNo submissions found."))

	main_children.append(
		text_display(f"Page **{safe_page}** / **{total_pages}** — {total} submission(s) total")
	)

	main = ui.Container(*main_children, accent_colour=STATUS_COLOR[current["status"]] if current else None)

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
	next_ = Button(
		style=ButtonStyle.secondary,
		label="Next",
		custom_id=f"{custom_id_prefix}|{safe_page + 1}",
		disabled=safe_page >= total_pages,
	)

	footer = text_display(
		"-# Use the buttons to vote or navigate. This message only updates for the user that triggered it."
	)

	return main, approve, decline, back, next_, footer


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
		body = "No reviewers configured yet. Ask an owner to add one with `/sanctions reviewer-add`."
	else:
		body = "\n".join(
			f"• <@{reviewer['id']}> — since {_discord_timestamp(reviewer['addedAt']).replace(':R>', ':D>')}"
			for reviewer in reviewer_list
		)
	return text_only_container(f"## NationSeal reviewers\n{body}", accent_color=0x3498DB)


def build_layout(*components: object) -> ui.LayoutView:
	view = ui.LayoutView()
	for component in components:
		view.add_item(component)  # type: ignore
	return view


def build_action_row(*buttons: Button) -> ActionRow:
	return ActionRow(*buttons)  # type: ignore[return-value]
