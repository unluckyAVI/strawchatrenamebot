"""
StraWchat Rename Bot — Main entry point
Telegram: @StraWchatOfficial
Supports concurrent file processing.
"""

import asyncio
import logging
import os

from pyrogram import Client
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting @StraWchatOfficial Rename Bot...")

    app = Client(
        "straWchat_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins={"root": "handlers"},
        workers=32,          # Handle up to 32 concurrent operations
        max_concurrent_transmissions=10,  # Up to 10 simultaneous uploads/downloads
    )

    app.run()


if __name__ == "__main__":
    main()
