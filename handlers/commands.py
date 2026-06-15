"""
Command handlers:
  /start  /help  /metadata  /tokens  /format  /setformat  /resetformat
  /preview  /examples  /thumbnail  /clearthumbnail  /rename
"""

from __future__ import annotations
import os

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from parser import parse_filename, build_output_name, apply_format, ParsedFile
from state import state_manager

# ── /start ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message):
    await message.reply_text(
        "👋 **Welcome to @StraWchatOfficial Rename Bot!**\n\n"
        "Send me any **document / video / audio** file and I'll:\n"
        "• Parse the filename automatically\n"
        "• Rename it using your format template\n"
        "• Embed channel metadata (FFmpeg copy — no re-encode)\n"
        "• Send it back with a clean caption\n\n"
        "Use /help for the full command reference.\n\n"
        f"💬 Channel: {Config.CHANNEL_TAG}"
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("help") & filters.private)
async def cmd_help(client: Client, message: Message):
    await message.reply_text(
        "**📖 Bot Help**\n\n"
        "**Send any file** → automatic rename + metadata embed → file returned.\n\n"
        "**Commands**\n"
        "`/start` — welcome message\n"
        "`/help` — this message\n"
        "`/metadata` — explain embedded metadata\n"
        "`/tokens` — list format tokens\n"
        "`/format` — show current format + thumbnail status\n"
        "`/setformat <template>` — save custom format\n"
        "`/resetformat` — restore default format\n"
        "`/preview <filename>` — dry-run rename preview\n"
        "`/examples` — 5 sample renames\n"
        "`/thumbnail` — set a custom thumbnail\n"
        "`/clearthumbnail` — remove thumbnail\n"
        "`/rename` — type a fully custom output name for the next file\n\n"
        "**Format must include** `{title}`, `{SE}`, or `{E}`.\n"
        f"Default: `{Config.DEFAULT_FORMAT}`\n\n"
        f"💬 {Config.CHANNEL_TAG}"
    )


# ── /metadata ─────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("metadata") & filters.private)
async def cmd_metadata(client: Client, message: Message):
    await message.reply_text(
        "**🏷 Embedded Metadata**\n\n"
        "**Global (file-level)**\n"
        f"• `title` → `{Config.METADATA_TITLE}`\n"
        f"• `author / artist / comment` → `{Config.METADATA_AUTHOR}`\n"
        f"• `encoded_by / encoder` → `{Config.METADATA_ENCODER}`\n"
        f"• `copyright` → `{Config.METADATA_COPYRIGHT}`\n"
        f"• `PURL` → `{Config.METADATA_PURL}`\n\n"
        "**Per-stream**\n"
        "• Video stream → `Encoded By :- Team @StraWchatOfficial`\n"
        "• Each audio stream → `<Lang> tg:- [@StraWchatOfficial]`\n"
        "• Each subtitle stream → `<Lang> tg:- [@StraWchatOfficial]`\n\n"
        "**Lang codes**: eng→Eng, hin→Hin, tam→Tam, tel→Tel, mal→Mal,\n"
        "jpn→Jpn, chi/zho→Chi, fra→Fra, deu→Ger, spa→Spa, por→Por,\n"
        "rus→Rus, ara→Ara, kor→Kor, und→Unk\n\n"
        "⚠️ **All audio/subtitle tracks are preserved — nothing is dropped.**\n"
        f"💬 {Config.CHANNEL_TAG}"
    )


# ── /tokens ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("tokens") & filters.private)
async def cmd_tokens(client: Client, message: Message):
    await message.reply_text(
        "**🔣 Format Tokens**\n\n"
        "`{title}` — parsed title (auto title-cased)\n"
        "`{SE}` — season+episode, e.g. `S01-E05`\n"
        "`{S}` — season number only, e.g. `01`\n"
        "`{E}` — episode number only, e.g. `05`\n"
        "`{quality}` — e.g. `1080p`, `720p`, `BluRay`, `WEB-DL`\n"
        "`{audio}` — e.g. `Dual Audio`, `Hindi`, `Subbed`\n"
        "`{ext}` — file extension (with dot), e.g. `.mkv`\n\n"
        "Empty `[]` / `()` groups are removed automatically.\n\n"
        f"Default: `{Config.DEFAULT_FORMAT}`\n"
        f"💬 {Config.CHANNEL_TAG}"
    )


