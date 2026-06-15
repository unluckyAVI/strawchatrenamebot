"""
Filename parser.
Extracts: title, season, episode, quality, audio type from a raw filename.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Regex patterns ────────────────────────────────────────────────────────────

# Season + Episode:  S01E05 / S01-E05 / S1E5 / 1x05 / Season 1 Episode 5
_RE_SE = re.compile(
    r"""
    (?:
        [Ss](\d{1,2})[.\-_ ]*[Ee](\d{1,3})   # S01E05 or S01-E05
      | [Ss](\d{1,2})[.\- ]+[Ee][Pp]?(\d{1,3}) # S01 Ep05
      | (\d{1,2})[xX](\d{1,3})                 # 1x05
      | [Ss]eason[\s._-]*(\d{1,2})[\s._-]+[Ee]pisode[\s._-]*(\d{1,3})  # Season 1 Episode 5
    )
    """,
    re.VERBOSE,
)

# Episode only (no season):  E05 / Ep05 / Episode 5
# Excludes quality resolutions: 1080p/720p are already caught by quality regex
_RE_EP_ONLY = re.compile(
    r"(?<![x\d])(?:[Ee][Pp]?|[Ee]pisode[\s._]*)(\d{1,3})(?![\dp])"
)

# Quality
_RE_QUALITY = re.compile(
    r"\b(4K|2160p|1080p|720p|480p|360p|HDRip|BRRip|BluRay|Blu-Ray|WEB-DL|WEBRip|"
    r"WEB|HDTV|DVDRip|DVDScr|CAMRip|CAM|HC|HDRIP|HQ|SD|HD)\b",
    re.IGNORECASE,
)

# Audio
_RE_AUDIO = re.compile(
    r"\b(Dual[\s.+]?Audio|Multi[\s.+]?Audio|Hindi|Tamil|Telugu|Malayalam|English|"
    r"Japanese|Korean|Chinese|French|German|Spanish|Portuguese|Russian|Arabic|"
    r"ORG|Original|Dubbed|Subbed|HIN|ENG|TAM|TEL|MAL|JPN)\b",
    re.IGNORECASE,
)

# Tokens to strip when building clean title
_STRIP_TOKENS = re.compile(
    r"""
    (?:
      \[.*?\]|\(.*?\)                         # anything in brackets
      |-[A-Z][A-Z0-9]{1,10}(?=\b|\Z)          # release group suffix e.g. -GROUP
      |\b(?:
        4K|2160p|1080p|720p|480p|360p
        |HDRip|BRRip|BluRay|Blu-Ray|WEB-DL|WEBRip|WEB|HDTV
        |DVDRip|DVDScr|CAMRip|CAM|HC|HQ|SD|HD
        |Dual[\s.+]?Audio|Multi[\s.+]?Audio
        |Hindi|Tamil|Telugu|Malayalam|English|Japanese|Korean|Chinese
        |French|German|Spanish|Portuguese|Russian|Arabic
        |ORG|Original|Dubbed|Subbed
        |HIN|ENG|TAM|TEL|MAL|JPN
        |x264|x265|H\.264|H\.265|HEVC|AVC
        |AAC|AC3|DTS|DD5?\.1|DD2\.0|MP3|FLAC
        |10bit|8bit|HDR|SDR|DV|Atmos
        |YIFY|YTSAM|ETTV|YTS|RARBG|EVO|FGT|CM|NTb
      )\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Common separators → space
_RE_SEP = re.compile(r"[._\-]+")

# Extension
_RE_EXT = re.compile(r"\.[a-zA-Z0-9]{2,5}$")


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

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def SE(self) -> str:
        """Return formatted SE token, e.g. S01-E05.  Empty if no episode."""
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
    """
    Parse a filename and return a ParsedFile with extracted metadata.

    Steps:
    1. Strip extension
    2. Extract quality
    3. Extract audio
    4. Extract S/E
    5. Build clean title from what remains
    """
    pf = ParsedFile(raw_name=raw)

    # 1. Extension
    m = _RE_EXT.search(raw)
    if m:
        pf.ext = m.group(0)          # e.g. ".mkv"
        name = raw[: m.start()]
    else:
        name = raw

    # 2. Quality (first match wins)
    mq = _RE_QUALITY.search(name)
    if mq:
        pf.quality = mq.group(0)

    # 3. Audio (first match wins — could normalise later)
    ma = _RE_AUDIO.search(name)
    if ma:
        raw_audio = ma.group(0)
        pf.audio = _normalise_audio(raw_audio)

    # 4. Season / Episode
    mse = _RE_SE.search(name)
    if mse:
        groups = mse.groups()
        # Pattern groups: (S,E), (S,EP), (1x,05), (Season,Episode)
        # We fill the first non-None pair
        if groups[0] and groups[1]:
            pf.season, pf.episode = int(groups[0]), int(groups[1])
        elif groups[2] and groups[3]:
            pf.season, pf.episode = int(groups[2]), int(groups[3])
        elif groups[4] and groups[5]:
            pf.season, pf.episode = int(groups[4]), int(groups[5])
        elif groups[6] and groups[7]:
            pf.season, pf.episode = int(groups[6]), int(groups[7])

        # Remove the SE token from the name before title extraction
        name = name[: mse.start()] + " " + name[mse.end():]
    else:
        mep = _RE_EP_ONLY.search(name)
        if mep:
            pf.episode = int(mep.group(1))
            name = name[: mep.start()] + " " + name[mep.end():]

    # 5. Clean title
    title = _STRIP_TOKENS.sub(" ", name)
    title = _RE_SEP.sub(" ", title)
    title = re.sub(r"\s{2,}", " ", title).strip()
    # Title-case it
    pf.title = _smart_title(title)

    return pf


def _normalise_audio(raw: str) -> str:
    """Normalise audio labels."""
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
        "dubbed": "Dubbed",
        "subbed": "Subbed",
        "original": "Original",
        "org": "Original",
    }
    return mapping.get(lc, raw.strip())


# Small words not capitalised in title case (unless first/last)
_SMALL_WORDS = {"a", "an", "the", "and", "but", "or", "nor", "for", "so",
                "yet", "at", "by", "in", "of", "on", "to", "up", "as", "is",
                "it", "vs", "via"}


def _smart_title(s: str) -> str:
    """Title-case with small-word handling."""
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
    """
    Render a format template with ParsedFile tokens.
    Removes empty bracket groups like [] or ().
    """
    tokens = pf.tokens
    result = template

    # Replace {token} placeholders
    for key, val in tokens.items():
        result = result.replace(f"{{{key}}}", val)

    # Remove empty bracket groups: [], (), {}
    result = re.sub(r"\[\s*\]|\(\s*\)|\{\s*\}", "", result)

    # Collapse multiple spaces
    result = re.sub(r"\s{2,}", " ", result).strip()
    result = re.sub(r"\s+([^\w])", r"\1", result)  # space before punctuation

    return result


def build_output_name(pf: ParsedFile, template: str) -> str:
    """Return the full output filename including extension."""
    stem = apply_format(template, pf)
    # Sanitise for filesystem
    stem = re.sub(r'[<>:"/\\|?*]', "", stem)
    return stem + pf.ext
