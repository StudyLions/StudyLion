# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-04
# Purpose: Lightweight Discord webhook logging handler for SoundsBot.
#          Sends ERROR+ log records to a Discord channel via webhook,
#          with batching and basic rate limiting.
# ============================================================

import asyncio
import logging
import time
from io import StringIO

import aiohttp
import discord
from discord import Webhook

logger = logging.getLogger(__name__)

MAX_SENDS_PER_MINUTE = 15
DISCORD_MSG_LIMIT = 1900


class WebhookErrorHandler(logging.Handler):
    """Logging handler that batches ERROR+ records and posts them to a Discord webhook."""

    def __init__(self, webhook_url: str, bot_label: str = "SoundsBot", batch_delay: float = 5.0):
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url
        self.bot_label = bot_label
        self.batch_delay = batch_delay

        self._session: aiohttp.ClientSession | None = None
        self._webhook: Webhook | None = None
        self._buffer: list[logging.LogRecord] = []
        self._flush_task: asyncio.Task | None = None

        self._send_count = 0
        self._window_start = 0.0

    def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._webhook = Webhook.from_url(self.webhook_url, session=self._session)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.format(record)
            loop = asyncio.get_running_loop()
            self._buffer.append(record)
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = loop.create_task(self._delayed_flush())
        except RuntimeError:
            pass
        except Exception:
            self.handleError(record)

    async def _delayed_flush(self):
        try:
            await asyncio.sleep(self.batch_delay)
            await self._flush()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[{self.bot_label}] Webhook flush error: {exc}")

    async def _flush(self):
        if not self._buffer:
            return

        records = self._buffer[:]
        self._buffer.clear()

        now = time.monotonic()
        if now - self._window_start > 60:
            self._send_count = 0
            self._window_start = now
        if self._send_count >= MAX_SENDS_PER_MINUTE:
            return

        self._ensure_session()

        lines = []
        for rec in records:
            ts = getattr(rec, 'asctime', '')
            line = f"[{ts}][{rec.levelname}] {rec.name}: {rec.getMessage()}"
            if rec.exc_text:
                line += f"\n{rec.exc_text}"
            lines.append(line)

        combined = "\n\n".join(lines)

        try:
            if len(combined) > DISCORD_MSG_LIMIT:
                fp = StringIO(combined)
                await self._webhook.send(
                    f"**{len(records)} error(s) from {self.bot_label}**",
                    file=discord.File(fp, filename="errors.md"),
                    username=self.bot_label,
                )
            else:
                await self._webhook.send(
                    f"```\n{combined}\n```",
                    username=self.bot_label,
                )
            self._send_count += 1
        except Exception as exc:
            print(f"[{self.bot_label}] Failed to post error webhook: {exc}")

    async def close_session(self):
        """Flush remaining records and close the HTTP session."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        if self._buffer:
            await self._flush()
        if self._session and not self._session.closed:
            await self._session.close()
