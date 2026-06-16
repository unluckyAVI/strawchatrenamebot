"""
Command handlers — upgraded UI edition.
"""

from __future__ import annotations
import os

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from parser import parse_filename, build_output_name
from state import state_manager

# ── /start ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message):
    await message.reply_text(
        "╔═══════════════════════════╗\n"
        "║   📁 StraWchat Rename Bot  ║\n"
        "╚═══════════════════════════╝\n\n"
        "👋 **Welcome!**\n\n"
        "Send me any **video / audio / document** and I'll:\n\n"
        "  ✦ Auto-parse the filename\n"
        "  ✦ Rename using your template\n"
        "  ✦ Embed channel metadata (no re-encode)\n"
        "  ✦ Send back as clean document\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📖 Commands: /help\n"
        "⚙️ Format: /format\n"
        "🔍 Preview: /preview <filename>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 Channel: **{Config.CHANNEL_TAG}**"
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("help") & filters.private)
async def cmd_help(client: Client, message: Message):
    await message.reply_text(
        "╔═══════════════════════════╗\n"
        "║        📖 Help Guide       ║\n"
        "╚═══════════════════════════╝\n\n"
        "**🔧 Basic Usage**\n"
        "Just send any file → bot renames + embeds metadata → sends back!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "**📋 Commands**\n\n"
        "**Info**\n"
        "  `/start` — Welcome message\n"
        "  `/help` — This guide\n"
        "  `/metadata` — What gets embedded\n"
        "  `/tokens` — Format token list\n\n"
        "**Format**\n"
        "  `/format` — Current settings\n"
        "  `/setformat <template>` — Custom format\n"
        "  `/resetformat` — Back to default\n\n"
        "**Preview & Test**\n"
        "  `/preview <filename>` — Dry-run rename\n"
        "  `/examples` — 5 sample renames\n\n"
        "**Thumbnail**\n"
        "  `/thumbnail` — Set custom thumbnail\n"
        "  `/clearthumbnail` — Remove thumbnail\n\n"
        "**Custom Name**\n"
        "  `/rename` — Set exact name for next file\n\n"
        "**Metadata**\n"
        "  `/setmeta <field> <value>` — Customize metadata\n"
        "  `/resetmeta` — Reset metadata to default\n"
        "  `/metadata` — View current metadata\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 **{Config.CHANNEL_TAG}**"
    )


