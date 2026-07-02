"""
Media handler — concurrent pipeline.
Each file is processed in its own independent async task.
Multiple files can be processed simultaneously at full speed.
"""

from __future__ import annotations
import os
import re
import uuid
import logging
import asyncio
import io
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from autorename import build_filename
from parser import parse_filename, build_output_name
from ffmpeg_utils import embed_metadata, extract_thumbnail
from progress import ProgressReporter
from state import state_manager
from handlers.auth import is_admin

logger = logging.getLogger(__name__)

# Track active tasks per chat so we can show queue position
_active_tasks: dict[int, int] = {}


def _get_media(message: Message):
    return message.document or message.video or message.audio


def _get_file_name(message: Message) -> str:
    media = _get_media(message)
    if not media:
        return "unknown"
    name = getattr(media, "file_name", None)
    if name:
        return name
    mime = getattr(media, "mime_type", "")
    ext_map = {
        "video/x-matroska": ".mkv", "video/mp4": ".mp4",
        "video/webm": ".webm", "audio/mpeg": ".mp3",
        "audio/x-flac": ".flac", "audio/ogg": ".ogg",
    }
    return f"media_{media.file_id[-8:]}{ext_map.get(mime, '')}"


def _sanitise(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()


def _uid() -> str:
    return uuid.uuid4().hex


def _cleanup(*paths: str):
    for p in paths:
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


# ── Photo handler ─────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.photo)
async def handle_photo(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
    state = state_manager.get(message.chat.id)
    if not state.awaiting_thumbnail:
        return
    state.awaiting_thumbnail = False
    status = await message.reply_text("⏬ Downloading thumbnail…")
    try:
        thumb_path = os.path.join(Config.THUMB_DIR, f"thumb_{message.chat.id}.jpg")
        await client.download_media(message, file_name=thumb_path)
        state_manager.set_thumbnail(message.chat.id, thumb_path)
        await status.edit_text("✅ Thumbnail saved! Used for all future files.")
    except Exception as e:
        await status.edit_text(f"❌ Failed: {e}")


# ── Text handler ──────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.text & ~filters.command(
    ["start", "help", "metadata", "tokens", "format",
     "setformat", "resetformat", "preview", "examples",
     "thumbnail", "clearthumbnail", "rename", "setmeta", "resetmeta"]
))
async def handle_text(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return
    state = state_manager.get(message.chat.id)
    if not state.awaiting_rename:
        return
    state.awaiting_rename = False
    custom_name = message.text.strip()
    state_manager.set_rename_override(message.chat.id, custom_name)
    await message.reply_text(
        f"✅ Custom name set: `{custom_name}`\nNow send me the file."
    )


# ── Core processing function ──────────────────────────────────────────────────

async def _process_file(client: Client, message: Message, chat_id: int):
    """
    Full pipeline for one file.
    Runs independently — multiple can run simultaneously.
    """
    state = state_manager.get(chat_id)
    raw_name = _get_file_name(message)
    logger.info("[%s] Processing: %s", chat_id, raw_name)

    # ── Build output name ─────────────────────────────────────────────────────
    custom = state_manager.consume_rename_override(chat_id)
    if custom:
        out_name = _sanitise(custom)
    else:
        out_name = _sanitise(build_filename(raw_name, state.fmt))

    logger.info("[%s] Output: %s", chat_id, out_name)

    status = await message.reply_text(f"⏳ **Queued**\n`{out_name}`")

    # ── Download ──────────────────────────────────────────────────────────────
    ext = Path(raw_name).suffix or ""
    dl_path = os.path.join(Config.DOWNLOAD_DIR, f"dl_{_uid()}{ext}")
    try:
        await status.edit_text(f"⏬ **Downloading…**\n`{raw_name}`")
        dl_reporter = ProgressReporter(status, "⏬ Downloading", raw_name)
        dl_path = await client.download_media(
            message, file_name=dl_path, progress=dl_reporter.update,
        )
    except Exception as e:
        logger.exception("Download failed")
        await status.edit_text(f"❌ Download failed: {e}")
        return

    # ── FFmpeg ────────────────────────────────────────────────────────────────
    final_path = os.path.join(Config.OUTPUT_DIR, f"{_uid()}_{out_name}")
    try:
        await status.edit_text(f"⚙️ **Processing…**\n`{out_name}`")
        await embed_metadata(
            dl_path, final_path,
            thumbnail_path=state.thumbnail,
            meta_overrides=state.custom_meta,
        )
    except Exception as e:
        logger.exception("FFmpeg failed")
        await status.edit_text(f"❌ FFmpeg error: {e}")
        _cleanup(dl_path, final_path)
        return
    finally:
        _cleanup(dl_path)

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    thumb_for_upload: Optional[str] = None
    if state.thumbnail and os.path.isfile(state.thumbnail):
        thumb_for_upload = state.thumbnail
    else:
        auto_thumb = os.path.join(Config.DOWNLOAD_DIR, f"thumb_{_uid()}.jpg")
        if await extract_thumbnail(final_path, auto_thumb):
            thumb_for_upload = auto_thumb

    # ── Upload ────────────────────────────────────────────────────────────────
    try:
        await status.edit_text(f"⏫ **Uploading…**\n`{out_name}`")
        up_reporter = ProgressReporter(status, "⏫ Uploading", out_name)

        with open(final_path, "rb") as f:
            buf = io.BytesIO(f.read())
        buf.name = out_name

        await client.send_document(
            chat_id=chat_id,
            document=buf,
            caption=out_name,
            thumb=thumb_for_upload,
            progress=up_reporter.update,
            force_document=True,
        )
        await status.delete()

    except Exception as e:
        logger.exception("Upload failed")
        await status.edit_text(f"❌ Upload failed: {e}")
    finally:
        _cleanup(final_path)
        if thumb_for_upload and thumb_for_upload != state.thumbnail:
            _cleanup(thumb_for_upload)


# ── Main media handler ────────────────────────────────────────────────────────

@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio)
)
async def handle_media(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id

    # Fire and forget — each file runs in its own independent task
    # This allows multiple files to be processed simultaneously
    asyncio.create_task(
        _process_file(client, message, chat_id)
    )
