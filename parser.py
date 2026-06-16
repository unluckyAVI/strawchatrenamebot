"""
Filename parser — advanced edition.
Extracts: title, season, episode, quality, audio type from a raw filename.
Handles many real-world naming conventions used by anime/movie release groups.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


# ── Regex patterns ────────────────────────────────────────────────────────────

# Season + Episode — ordered from most specific to least
_SE_PATTERNS = [
    # S01E05 / S01-E05 / S1E5
    (re.compile(r'[Ss](\d{1,2})[.\-_ ]*[Ee](\d{1,3})'), True),
    # S01 Ep05 / S01 EP05
    (re.compile(r'[Ss](\d{1,2})[.\- ]+[Ee][Pp]?(\d{1,3})'), True),
    # Season 1 Episode 5
    (re.compile(r'[Ss]eason[\s._-]*(\d{1,2})[\s._-]+[Ee]p(?:isode)?[\s._-]*(\d{1,3})'), True),
    # [S02] [02] or [S02][02]
    (re.compile(r'\[S(\d{1,2})\]\s*\[0*(\d{1,3})\]'), True),
    # [S02E05]
    (re.compile(r'\[S(\d{1,2})E(\d{1,3})\]'), True),
    # 1x05
    (re.compile(r'(\d{1,2})[xX](\d{1,3})'), True),
    # S01 - E05 (with spaces around dash)
    (re.compile(r'[Ss](\d{1,2})\s*-\s*[Ee](\d{1,3})'), True),
    # - 176 - (episode number surrounded by dashes/spaces — anime style)
    (re.compile(r'(?:^|[\s\-_])[Ee]?(\d{3})[\s\-_]'), False),  # 3-digit ep, no season
]

# Episode only patterns (no season)
_EP_ONLY_PATTERNS = [
    # E05 / Ep05 / EP05
    re.compile(r'(?<![x\d\-])[Ee][Pp]?(\d{1,3})(?![\dp])'),
    # Episode 5
    re.compile(r'[Ee]pisode[\s._]*(\d{1,3})'),
    # " - 176 " or "- 176 -" style (anime absolute episode)
    re.compile(r'(?:^|[\s_])-\s*(\d{1,4})\s*(?:-|$|\[)'),
    # Leading number "176 - Title" or "176. Title"
    re.compile(r'^(\d{1,4})[\s]*[-\.]\s*[A-Za-z]'),
]

# Quality
_RE_QUALITY = re.compile(
    r'\b(4K|2160p|1080p|720p|480p|360p|HDRip|BRRip|BluRay|Blu-Ray|'
    r'WEB-DL|WEBRip|WEB|HDTV|DVDRip|DVDScr|CAMRip|CAM|HC|HDRIP|HQ|SD|HD)\b',
    re.IGNORECASE,
)

# Audio
_RE_AUDIO = re.compile(
    r'\b(Dual[\s.+]?Audio|Multi[\s.+]?Audio|Dual|Multi|'
    r'Hindi|Tamil|Telugu|Malayalam|English|Japanese|Korean|Chinese|'
    r'French|German|Spanish|Portuguese|Russian|Arabic|'
    r'ORG|Original|Dubbed|Subbed|HIN|ENG|TAM|TEL|MAL|JPN)\b',
    re.IGNORECASE,
)

# Tokens to strip when building clean title
_STRIP_TOKENS = re.compile(
    r"""
    (?:
      \[.*?\]|\(.*?\)                             # anything in brackets/parens
      |-[A-Z][A-Z0-9]{1,10}(?=\b|\Z)             # release group e.g. -GROUP
      |@\S+                                       # @username tags
      |\b(?:
        4K|2160p|1080p|720p|480p|360p
        |HDRip|BRRip|BluRay|Blu-Ray|WEB-DL|WEBRip|WEB|HDTV
        |DVDRip|DVDScr|CAMRip|CAM|HC|HQ|SD|HD
        |Dual[\s.+]?Audio|Multi[\s.+]?Audio|Dual|Multi
        |Hindi|Tamil|Telugu|Malayalam|English|Japanese|Korean|Chinese
        |French|German|Spanish|Portuguese|Russian|Arabic
        |ORG|Original|Dubbed|Subbed
        |HIN|ENG|TAM|TEL|MAL|JPN
        |x264|x265|H\.264|H\.265|HEVC|AVC
        |AAC|AC3|DTS|DD5?\.1|DD2\.0|MP3|FLAC
        |10bit|8bit|HDR|SDR|DV|Atmos
        |YIFY|YTSAM|ETTV|YTS|RARBG|EVO|FGT|CM|NTb
        |\d{4}(?=\s|$|[\._\-])                   # year like 2019
      )\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Common separators → space
_RE_SEP = re.compile(r'[._]+')

# Extension
_RE_EXT = re.compile(r'\.[a-zA-Z0-9]{2,5}$')


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class ParsedFile:
    raw_name: str
    ext: str = ""
    title: str = ""
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: str = ""
    audio: str = ""

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


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_filename(raw: str) -> ParsedFile:
    pf = ParsedFile(raw_name=raw)

    # 1. Extension
    m = _RE_EXT.search(raw)
    if m:
        pf.ext = m.group(0)
        name = raw[: m.start()]
    else:
        name = raw

    # 2. Quality
    mq = _RE_QUALITY.search(name)
    if mq:
        pf.quality = mq.group(0)

    # 3. Audio
    ma = _RE_AUDIO.search(name)
    if ma:
        pf.audio = _normalise_audio(ma.group(0))

    # 4. Season + Episode — try each pattern in order
    se_found = False
    for pattern, has_season in _SE_PATTERNS:
        m = pattern.search(name)
        if m:
            if has_season:
                try:
                    pf.season = int(m.group(1))
                    pf.episode = int(m.group(2))
                    se_found = True
                    name = name[:m.start()] + " " + name[m.end():]
                    break
                except (IndexError, ValueError):
                    continue
            else:
                try:
                    pf.episode = int(m.group(1))
                    se_found = True
                    name = name[:m.start()] + " " + name[m.end():]
                    break
                except (IndexError, ValueError):
                    continue

    # 5. Episode only fallback
    if not se_found:
        for pattern in _EP_ONLY_PATTERNS:
            m = pattern.search(name)
            if m:
                try:
                    ep = int(m.group(1))
                    # Sanity check: skip if it looks like a year or resolution
                    if ep > 1500 or ep in (480, 720, 1080, 2160, 360):
                        continue
                    pf.episode = ep
                    name = name[:m.start()] + " " + name[m.end():]
                    break
                except (IndexError, ValueError):
                    continue

    # 6. Clean title
    title = _STRIP_TOKENS.sub(" ", name)
    title = _RE_SEP.sub(" ", title)
    # Remove leftover dashes/underscores
    title = re.sub(r'\s*-\s*', ' ', title)
    title = re.sub(r'\s{2,}', ' ', title).strip()
    pf.title = _smart_title(title)

    return pf


def _normalise_audio(raw: str) -> str:
    lc = raw.lower().replace(".", "").replace("+", "").replace(" ", "")
    if "dual" in lc:
        return "Dual Audio"
    if "multi" in lc:
        return "Multi Audio"
    mapping = {
        "hindi": "Hindi", "hin": "Hindi",
        "english": "English", "eng": "English",
        "tamil": "Tamil", "tam": "Tamil",
        "telugu": "Telugu", "tel": "Telugu",
        "malayalam": "Malayalam", "mal": "Malayalam",
        "japanese": "Japanese", "jpn": "Japanese",
        "korean": "Korean", "kor": "Korean",
        "chinese": "Chinese",
        "french": "French", "fra": "French",
        "german": "German", "deu": "German",
        "spanish": "Spanish", "spa": "Spanish",
        "portuguese": "Portuguese", "por": "Portuguese",
        "russian": "Russian", "rus": "Russian",
        "arabic": "Arabic", "ara": "Arabic",
        "dubbed": "Dubbed", "subbed": "Subbed",
        "original": "Original", "org": "Original",
    }
    return mapping.get(lc, raw.strip())


_SMALL_WORDS = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "so",
    "yet", "at", "by", "in", "of", "on", "to", "up", "as", "is",
    "it", "vs", "via",
}


def _smart_title(s: str) -> str:
    if not s:
        return s
    words = s.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or i == len(words) - 1:
            result.append(w.capitalize())
        elif w.lower() in _SMALL_WORDS:
            result.append(w.lower())
        else:
            result.append(w.capitalize())
    return " ".join(result)


# ── Format template renderer ──────────────────────────────────────────────────

def apply_format(template: str, pf: ParsedFile) -> str:
    tokens = pf.tokens
    result = template
    for key, val in tokens.items():
        result = result.replace(f"{{{key}}}", val)
    result = re.sub(r'\[\s*\]|\(\s*\)|\{\s*\}', "", result)
    result = re.sub(r'\s{2,}', " ", result).strip()
    result = re.sub(r'\s+([^\w])', r'\1', result)
    return result


def build_output_name(pf: ParsedFile, template: str) -> str:
    stem = apply_format(template, pf)
    stem = re.sub(r'[<>:"/\\|?*]', "", stem)
    return stem + pf.ext