# ── /metadata ─────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("metadata") & filters.private)
async def cmd_metadata(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    meta = state.custom_meta

    title = meta.get("title", Config.METADATA_TITLE)
    author = meta.get("author", Config.METADATA_AUTHOR)
    encoder = meta.get("encoder", Config.METADATA_ENCODER)
    copyright_ = meta.get("copyright", Config.METADATA_COPYRIGHT)

    await message.reply_text(
        "╔═══════════════════════════╗\n"
        "║     🏷 Embedded Metadata   ║\n"
        "╚═══════════════════════════╝\n\n"
        "**🌐 Global (File-level)**\n"
        f"  `title` → `{title}`\n"
        f"  `author` → `{author}`\n"
        f"  `encoder` → `{encoder}`\n"
        f"  `copyright` → `{copyright_}`\n\n"
        "**🎬 Per-stream**\n"
        "  Video → `Encoded By :- Team @StraWchatOfficial`\n"
        "  Audio → `<Lang> tg:- [@StraWchatOfficial]`\n"
        "  Subs  → `<Lang> tg:- [@StraWchatOfficial]`\n\n"
        "**📝 Customize**\n"
        "  `/setmeta title My Channel` — change title\n"
        "  `/setmeta author My Name` — change author\n"
        "  `/setmeta encoder My Encoder` — change encoder\n"
        "  `/resetmeta` — reset all to default\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ All audio/subtitle tracks are **preserved**\n"
        f"💬 **{Config.CHANNEL_TAG}**"
    )


# ── /setmeta ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("setmeta") & filters.private)
async def cmd_setmeta(client: Client, message: Message):
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.reply_text(
            "**Usage:** `/setmeta <field> <value>`\n\n"
            "**Available fields:**\n"
            "  `title` — file title metadata\n"
            "  `author` — author/artist field\n"
            "  `encoder` — encoder/encoded_by field\n"
            "  `copyright` — copyright field\n\n"
            "**Example:**\n"
            "  `/setmeta title My Awesome Channel`\n"
            "  `/setmeta author John Doe`"
        )
        return

    field = parts[1].lower().strip()
    value = parts[2].strip()

    allowed = {"title", "author", "encoder", "copyright"}
    if field not in allowed:
        await message.reply_text(
            f"❌ Unknown field `{field}`\n\n"
            f"Allowed: `title`, `author`, `encoder`, `copyright`"
        )
        return

    state = state_manager.get(message.chat.id)
    state.custom_meta[field] = value
    state_manager._save(message.chat.id)

    await message.reply_text(
        f"✅ **Metadata updated!**\n\n"
        f"`{field}` → `{value}`"
    )


# ── /resetmeta ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("resetmeta") & filters.private)
async def cmd_resetmeta(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    state.custom_meta = {}
    state_manager._save(message.chat.id)
    await message.reply_text("✅ Metadata reset to default channel values!")


# ── /tokens ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("tokens") & filters.private)
async def cmd_tokens(client: Client, message: Message):
    await message.reply_text(
        "╔═══════════════════════════╗\n"
        "║      🔣 Format Tokens      ║\n"
        "╚═══════════════════════════╝\n\n"
        "| Token | Example |\n"
        "|-------|---------|\n"
        "| `{title}` | `Breaking Bad` |\n"
        "| `{SE}` | `S01-E05` |\n"
        "| `{S}` | `01` |\n"
        "| `{E}` | `05` |\n"
        "| `{quality}` | `1080p` / `BluRay` |\n"
        "| `{audio}` | `Dual Audio` / `Hindi` |\n"
        "| `{ext}` | `.mkv` |\n\n"
        "💡 Empty `[]` groups are auto-removed\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Default:**\n`{Config.DEFAULT_FORMAT}`\n\n"
        f"💬 **{Config.CHANNEL_TAG}**"
    )


# ── /format ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("format") & filters.private)
async def cmd_format(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    thumb_status = (
        f"✅ Set"
        if state.thumbnail and os.path.isfile(state.thumbnail)
        else "❌ Not set"
    )
    meta = state.custom_meta
    meta_status = "✅ Custom" if meta else "📋 Default"

    await message.reply_text(
        "╔═══════════════════════════╗\n"
        "║      ⚙️ Current Settings   ║\n"
        "╚═══════════════════════════╝\n\n"
        f"**📝 Format:**\n`{state.fmt}`\n\n"
        f"**🖼 Thumbnail:** {thumb_status}\n"
        f"**🏷 Metadata:** {meta_status}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  `/setformat <template>` — change format\n"
        "  `/resetformat` — restore default\n"
        "  `/tokens` — available tokens\n"
        f"💬 **{Config.CHANNEL_TAG}**"
    )


# ── /setformat ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("setformat") & filters.private)
async def cmd_setformat(client: Client, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply_text(
            "**Usage:** `/setformat <template>`\n\n"
            f"**Example:**\n`{Config.DEFAULT_FORMAT}`\n\n"
            "See /tokens for placeholders."
        )
        return

    template = parts[1].strip()
    if not any(t in template for t in ("{title}", "{SE}", "{E}", "{S}")):
        await message.reply_text(
            "❌ Format must include at least one of:\n"
            "`{title}`, `{SE}`, `{S}`, `{E}`"
        )
        return

    state_manager.set_format(message.chat.id, template)
    await message.reply_text(
        f"✅ **Format saved!**\n\n`{template}`"
    )


# ── /resetformat ──────────────────────────────────────────────────────────────

@Client.on_message(filters.command("resetformat") & filters.private)
async def cmd_resetformat(client: Client, message: Message):
    state_manager.reset_format(message.chat.id)
    await message.reply_text(
        f"✅ **Format reset to default:**\n\n`{Config.DEFAULT_FORMAT}`"
    )


# ── /preview ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("preview") & filters.private)
async def cmd_preview(client: Client, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply_text(
            "**Usage:** `/preview <filename>`\n\n"
            "**Example:**\n"
            "`/preview Breaking.Bad.S01E05.720p.BluRay.mkv`"
        )
        return

    raw = parts[1].strip()
    state = state_manager.get(message.chat.id)
    pf = parse_filename(raw)
    out = build_output_name(pf, state.fmt)

    await message.reply_text(
        "╔═══════════════════════════╗\n"
        "║       🔍 Rename Preview    ║\n"
        "╚═══════════════════════════╝\n\n"
        f"**📥 Input:**\n`{raw}`\n\n"
        "**🔎 Parsed:**\n"
        f"  Title   : `{pf.title or '—'}`\n"
        f"  SE      : `{pf.SE or '—'}`\n"
        f"  Quality : `{pf.quality or '—'}`\n"
        f"  Audio   : `{pf.audio or '—'}`\n"
        f"  Ext     : `{pf.ext or '—'}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**📤 Output:**\n`{out}`"
    )


# ── /examples ─────────────────────────────────────────────────────────────────

_SAMPLE_FILES = [
    "Breaking.Bad.S01E05.720p.BluRay.x264-GROUP.mkv",
    "Avengers.Endgame.2019.1080p.WEB-DL.Dual.Audio.mkv",
    "Demon.Slayer.S03E12.1080p.WEBRip.x265.Subbed.mkv",
    "[S02] [02] Tokyo Revengers [720p] [Dual] @Anime_Web_36.mkv",
    "176 - Naruto [480p] [Dual].mkv",
]


@Client.on_message(filters.command("examples") & filters.private)
async def cmd_examples(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    lines = [
        "╔═══════════════════════════╗\n"
        "║      📋 Sample Renames     ║\n"
        "╚═══════════════════════════╝\n\n"
        f"**Format:** `{state.fmt}`\n\n"
    ]
    for i, raw in enumerate(_SAMPLE_FILES, 1):
        pf = parse_filename(raw)
        out = build_output_name(pf, state.fmt)
        lines.append(f"**{i}.** `{raw}`\n    ➜ `{out}`\n")

    await message.reply_text("\n".join(lines))


# ── /thumbnail ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("thumbnail") & filters.private)
async def cmd_thumbnail(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    state.awaiting_thumbnail = True
    await message.reply_text(
        "🖼 **Set Thumbnail**\n\n"
        "Send me a **photo** to use as thumbnail for all future files.\n\n"
        "  ✦ Embedded into MKV/WebM files\n"
        "  ✦ Shown as Telegram doc preview\n"
        "  ✦ Auto-extracted if not set\n\n"
        "📸 Send your photo now!"
    )


# ── /clearthumbnail ───────────────────────────────────────────────────────────

@Client.on_message(filters.command("clearthumbnail") & filters.private)
async def cmd_clearthumbnail(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    if state.thumbnail and os.path.isfile(state.thumbnail):
        os.remove(state.thumbnail)
    state_manager.clear_thumbnail(message.chat.id)
    await message.reply_text("🗑 **Thumbnail removed.**\nBot will auto-extract frames from videos.")


# ── /rename ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("rename") & filters.private)
async def cmd_rename(client: Client, message: Message):
    state = state_manager.get(message.chat.id)
    state.awaiting_rename = True
    await message.reply_text(
        "✏️ **Custom Rename**\n\n"
        "Type the **exact filename** (with extension) for the next file:\n\n"
        "**Example:**\n"
        "`My Movie [1080p] [@StraWchatOfficial].mkv`\n\n"
        "⚠️ This overrides the format template for one file only."
    )
