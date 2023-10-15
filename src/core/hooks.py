from typing import Optional
import logging
import asyncio

import discord

from meta import LionBot

from .data import CoreData

logger = logging.getLogger(__name__)


MISSING = discord.utils.MISSING


class HookedChannel:
    def __init__(self, bot: LionBot, channelid: int):
        self.bot = bot
        self.channelid = channelid

        self.webhook: Optional[discord.Webhook] | MISSING = None
        self.data: Optional[CoreData.LionHook] = None

        self.lock = asyncio.Lock()

    @property
    def channel(self) -> Optional[discord.TextChannel | discord.VoiceChannel | discord.StageChannel]:
        if not self.bot.is_ready():
            raise ValueError("Cannot get hooked channel before ready.")
        channel = self.bot.get_channel(self.channelid)
        if channel and not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
            raise ValueError(f"Hooked channel expects GuildChannel not '{channel.__class__.__name__}'")
        return channel

    async def get_webhook(self) -> Optional[discord.Webhook]:
        """
        Fetch the saved discord.Webhook for this channel.

        Uses cached webhook if possible, but instantiates if required.
        Does not create a new webhook, use `create_webhook` for that.
        """
        async with self.lock:
            if self.webhook is MISSING:
                hook = None
            elif self.webhook is None:
                # Fetch webhook data
                data = await CoreData.LionHook.fetch(self.channelid)
                if data is not None:
                    # Instantiate Webhook
                    hook = self.webhook = data.as_webhook(client=self.bot)
                else:
                    self.webhook = MISSING
                    hook = None
            else:
                hook = self.webhook

            return hook

    async def create_webhook(self, **creation_kwargs) -> Optional[discord.Webhook]:
        """
        Create and save a new webhook in this channel.

        Returns None if we could not create a new webhook.
        """
        async with self.lock:
            if self.webhook is not MISSING:
                # Delete any existing webhook
                if self.webhook is not None:
                    try:
                        await self.webhook.delete()
                    except discord.HTTPException as e:
                        logger.info(
                            f"Ignoring exception while refreshing webhook for {self.channelid}: {repr(e)}"
                        )
                await self.bot.core.data.LionHook.table.delete_where(channelid=self.channelid)
                self.webhook = MISSING
                self.data = None

            channel = self.channel
            if channel is not None and channel.permissions_for(channel.guild.me).manage_webhooks:
                if 'avatar' not in creation_kwargs:
                    avatar = self.bot.user.avatar if self.bot.user else None
                    creation_kwargs['avatar'] = (await avatar.to_file()).fp.read() if avatar else None
                webhook = await channel.create_webhook(**creation_kwargs)
                self.data = await self.bot.core.data.LionHook.create(
                    channelid=self.channelid,
                    token=webhook.token,
                    webhookid=webhook.id,
                )
                self.webhook = webhook
                return webhook

    async def invalidate(self, webhook: discord.Webhook):
        """
        Invalidate the given webhook.

        To be used when the webhook has been deleted on the Discord side.
        """
        async with self.lock:
            if self.webhook is not None and self.webhook is not MISSING and self.webhook.id == webhook.id:
                # Webhook provided matches current webhook
                # Delete current webhook
                self.webhook = MISSING
                self.data = None
            await self.bot.core.data.LionHook.table.delete_where(webhookid=webhook.id)
