"""
FFmpeg / FFprobe helpers.

- probe_streams()  → list all streams with codec_type + tags
- embed_metadata() → copy-encode with full global + per-stream metadata
- attach_thumbnail() → attach cover art into MKV/WebM
"""

from __future__ import annotations
import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Optional
import static_ffmpeg
static_ffmpeg.add_paths()
from config import Config

# Language code → friendly label used in stream metadata
_LANG_MAP: dict[str, str] = {
    "eng": "Eng", "hin": "Hin", "tam": "Tam", "tel": "Tel",
    "mal": "Mal", "jpn": "Jpn", "chi": "Chi", "zho": "Chi",
    "fra": "Fra", "deu": "Ger", "spa": "Spa", "por": "Por",
    "rus": "Rus", "ara": "Ara", "kor": "Kor", "und": "Unk",
}

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"


# ── Run helper ────────────────────────────────────────────────────────────────

async def _run(*args: str) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


# ── FFprobe ───────────────────────────────────────────────────────────────────

async def probe_streams(path: str) -> list[dict]:
    """
    Return list of stream dicts from ffprobe.
    Each dict has at minimum: index, codec_type, tags (dict).
    """
    code, out, err = await _run(
        _FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        path,
    )
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err.strip()}")
    data = json.loads(out)
    return data.get("streams", [])


def _lang_label(tags: dict) -> str:
    lang = tags.get("language", "und").lower()
    return _LANG_MAP.get(lang, lang.capitalize())


# ── FFmpeg metadata embed ─────────────────────────────────────────────────────

async def embed_metadata(
    input_path: str,
    output_path: str,
    thumbnail_path: Optional[str] = None,
) -> None:
    """
    Copy-encode the file and embed:
      - Global metadata (title, author, encoder, copyright, PURL …)
      - Per-stream metadata for video, audio, subtitle streams
      - Optional thumbnail attachment for MKV/WebM
    Never re-encodes — uses -c copy throughout.
    """
    streams = await probe_streams(input_path)
    ext = Path(output_path).suffix.lower()
    is_mkv_webm = ext in (".mkv", ".webm")

    cmd = [_FFMPEG, "-y", "-i", input_path]

    # Optional thumbnail input for MKV
    if thumbnail_path and is_mkv_webm and os.path.isfile(thumbnail_path):
        cmd += ["-attach", thumbnail_path,
                "-metadata:s:t", "mimetype=image/jpeg"]

    # ── Global metadata ───────────────────────────────────────────────────────
    global_meta = {
        "title": Config.METADATA_TITLE,
        "author": Config.METADATA_AUTHOR,
        "artist": Config.METADATA_AUTHOR,
        "comment": Config.METADATA_AUTHOR,
        "encoded_by": Config.METADATA_ENCODER,
        "encoder": Config.METADATA_ENCODER,
        "copyright": Config.METADATA_COPYRIGHT,
        "PURL": Config.METADATA_PURL,
    }
    for k, v in global_meta.items():
        cmd += ["-metadata", f"{k}={v}"]

    # ── Stream copy + per-stream metadata ─────────────────────────────────────
    cmd += ["-c", "copy"]

    video_idx = audio_idx = sub_idx = 0
    for stream in streams:
        stype = stream.get("codec_type", "")
        tags = stream.get("tags", {})
        si = stream.get("index", 0)

        if stype == "video":
            cmd += [
                f"-metadata:s:v:{video_idx}",
                f"title=Encoded By :- Team {Config.CHANNEL_TAG}",
            ]
            video_idx += 1

        elif stype == "audio":
            label = _lang_label(tags)
            cmd += [
                f"-metadata:s:a:{audio_idx}",
                f"title={label} tg:- [{Config.CHANNEL_TAG}]",
            ]
            audio_idx += 1

        elif stype == "subtitle":
            label = _lang_label(tags)
            cmd += [
                f"-metadata:s:s:{sub_idx}",
                f"title={label} tg:- [{Config.CHANNEL_TAG}]",
            ]
            sub_idx += 1

    # Map ALL streams explicitly so nothing is dropped
    cmd += ["-map", "0"]

    cmd.append(output_path)

    code, out, err = await _run(*cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg failed (code {code}):\n{err[-2000:]}")


# ── Thumbnail probe ───────────────────────────────────────────────────────────

async def extract_thumbnail(input_path: str, out_path: str) -> bool:
    """
    Try to extract the first video frame as a JPEG thumbnail.
    Returns True on success.
    """
    code, _, err = await _run(
        _FFMPEG, "-y",
        "-i", input_path,
        "-ss", "00:00:05",
        "-vframes", "1",
        "-vf", "scale=320:-1",
        out_path,
    )
    return code == 0 and os.path.isfile(out_path)
