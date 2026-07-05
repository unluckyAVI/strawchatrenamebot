"""
Advanced AutoRename Engine for StraWchat Bot
Handles all known anime/movie/series naming conventions
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

# ── Extension ─────────────────────────────────────────────────────────────────
_RE_EXT = re.compile(r'\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v|ts|m2ts|mp3|flac|aac|opus|ogg|m4a)$', re.IGNORECASE)

# ── Quality patterns ──────────────────────────────────────────────────────────
_QUALITY_MAP = {
    r'4k|2160p': '4K',
    r'1080p': '1080p',
    r'720p': '720p',
    r'480p': '480p',
    r'360p': '360p',
    r'blu.?ray|bluray|bdrip|brrip': 'BluRay',
    r'web.?dl': 'WEB-DL',
    r'webrip|web.?rip': 'WEBRip',
    r'hdrip|hd.?rip': 'HDRip',
    r'dvdrip|dvd.?rip': 'DVDRip',
    r'hdtv': 'HDTV',
    r'camrip|cam': 'CAM',
}

# ── Audio patterns ────────────────────────────────────────────────────────────
_AUDIO_MAP = {
    r'dual.?audio|dual': 'Dual',
    r'multi.?audio|multi': 'Multi',
    r'hindi|hin': 'Hindi',
    r'english|eng': 'English',
    r'tamil|tam': 'Tamil',
    r'telugu|tel': 'Telugu',
    r'malayalam|mal': 'Malayalam',
    r'japanese|jpn': 'Japanese',
    r'korean|kor': 'Korean',
    r'chinese|chi|zho': 'Chinese',
    r'french|fra': 'French',
    r'german|deu': 'German',
    r'spanish|spa': 'Spanish',
    r'portuguese|por': 'Portuguese',
    r'russian|rus': 'Russian',
    r'arabic|ara': 'Arabic',
    r'dubbed': 'Dubbed',
    r'subbed|sub': 'Subbed',
}

# ── Junk tokens to remove from title ─────────────────────────────────────────
_JUNK = re.compile(r"""
    \b(?:
        4k|2160p|1080p|720p|480p|360p
        |blu.?ray|bluray|bdrip|brrip
        |web.?dl|webrip|web.?rip
        |hdrip|hd.?rip|dvdrip|dvd.?rip|hdtv
        |camrip|cam|hc|hq
        |x264|x265|h264|h265|hevc|avc|xvid|divx
        |aac|ac3|dts|dd5\.1|dd2\.0|mp3|flac|opus
        |10bit|8bit|hdr|sdr|dv|dolby|atmos
        |dual.?audio|multi.?audio|dual|multi
        |hindi|english|tamil|telugu|malayalam
        |japanese|korean|chinese|french|german
        |spanish|portuguese|russian|arabic
        |dubbed|subbed
        |yify|yts|rarbg|ettv|eztv|ion10|ntb|joy
        |season|complete|series|episode
        |repack|proper|extended|theatrical|unrated
        |directors.?cut|dc|se|oe
    )\b
    |\[.*?\]          # [anything]
    |\(.*?\)          # (anything)
    |@\w+             # @username
    |-[A-Z][A-Z0-9]{1,12}(?=\s|$)  # -GROUPNAME
