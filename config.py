"""
Configuration — reads from environment variables.
Set these before running:
  TELEGRAM_API_ID
  TELEGRAM_API_HASH
  TELEGRAM_BOT_TOKEN
  MONGO_URI
"""

import os
import sys


class Config:
    API_ID: int = int(os.environ.get("TELEGRAM_API_ID", 0))
    API_HASH: str = os.environ.get("TELEGRAM_API_HASH", "")
    BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    MONGO_URI: str = os.environ.get("MONGO_URI", "") or os.environ.get("MONGO", "")

    # Branding
    CHANNEL_TAG: str = "@StraWchatOfficial"
    METADATA_TITLE: str = "@StraWchatOfficial on Telegram"
    METADATA_AUTHOR: str = "Tg :- [@StraWchatOfficial]"
    METADATA_ENCODER: str = "Team @StraWchatOfficial"
    METADATA_COPYRIGHT: str = "Team @StraWchatOfficial"
    METADATA_PURL: str = "Tg :- [@StraWchatOfficial]"

    # Default rename format
    DEFAULT_FORMAT: str = "{title} [{SE}] [{quality}] [{audio}] [@StraWchatOfficial]"

    # Working dirs
    DOWNLOAD_DIR: str = os.environ.get("DOWNLOAD_DIR", "/tmp/straWchat/downloads")
    OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "/tmp/straWchat/output")
    THUMB_DIR: str = os.environ.get("THUMB_DIR", "/tmp/straWchat/thumbs")

    @classmethod
    def validate(cls):
        errors = []
        if not cls.API_ID:
            errors.append("TELEGRAM_API_ID is not set or invalid")
        if not cls.API_HASH:
            errors.append("TELEGRAM_API_HASH is not set")
        if not cls.BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is not set")
        if errors:
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            sys.exit(1)


# Validate on import
Config.validate()

# Create working directories
for _d in [Config.DOWNLOAD_DIR, Config.OUTPUT_DIR, Config.THUMB_DIR]:
    os.makedirs(_d, exist_ok=True)
