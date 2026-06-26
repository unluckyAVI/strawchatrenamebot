"""
Media handler — core pipeline.

1. Receive document / video / audio
2. Download with progress
3. Parse filename → apply format (or override)
4. Run FFmpeg to embed metadata (-c copy)
5. Upload with progress
6. Caption = filename only
"""

from __future__ import annotations
import os
import time
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from parser import parse_filename, build_output_name
from ffmpeg_utils import embed_metadata, extract_thumbnail
from progress import ProgressReporter
from state import state_manager

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_media(message: Message):
    """Return the first media object from the message (document/video/audio)."""
    return message.document or message.video or message.audio


def _get_file_name(message: Message) -> str:
    """Best-effort filename from the message media."""
    media = _get_media(message)
    if not media:
        return "unknown"
    # document has file_name; video/audio may not
    name = getattr(media, "file_name", None)
    if name:
        return name
    mime = getattr(media, "mime_type", "")
    ext_map = {
        "video/x-matroska": ".mkv", "video/mp4": ".mp4",
        "video/webm": ".webm", "audio/mpeg": ".mp3",
        "audio/x-flac": ".flac", "audio/ogg": ".ogg",
    }
    ext = ext_map.get(mime, "")
    return f"media_{media.file_id[-8:]}{ext}"


def _tmp_path(suffix: str = "") -> str:
    uid = uuid.uuid4().hex
    return os.path.join(Config.DOWNLOAD_DIR, f"{uid}{suffix}")


def _out_path(name: str) -> str:
    # Sanitise slashes just in case
    safe = name.replace("/", "-").replace("\\", "-")
    return os.path.join(Config.OUTPUT_DIR, safe)


# ── Photo handler (for /thumbnail flow) ──────────────────────────────────────

@Client.on_message(filters.private & filters.photo)
async def handle_photo(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    if not state.awaiting_thumbnail:
        return  # Not in thumbnail-setting mode; ignore

    state.awaiting_thumbnail = False
    status = await message.reply_text("⏬ Downloading thumbnail…")

    try:
        thumb_path = os.path.join(
            Config.THUMB_DIR, f"thumb_{message.chat.id}.jpg"
        )
        await client.download_media(message, file_name=thumb_path)
        state_manager.set_thumbnail(message.chat.id, thumb_path)
        await status.edit_text("✅ Thumbnail saved! It will be used for all future files.")
    except Exception as e:
        await status.edit_text(f"❌ Failed to save thumbnail: {e}")


# ── Text handler (for /rename flow) ──────────────────────────────────────────

@Client.on_message(filters.private & filters.text & ~filters.command(
    ["start", "help", "metadata", "tokens", "format",
     "setformat", "resetformat", "preview", "examples",
     "thumbnail", "clearthumbnail", "rename"]
))
async def handle_text(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    if not state.awaiting_rename:
        return

    state.awaiting_rename = False
    custom_name = message.text.strip()
    state_manager.set_rename_override(message.chat.id, custom_name)
    await message.reply_text(
        f"✅ Custom name set: `{custom_name}`\n"
        "Now send me the file and I'll use this name."
    )


# ── Main media handler ────────────────────────────────────────────────────────

@Client.on_message(
    filters.private
    & (filters.document | filters.video | filters.audio)
)
async def handle_media(client: Client, message: Message):
    chat_id = message.chat.id
    state = state_manager.get(chat_id)
    media = _get_media(message)

    if not media:
        return

    raw_name = _get_file_name(message)
    logger.info("[%s] Received: %s", chat_id, raw_name)

    # ── Determine output filename ─────────────────────────────────────────────
    custom = state_manager.consume_rename_override(chat_id)
    if custom:
        out_name = custom
    else:
        pf = parse_filename(raw_name)
        out_name = build_output_name(pf, state.fmt)

    # ── Status message ────────────────────────────────────────────────────────
    status = await message.reply_text("⏳ Starting…")

    # ── Download ──────────────────────────────────────────────────────────────
    dl_path = _tmp_path(Path(raw_name).suffix or "")
    try:
        dl_reporter = ProgressReporter(status, "⏬ Downloading", raw_name)
        await status.edit_text(f"⏬ **Downloading…**\n`{raw_name}`")
        dl_path = await client.download_media(
            message,
            file_name=dl_path,
            progress=dl_reporter.update,
        )
    except Exception as e:
        logger.exception("Download failed")
        await status.edit_text(f"❌ Download failed: {e}")
        return

    # ── FFmpeg embed ──────────────────────────────────────────────────────────
    out_full = _out_path(out_name)
    try:
        await status.edit_text(f"⚙️ **Embedding metadata…**\n`{out_name}`")
        await embed_metadata(dl_path, out_full, thumbnail_path=state.thumbnail, meta_overrides=state.custom_meta)
    except Exception as e:
        logger.exception("FFmpeg failed")
        await status.edit_text(f"❌ FFmpeg error: {e}")
        _cleanup(dl_path, out_full)
        return
    finally:
        _cleanup(dl_path)  # remove download once processed

    # ── Thumbnail for upload ──────────────────────────────────────────────────
    thumb_for_upload: Optional[str] = None
    if state.thumbnail and os.path.isfile(state.thumbnail):
        thumb_for_upload = state.thumbnail
    else:
        # Try to auto-extract
        auto_thumb = _tmp_path(".jpg")
        ok = await extract_thumbnail(out_full, auto_thumb)
        if ok:
            thumb_for_upload = auto_thumb

    # ── Upload ────────────────────────────────────────────────────────────────
    try:
        up_reporter = ProgressReporter(status, "⏫ Uploading", out_name)
        await status.edit_text(f"⏫ **Uploading…**\n`{out_name}`")

        file_size = os.path.getsize(out_full)
        send_kwargs = dict(
            chat_id=chat_id,
            caption=out_name,          # caption = filename only
            file_name=out_name,
            thumb=thumb_for_upload,
            progress=up_reporter.update,
        )

        await client.send_document(**send_kwargs, document=out_full)

        await status.delete()

    except Exception as e:
        logger.exception("Upload failed")
        await status.edit_text(f"❌ Upload failed: {e}")
    finally:
        _cleanup(out_full)
        if thumb_for_upload and thumb_for_upload != state.thumbnail:
            _cleanup(thumb_for_upload)


def _cleanup(*paths: str):
    for p in paths:
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
