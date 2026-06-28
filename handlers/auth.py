"""
Auth handler — admin only access control.
Blocks non-admin users from using the bot.
Set ADMIN_IDS in environment variables as comma-separated Telegram user IDs.
e.g. ADMIN_IDS=123456789,987654321
"""

import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

logger = logging.getLogger(__name__)

# Load admin IDs from env
_raw = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = set(
    int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()
)

logger.info("Admin IDs loaded: %s", ADMIN_IDS)


def is_admin(user_id: int) -> bool:
    """Return True if user is admin or no admins configured."""
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


@Client.on_message(
    filters.private & ~filters.command("start"),
    group=-999,  # Run FIRST before all other handlers
)
async def auth_gate(client: Client, message: Message):
    """Block non-admins. Let admins through."""
    user_id = message.from_user.id if message.from_user else 0

    if is_admin(user_id):
        # Admin — do nothing, let other handlers process
        return

    # Not admin — block and stop
    await message.reply_text(
        "🔒 **This bot is private.**\n\n"
        "Only authorized users can use this bot."
    )
    message.stop_propagation()
