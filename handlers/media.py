"""
Media handler — core pipeline.
Sends file as BytesIO with .name set to force correct filename.
"""

from __future__ import annotations
import os
import re
import uuid
import logging
import io
import pyrogram

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


def _tmp_path(suffix: str = "") -> str:
    return os.path.join(Config.DOWNLOAD_DIR, f"{uuid.uuid4().hex}{suffix}")


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
    state = state_manager.get(message.chat.id)
    if not state.awaiting_thumbnail:
        return
    state.awaiting_thumbnail = False
    status = await message.reply_text("⏬ Downloading thumbnail…")
    try:
        thumb_path = os.path.join(Config.THUMB_DIR, f"thumb_{message.chat.id}.jpg")
        await client.download_media(message, file_name=thumb_path)
        state_manager.set_thumbnail(message.chat.id, thumb_path)
        await status.edit_text("✅ Thumbnail saved!")
    except Exception as e:
        await status.edit_text(f"❌ Failed: {e}")


# ── Text handler ──────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.text & ~filters.command(
    ["start", "help", "metadata", "tokens", "format",
     "setformat", "resetformat", "preview", "examples",
     "thumbnail", "clearthumbnail", "rename", "setmeta", "resetmeta"]
))
async def handle_text(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    if not state.awaiting_rename:
        return
    state.awaiting_rename = False
    custom_name = message.text.strip()
    state_manager.set_rename_override(message.chat.id, custom_name)
    await message.reply_text(f"✅ Custom name set: `{custom_name}`\nNow send me the file.")


# ── Main media handler ────────────────────────────────────────────────────────

@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio)
)
async def handle_media(client: Client, message: Message):
    chat_id = message.chat.id
    state = state_manager.get(chat_id)
    media = _get_media(message)
    if not media:
        return

    raw_name = _get_file_name(message)
    logger.info("[%s] Received: %s", chat_id, raw_name)

    # ── Build output name ─────────────────────────────────────────────────────
    custom = state_manager.consume_rename_override(chat_id)
    if custom:
        out_name = _sanitise(custom)
    else:
        pf = parse_filename(raw_name)
        out_name = _sanitise(build_output_name(pf, state.fmt))

    logger.info("DEBUG_OUT_NAME: %s", out_name)
    logger.info("DEBUG_RAW_NAME: %s", raw_name)

    status = await message.reply_text("⏳ Starting…")

    # ── Download ──────────────────────────────────────────────────────────────
    dl_path = _tmp_path(Path(raw_name).suffix or "")
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
    ffmpeg_out = _tmp_path(Path(out_name).suffix or ".mkv")
    try:
        await status.edit_text(f"⚙️ **Embedding metadata…**\n`{out_name}`")
        await embed_metadata(
            dl_path, ffmpeg_out,
            thumbnail_path=state.thumbnail,
            meta_overrides=state.custom_meta,
        )
    except Exception as e:
        logger.exception("FFmpeg failed")
        await status.edit_text(f"❌ FFmpeg error: {e}")
        _cleanup(dl_path, ffmpeg_out)
        return
    finally:
        _cleanup(dl_path)

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    thumb_for_upload: Optional[str] = None
    if state.thumbnail and os.path.isfile(state.thumbnail):
        thumb_for_upload = state.thumbnail
    else:
        auto_thumb = _tmp_path(".jpg")
        if await extract_thumbnail(ffmpeg_out, auto_thumb):
            thumb_for_upload = auto_thumb

    # ── Upload ────────────────────────────────────────────────────────────────
    try:
        await status.edit_text(f"⏫ **Uploading…**\n`{out_name}`")
        up_reporter = ProgressReporter(status, "⏫ Uploading", out_name)

        
        logger.info("DEBUG_PYROGRAM_VERSION: %s", pyrogram.__version__)

        # Read file into memory and set .name to our desired filename
        with open(ffmpeg_out, "rb") as f:
            buf = io.BytesIO(f.read())
        buf.name = out_name
        logger.info("DEBUG_BYTESIO_NAME: %s", buf.name)

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
        _cleanup(ffmpeg_out)
        if thumb_for_upload and thumb_for_upload != state.thumbnail:
            _cleanup(thumb_for_upload)