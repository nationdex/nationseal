"""Environment variable parsing."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

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
	bot_token: str
	owner_ids: list[str]
	required_approvals: int
	ban_delete_message_seconds: int
	database_path: str
	antiraid_bot_ids: list[str]

	def __init__(self) -> None:
		self.bot_token = os.getenv("BOT_TOKEN", "")
		self.owner_ids = _parse_ids(os.getenv("OWNER_IDS"))
		self.required_approvals = max(1, _parse_number(os.getenv("REQUIRED_APPROVALS"), 2))
		self.ban_delete_message_seconds = min(
			604_800, max(0, _parse_number(os.getenv("BAN_DELETE_MESSAGE_SECONDS"), 0))
		)
		self.database_path = os.getenv("DATABASE_PATH", "./.data/data.json")
		self.antiraid_bot_ids = _parse_ids(os.getenv("ANTIRAID_BOT_IDS"))

		if not self.bot_token:
			raise RuntimeError("[nationseal] BOT_TOKEN is not set in environment variables.")
		if not self.owner_ids:
			raise RuntimeError(
				"[nationseal] OWNER_IDS is empty. At least one owner is required to manage reviewers."
			)


config = Config()
