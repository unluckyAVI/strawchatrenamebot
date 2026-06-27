"""
Media handler — core pipeline.
Downloads, processes with FFmpeg, saves with correct name, uploads as document.
"""

from __future__ import annotations
import os
import re
import uuid
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
    # Remove filesystem unsafe chars but keep spaces and brackets
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
    await message.reply_text(
        f"✅ Custom name set: `{custom_name}`\nNow send me the file."
    )


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

    logger.info("[%s] Output name: %s", chat_id, out_name)

    status = await message.reply_text("⏳ Starting…")

    # ── Download to temp path ─────────────────────────────────────────────────
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

    # ── FFmpeg — output directly to correctly named file ──────────────────────
    # IMPORTANT: the output file IS named correctly on disk
    # Pyrogram will use os.path.basename(file_path) as the filename
    out_ext = Path(out_name).suffix or ext
    final_path = os.path.join(Config.OUTPUT_DIR, out_name)

    try:
        if state.metadata_enabled:
            await status.edit_text(f"⚙️ **Embedding metadata…**\n`{out_name}`")
            await embed_metadata(
                dl_path, final_path,
                thumbnail_path=state.thumbnail,
                meta_overrides=state.custom_meta,
            )
        else:
            # Metadata embedding off — just move the downloaded file to its
            # correctly-named final path, no ffmpeg pass needed.
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            os.replace(dl_path, final_path)
    except Exception as e:
        logger.exception("FFmpeg failed")
        await status.edit_text(f"❌ FFmpeg error: {e}")
        _cleanup(dl_path, final_path)
        return
    finally:
        _cleanup(dl_path)

    logger.info("[%s] Final file path: %s", chat_id, final_path)
    logger.info("[%s] File exists: %s", chat_id, os.path.isfile(final_path))

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    thumb_for_upload: Optional[str] = None
    if state.thumbnail and os.path.isfile(state.thumbnail):
        thumb_for_upload = state.thumbnail
    else:
        auto_thumb = os.path.join(Config.DOWNLOAD_DIR, f"thumb_{_uid()}.jpg")
        if await extract_thumbnail(final_path, auto_thumb):
            thumb_for_upload = auto_thumb

    # ── Upload ────────────────────────────────────────────────────────────────
    # Send final_path as string — Pyrogram uses os.path.basename(final_path)
    # as the filename. Since final_path ends with out_name, this is correct.
    try:
        await status.edit_text(f"⏫ **Uploading…**\n`{out_name}`")
        up_reporter = ProgressReporter(status, "⏫ Uploading", out_name)

        await client.send_document(
            chat_id=chat_id,
            document=final_path,          # file path — basename = out_name ✅
            file_name=out_name,           # explicit override
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