""", re.VERBOSE | re.IGNORECASE)

# ── Season/Episode patterns ───────────────────────────────────────────────────
# Each tuple: (pattern, has_season, se_group, ep_group)
_SE_PATTERNS = [
    # S01E05, S01E05E06 (double episode)
    (re.compile(r'S(\d{1,2})E(\d{1,3})(?:[-~&]?E\d{1,3})*', re.IGNORECASE), True, 1, 2),
    # S01 - E05, S01-E05
    (re.compile(r'S(\d{1,2})\s*[-_]\s*E(\d{1,3})', re.IGNORECASE), True, 1, 2),
    # S01.E05
    (re.compile(r'S(\d{1,2})\.E(\d{1,3})', re.IGNORECASE), True, 1, 2),
    # [S5] [EP-21], [S05] [EP-21], [S5][EP21]
    (re.compile(r'\[S(\d{1,2})\]\s*\[EP?-?(\d{1,3})\]', re.IGNORECASE), True, 1, 2),
    # [S01][05], [S01] [05], [S01][E05]
    (re.compile(r'\[S(\d{1,2})\]\s*\[E?(\d{1,3})\]', re.IGNORECASE), True, 1, 2),
    # S5 EP-21, S05 EP21, S5 EP 21
    (re.compile(r'S(\d{1,2})\s+EP?-?\s*(\d{1,3})(?!\d)', re.IGNORECASE), True, 1, 2),
    # S01 EP05, S01 Ep05
    (re.compile(r'S(\d{1,2})\s+Ep?(\d{1,3})', re.IGNORECASE), True, 1, 2),
    # S02 - 01 (season dash episode WITHOUT E prefix — very common in anime)
    (re.compile(r'S(\d{1,2})\s*-\s*(\d{1,3})(?!\d)(?!\s*[Ee])'), True, 1, 2),
    # S02 01 (season space episode no separator)
    (re.compile(r'(?:^|\s)S(\d{1,2})\s+(\d{2,3})(?!\d)(?!\s*[Ee])'), True, 1, 2),
    # 1x05, 01x05
    (re.compile(r'(\d{1,2})[xX](\d{1,3})'), True, 1, 2),
    # Season 1 Episode 5
    (re.compile(r'Season\s*(\d{1,2})\s+Episode\s*(\d{1,3})', re.IGNORECASE), True, 1, 2),
    # - 176 - (anime absolute episode with dashes)
    (re.compile(r'(?:^|[\s_])-\s*(\d{1,4})\s*-(?:\s|$)'), False, None, 1),
    # " - 05 " surrounded by spaces (anime style)
    (re.compile(r'\s-\s(\d{1,3})\s'), False, None, 1),
    # E05, EP05, Ep05 standalone
    (re.compile(r'(?<![A-Za-z\d])E[Pp]?(\d{1,3})(?!\d)', re.IGNORECASE), False, None, 1),
    # Episode 05
    (re.compile(r'Episode\s*(\d{1,3})', re.IGNORECASE), False, None, 1),
    # Leading number "176 - Title" or "176. Title" (absolute episode)
    (re.compile(r'^(\d{1,4})\s*[-\.]+\s*(?=[A-Za-z])'), False, None, 1),
]

# ── Small words for title case ────────────────────────────────────────────────
_SMALL = {'a','an','the','and','but','or','nor','for','so','yet',
          'at','by','in','of','on','to','up','as','is','it','vs','via'}


@dataclass
class RenameResult:
    title: str = ""
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: str = ""
    audio: str = ""
    ext: str = ""
    raw: str = ""

    @property
    def SE(self) -> str:
        if self.season is not None and self.episode is not None:
            return f"S{self.season:02d}-E{self.episode:02d}"
        if self.episode is not None:
            return f"E{self.episode:02d}"
        return ""

    @property
    def tokens(self) -> dict:
        return {
            "title": self.title,
            "SE": self.SE,
            "S": f"{self.season:02d}" if self.season is not None else "",
            "E": f"{self.episode:02d}" if self.episode is not None else "",
            "quality": self.quality,
            "audio": self.audio,
            "ext": self.ext,
        }


def _find_quality(text: str) -> str:
    for pattern, label in _QUALITY_MAP.items():
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return ""


def _find_audio(text: str) -> str:
    # Check dual/multi first (most specific)
    for pattern, label in _AUDIO_MAP.items():
        if re.search(r'\b' + pattern + r'\b', text, re.IGNORECASE):
            return label
    return ""


def _smart_title(s: str) -> str:
    if not s:
        return s
    words = s.split()
    out = []
    for i, w in enumerate(words):
        if not w:
            continue
        if i == 0 or i == len(words) - 1 or w.lower() not in _SMALL:
            out.append(w.capitalize())
        else:
            out.append(w.lower())
    return " ".join(out)


def _clean_title(name: str) -> str:
    """Remove junk tokens and clean up the title."""
    # Remove @username first
    name = re.sub(r'@\S+', ' ', name)
    # Remove junk
    name = _JUNK.sub(' ', name)
    # Replace separators with spaces
    name = re.sub(r'[._]', ' ', name)
    # Remove leftover dashes between words
    name = re.sub(r'\s*-\s*', ' ', name)
    # Collapse spaces
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove trailing numbers (from @Anime_Web_36 etc)
    name = re.sub(r'\s+\d{1,3}$', '', name).strip()
    return name


def autorename(filename: str) -> RenameResult:
    """
    Main autorename function.
    Parses any filename and returns structured RenameResult.
    """
    result = RenameResult(raw=filename)

    # 1. Extension
    m = _RE_EXT.search(filename)
    if m:
        result.ext = '.' + m.group(1).lower()
        name = filename[:m.start()]
    else:
        name = filename

    # 2. Remove @username tags early (before quality detection)
    name_clean = re.sub(r'@\S+', ' ', name)

    # 3. Quality
    result.quality = _find_quality(name_clean)

    # 4. Audio — check inside brackets first for accuracy
    brackets = re.findall(r'\[([^\]]+)\]|\(([^)]+)\)', name_clean)
    bracket_text = ' '.join(b[0] or b[1] for b in brackets)
    result.audio = _find_audio(bracket_text) or _find_audio(name_clean)

    # 5. Season + Episode
    # Pre-process: insert space before quality/resolution glued to SE numbers
    name_proc = re.sub(
        r'(\d)(4[Kk]|2160p|1080p|720p|480p|360p)',
        r'\1 \2', name_clean, flags=re.IGNORECASE
    )
    # Insert space after quality token glued to next word
    name_proc = re.sub(
        r'(4[Kk]|2160p|1080p|720p|480p|360p)([A-Za-z])',
        r'\1 \2', name_proc, flags=re.IGNORECASE
    )
    # Normalize underscores to spaces
    name_proc = re.sub(r'_', ' ', name_proc)

    se_found = False
    se_match_span = None

    for pattern, has_season, sg, eg in _SE_PATTERNS:
        m = pattern.search(name_proc)
        if not m:
            continue
        try:
            ep_val = int(m.group(eg))
            # Sanity: skip if looks like year or resolution
            if ep_val in (480, 720, 1080, 2160, 360) or ep_val > 2000:
                continue
            if has_season and sg:
                result.season = int(m.group(sg))
            result.episode = ep_val
            se_match_span = (m.start(), m.end())
            se_found = True
            break
        except (IndexError, ValueError):
            continue

    # 6. Build clean title
    # Remove the SE match from name before cleaning
    title_src = name_proc
    if se_match_span:
        title_src = title_src[:se_match_span[0]] + ' ' + title_src[se_match_span[1]:]

    result.title = _smart_title(_clean_title(title_src))

    return result


def apply_template(template: str, result: RenameResult) -> str:
    """Apply format template with tokens from RenameResult."""
    out = template
    for key, val in result.tokens.items():
        out = out.replace(f"{{{key}}}", val)

    # Remove empty bracket groups
    out = re.sub(r'\[\s*\]|\(\s*\)', '', out)
    # Collapse spaces
    out = re.sub(r'\s{2,}', ' ', out).strip()
    # Remove trailing/leading spaces around brackets
    out = re.sub(r'\s+\[', '[', out)
    out = re.sub(r'\]\s+\[', '][', out)

    return out


def build_filename(filename: str, template: str) -> str:
    """Full pipeline: parse filename → apply template → return new filename."""
    result = autorename(filename)
    stem = apply_template(template, result)
    # Sanitise for filesystem
    stem = re.sub(r'[<>:"/\\|?*]', '', stem)
    return stem + result.ext