# ── /format ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("format") & filters.private)
async def cmd_format(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    thumb_status = (
        f"✅ Set (`{os.path.basename(state.thumbnail)}`)"
        if state.thumbnail and os.path.isfile(state.thumbnail)
        else "❌ Not set"
    )
    await message.reply_text(
        f"**⚙️ Current Settings**\n\n"
        f"**Format:** `{state.fmt}`\n"
        f"**Thumbnail:** {thumb_status}\n\n"
        f"Use `/setformat <template>` to change.\n"
        f"Use `/resetformat` to restore default.\n"
        f"💬 {Config.CHANNEL_TAG}"
    )


# ── /setformat ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("setformat") & filters.private)
async def cmd_setformat(client: Client, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply_text(
            "Usage: `/setformat <template>`\n\n"
            f"Example: `{Config.DEFAULT_FORMAT}`\n"
            "See /tokens for available placeholders."
        )
        return

    template = parts[1].strip()
    # Must contain at least one of the required tokens
    if not any(t in template for t in ("{title}", "{SE}", "{E}", "{S}")):
        await message.reply_text(
            "❌ Format must include at least one of: `{title}`, `{SE}`, `{S}`, `{E}`"
        )
        return

    state_manager.set_format(message.chat.id, template)
    await message.reply_text(f"✅ Format saved:\n`{template}`")


# ── /resetformat ──────────────────────────────────────────────────────────────

@Client.on_message(filters.command("resetformat") & filters.private)
async def cmd_resetformat(client: Client, message: Message):
    state_manager.reset_format(message.chat.id)
    await message.reply_text(
        f"✅ Format reset to default:\n`{Config.DEFAULT_FORMAT}`"
    )


# ── /preview ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("preview") & filters.private)
async def cmd_preview(client: Client, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply_text(
            "Usage: `/preview <filename>`\n\n"
            "Example: `/preview Breaking.Bad.S01E05.720p.BluRay.mkv`"
        )
        return

    raw = parts[1].strip()
    state = state_manager.get(message.chat.id)
    pf = parse_filename(raw)
    out = build_output_name(pf, state.fmt)

    await message.reply_text(
        f"**🔍 Preview**\n\n"
        f"**Input:** `{raw}`\n\n"
        f"**Parsed:**\n"
        f"• Title: `{pf.title or '—'}`\n"
        f"• SE: `{pf.SE or '—'}`\n"
        f"• Quality: `{pf.quality or '—'}`\n"
        f"• Audio: `{pf.audio or '—'}`\n"
        f"• Extension: `{pf.ext or '—'}`\n\n"
        f"**Output:** `{out}`"
    )


# ── /examples ─────────────────────────────────────────────────────────────────

_SAMPLE_FILES = [
    "Breaking.Bad.S01E05.720p.BluRay.x264-GROUP.mkv",
    "Avengers.Endgame.2019.1080p.WEB-DL.Dual.Audio.Hindi.English.mkv",
    "Demon.Slayer.S03E12.1080p.WEBRip.x265.Subbed.mkv",
    "The.Dark.Knight.2008.4K.BluRay.Hindi.Dubbed.mkv",
    "Attack.on.Titan.Final.Season.S04E28.720p.HDRip.Multi.Audio.mkv",
]


@Client.on_message(filters.command("examples") & filters.private)
async def cmd_examples(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    lines = [f"**📋 Sample Renames** (format: `{state.fmt}`)\n"]
    for raw in _SAMPLE_FILES:
        pf = parse_filename(raw)
        out = build_output_name(pf, state.fmt)
        lines.append(f"**→** `{raw}`\n   `{out}`\n")
    await message.reply_text("\n".join(lines))


# ── /thumbnail ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("thumbnail") & filters.private)
async def cmd_thumbnail(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    state.awaiting_thumbnail = True
    await message.reply_text(
        "📸 **Send me a photo** to use as the thumbnail for all future files.\n"
        "It will be embedded into MKV/WebM and sent as Telegram document thumb."
    )


# ── /clearthumbnail ───────────────────────────────────────────────────────────

@Client.on_message(filters.command("clearthumbnail") & filters.private)
async def cmd_clearthumbnail(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    if state.thumbnail and os.path.isfile(state.thumbnail):
        os.remove(state.thumbnail)
    state_manager.clear_thumbnail(message.chat.id)
    await message.reply_text("🗑 Thumbnail removed.")


# ── /rename ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("rename") & filters.private)
async def cmd_rename(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    state.awaiting_rename = True
    await message.reply_text(
        "✏️ **Type the exact filename** (with extension) you want for the next file.\n\n"
        "Example: `My Movie [1080p] [@StraWchatOfficial].mkv`"
    )
