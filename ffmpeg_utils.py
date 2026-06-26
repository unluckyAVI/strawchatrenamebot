"""
FFmpeg / FFprobe helpers.
Supports custom per-user metadata via the meta_overrides dict.
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

_LANG_MAP: dict[str, str] = {
    "eng": "Eng", "hin": "Hin", "tam": "Tam", "tel": "Tel",
    "mal": "Mal", "jpn": "Jpn", "chi": "Chi", "zho": "Chi",
    "fra": "Fra", "deu": "Ger", "spa": "Spa", "por": "Por",
    "rus": "Rus", "ara": "Ara", "kor": "Kor", "und": "Unk",
}

_FFMPEG  = shutil.which("ffmpeg")  or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"


async def _run(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def probe_streams(path: str) -> list[dict]:
    code, out, err = await _run(
        _FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams", path,
    )
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err.strip()}")
    return json.loads(out).get("streams", [])


def _lang_label(tags: dict) -> str:
    lang = tags.get("language", "und").lower()
    return _LANG_MAP.get(lang, lang.capitalize())


async def embed_metadata(
    input_path: str,
    output_path: str,
    thumbnail_path: Optional[str] = None,
    meta_overrides: Optional[dict] = None,
) -> None:
    """
    Copy-encode with full metadata embedding.
    meta_overrides: dict with keys title/author/encoder/copyright to override defaults.
    """
    streams = await probe_streams(input_path)
    ext = Path(output_path).suffix.lower()
    is_mkv_webm = ext in (".mkv", ".webm")

    cmd = [_FFMPEG, "-y", "-i", input_path]

    if thumbnail_path and is_mkv_webm and os.path.isfile(thumbnail_path):
        cmd += ["-attach", thumbnail_path, "-metadata:s:t", "mimetype=image/jpeg"]

    # Resolve metadata values (custom overrides default)
    overrides = meta_overrides or {}
    meta_title     = overrides.get("title",     Config.METADATA_TITLE)
    meta_author    = overrides.get("author",    Config.METADATA_AUTHOR)
    meta_encoder   = overrides.get("encoder",   Config.METADATA_ENCODER)
    meta_copyright = overrides.get("copyright", Config.METADATA_COPYRIGHT)

    global_meta = {
        "title":      meta_title,
        "author":     meta_author,
        "artist":     meta_author,
        "comment":    meta_author,
        "encoded_by": meta_encoder,
        "encoder":    meta_encoder,
        "copyright":  meta_copyright,
        "PURL":       Config.METADATA_PURL,
    }
    for k, v in global_meta.items():
        cmd += ["-metadata", f"{k}={v}"]

    cmd += ["-c", "copy", "-ignore_unknown"]

    video_idx = audio_idx = sub_idx = 0
    for stream in streams:
        stype = stream.get("codec_type", "")
        tags  = stream.get("tags", {})

        if stype == "video":
            cmd += [f"-metadata:s:v:{video_idx}",
                    f"title=Encoded By :- Team {Config.CHANNEL_TAG}"]
            video_idx += 1
        elif stype == "audio":
            label = _lang_label(tags)
            cmd += [f"-metadata:s:a:{audio_idx}",
                    f"title={label} tg:- [{Config.CHANNEL_TAG}]"]
            audio_idx += 1
        elif stype == "subtitle":
            label = _lang_label(tags)
            cmd += [f"-metadata:s:s:{sub_idx}",
                    f"title={label} tg:- [{Config.CHANNEL_TAG}]"]
            sub_idx += 1

    cmd += ["-map", "0", "-ignore_unknown"]
    cmd.append(output_path)

    code, out, err = await _run(*cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg failed (code {code}):\n{err[-2000:]}")


async def extract_thumbnail(input_path: str, out_path: str) -> bool:
    code, _, _ = await _run(
        _FFMPEG, "-y",
        "-i", input_path,
        "-ss", "00:00:05",
        "-vframes", "1",
        "-vf", "scale=320:-1",
        out_path,
    )
    return code == 0 and os.path.isfile(out_path)
