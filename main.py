# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: Entry point for the Ambient Sounds Bot — loads config,
#          pre-encodes audio, and starts up to 5 bot instances
#          in a single asyncio event loop.
# ============================================================

import asyncio
import configparser
import logging
import os
import sys

from audio_manager import AudioLibrary
from sound_bot import SoundBot
from webhook_logger import WebhookErrorHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('sounds_bot')

# --- AI-MODIFIED (2026-04-04) ---
# Purpose: Global reference to webhook handler for cleanup on shutdown
_webhook_handler: WebhookErrorHandler | None = None
# --- END AI-MODIFIED ---


def load_config(path: str = None) -> configparser.ConfigParser:
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
    cfg = configparser.ConfigParser()
    if not os.path.isfile(path):
        logger.error("Config file not found: %s", path)
        sys.exit(1)
    cfg.read(path)
    return cfg


async def main():
    # --- AI-MODIFIED (2026-04-04) ---
    # Purpose: Set up Discord webhook error logging
    global _webhook_handler
    # --- END AI-MODIFIED ---
    config = load_config()

    dsn = config.get('database', 'dsn')
    sounds_dir = config.get('audio', 'sounds_dir', fallback='sounds')

    # --- AI-MODIFIED (2026-04-04) ---
    # Purpose: Attach webhook error handler so ERROR+ logs go to Discord
    error_webhook = config.get('logging', 'error_webhook', fallback='').strip()
    if error_webhook:
        _webhook_handler = WebhookErrorHandler(
            webhook_url=error_webhook,
            bot_label="SoundsBot",
            batch_delay=5.0,
        )
        logging.getLogger().addHandler(_webhook_handler)
        logger.info("Webhook error logging enabled")
    else:
        logger.warning("No error_webhook configured — errors will only go to console")
    # --- END AI-MODIFIED ---

    if not os.path.isabs(sounds_dir):
        sounds_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), sounds_dir)

    logger.info("Loading audio library from %s …", sounds_dir)
    audio_lib = AudioLibrary(sounds_dir)
    logger.info("Audio ready: %s", ', '.join(audio_lib.available_sounds))

    bots: list[tuple[SoundBot, str]] = []
    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Discover LoFi directory and pass to each SoundBot
    lofi_dir = os.path.join(sounds_dir, 'lofi')
    if os.path.isdir(lofi_dir):
        lofi_count = len([f for f in os.listdir(lofi_dir) if f.lower().endswith(('.mp3', '.ogg', '.wav', '.flac'))])
        logger.info("LoFi directory found: %s (%d songs)", lofi_dir, lofi_count)
    else:
        lofi_dir = None
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Support 10 sound bots instead of 5
    for i in range(1, 11):
        key = f'token_{i}'
        if config.has_option('bots', key):
            token = config.get('bots', key).strip()
            if token and not token.startswith('YOUR_'):
                bot = SoundBot(bot_number=i, db_dsn=dsn, audio_lib=audio_lib, lofi_dir=lofi_dir)
                bots.append((bot, token))
                logger.info("Registered bot #%d", i)

    if not bots:
        logger.error("No valid bot tokens in config — nothing to start")
        sys.exit(1)

    logger.info("Starting %d sound bot(s) …", len(bots))

    try:
        await asyncio.gather(*(bot.start(token) for bot, token in bots))
    except KeyboardInterrupt:
        pass
    finally:
        for bot, _ in bots:
            if not bot.is_closed():
                await bot.close()
        # --- AI-MODIFIED (2026-04-04) ---
        # Purpose: Flush and close webhook session on shutdown
        if _webhook_handler is not None:
            await _webhook_handler.close_session()
        # --- END AI-MODIFIED ---
        logger.info("All bots shut down")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
