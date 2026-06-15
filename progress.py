"""
Progress helpers.
Edits a single Telegram message to show a live progress bar.
"""

from __future__ import annotations
import time
from typing import Optional

from pyrogram.types import Message


def _make_bar(pct: float, width: int = 20) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return bar


def _human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _eta(elapsed: float, pct: float) -> str:
    if pct <= 0:
        return "–"
    total = elapsed / (pct / 100)
    remaining = total - elapsed
    if remaining < 60:
        return f"{remaining:.0f}s"
    return f"{remaining / 60:.1f}m"


class ProgressReporter:
    """
    Call update() from a Pyrogram progress callback.
    Throttles edits to once per ~2 seconds to avoid flood waits.
    """

    def __init__(
        self,
        message: Message,
        action: str = "Processing",
        file_name: str = "",
    ):
        self._msg = message
        self._action = action
        self._file_name = file_name
        self._last_edit: float = 0.0
        self._start = time.time()

    async def update(self, current: int, total: int) -> None:
        now = time.time()
        if now - self._last_edit < 2.0 and current < total:
            return
        self._last_edit = now

        pct = (current / total * 100) if total else 0
        elapsed = now - self._start

        name_part = f"`{self._file_name}`\n" if self._file_name else ""
        text = (
            f"**{self._action}…**\n"
            f"{name_part}"
            f"`{_make_bar(pct)}` **{pct:.1f}%**\n"
            f"{_human_size(current)} / {_human_size(total)} "
            f"• ETA: {_eta(elapsed, pct)}"
        )
        try:
            await self._msg.edit_text(text)
        except Exception:
            pass  # Message may have been deleted; ignore silently
