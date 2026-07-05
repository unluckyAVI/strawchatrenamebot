"""
StraWchat Rename Bot — Main entry point
Telegram: @StraWchatOfficial
Max 4 concurrent file tasks for optimal speed.
"""

import logging
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
        workers=16,
        max_concurrent_transmissions=3,
    )

    app.run()


if __name__ == "__main__":
    main()
