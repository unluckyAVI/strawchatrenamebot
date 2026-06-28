"""
Forward fix handler.
Intercepts forwarded files BEFORE the main media handler.
Copies the forwarded file to remove the original file_id cache,
then processes it so Telegram shows our renamed filename correctly.
"""

import os
import re
import logging
import uuid
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from parser import parse_filename, build_output_name
from ffmpeg_utils import embed_metadata, extract_thumbnail
from progress import ProgressReporter
from state import state_manager
from handlers.auth import is_admin

logger = logging.getLogger(__name__)


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


def _get_file_name(message: Message) -> str:
    media = message.document or message.video or message.audio
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


@Client.on_message(
    filters.private
    & (filters.document | filters.video | filters.audio)
    & filters.forwarded,
    group=0,
)
async def handle_forwarded_file(client: Client, message: Message):
    """
    Handles forwarded files specially:
    1. Downloads the file
    2. Renames + embeds metadata via FFmpeg
    3. Uploads as a FRESH file (new file_id = correct filename shown)
    """
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    state = state_manager.get(chat_id)

    raw_name = _get_file_name(message)
    logger.info("[%s] Forwarded file: %s", chat_id, raw_name)

    # ── Build output name ─────────────────────────────────────────────────────
    custom = state_manager.consume_rename_override(chat_id)
    if custom:
        out_name = _sanitise(custom)
    else:
        pf = parse_filename(raw_name)
        out_name = _sanitise(build_output_name(pf, state.fmt))

    logger.info("[%s] Output name: %s", chat_id, out_name)

    status = await message.reply_text("⏳ Starting…")

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
    final_path = os.path.join(Config.OUTPUT_DIR, out_name)
    try:
        await status.edit_text(f"⚙️ **Embedding metadata…**\n`{out_name}`")
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

    # ── Upload as FRESH file ──────────────────────────────────────────────────
    # Reading into bytes and uploading fresh means Telegram assigns a NEW
    # file_id — so it shows OUR filename, not the original forwarded filename!
    try:
        await status.edit_text(f"⏫ **Uploading…**\n`{out_name}`")
        up_reporter = ProgressReporter(status, "⏫ Uploading", out_name)

        import io
        with open(final_path, "rb") as f:
            raw_bytes = f.read()

        # Upload in chunks to avoid memory issues with large files
        buf = io.BytesIO(raw_bytes)
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

    # Stop propagation so media.py doesn't process it again
    message.stop_propagation()
