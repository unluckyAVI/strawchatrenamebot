"""
Auth handler — admin only access control.
Silently ignores all messages from non-admin users.
Add ADMIN_IDS to your environment variables as comma-separated IDs.
e.g. ADMIN_IDS=123456789,987654321
"""

from pyrogram import Client, filters
from pyrogram.types import Message
import os

# Load admin IDs from env — comma separated
# e.g. ADMIN_IDS=123456789,987654321
_raw = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = set(
    int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()
)


def is_admin(user_id: int) -> bool:
    """Return True if user is admin or no admins configured."""
    if not ADMIN_IDS:
        return True  # No restriction if not configured
    return user_id in ADMIN_IDS


@Client.on_message(
    filters.private
    & ~filters.command(["start"])  # Allow /start for everyone
)
async def auth_gate(client: Client, message: Message):
    """
    Block all non-admin users.
    This handler runs BEFORE all others (group -1).
    """
    if not is_admin(message.from_user.id):
        await message.reply_text(
            "🔒 **This bot is private.**\n\n"
            "Only authorized users can use this bot.\n"
            f"Contact the owner to get access."
        )
        message.stop_propagation()
