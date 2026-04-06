# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-06
# Purpose: Discord UI components for Anti AFK System.
#          Persistent "I'm still here" button view that
#          survives bot restarts via custom_id prefix.
# ============================================================
import discord
from discord.ui import View, Button, button
from discord import ButtonStyle

from meta import LionBot
from utils.lib import utc_now

from . import babel, logger

_p = babel._p

CUSTOM_ID_PREFIX = 'anti_afk:confirm'


class AntiAfkConfirmView(View):
    """
    Persistent view with an "I'm still here" button.

    Uses a fixed custom_id so buttons survive bot restarts.
    Each button encodes the guild and user it belongs to.
    When multiple users are batched into one message, we use
    a shared view where the callback checks interaction.user.id.
    """

    def __init__(self, bot: LionBot, guildid: int, userids: list[int]):
        super().__init__(timeout=None)
        self.bot = bot
        self.guildid = guildid
        self.userids = set(userids)

        self.confirm_button = Button(
            style=ButtonStyle.green,
            label="I'm still here!",
            emoji="\u2705",
            custom_id=f"{CUSTOM_ID_PREFIX}:{guildid}",
        )
        self.confirm_button.callback = self._on_confirm
        self.add_item(self.confirm_button)

    async def _on_confirm(self, interaction: discord.Interaction):
        user = interaction.user
        cog = self.bot.get_cog('AntiAfkCog')
        if not cog:
            await interaction.response.send_message(
                "Anti AFK system is currently unavailable.",
                ephemeral=True,
            )
            return

        handled = await cog.handle_confirm(interaction.guild_id or self.guildid, user.id)
        if handled:
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description="\u2705 Confirmed! Your check timer has been reset. Stay productive!",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                colour=discord.Colour.greyple(),
                description="No active check found for you. You're all good!",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class AntiAfkPersistentView(View):
    """
    Minimal persistent view registered at startup via bot.add_view().
    Handles all anti-afk confirm button presses by custom_id prefix.
    """

    def __init__(self, bot: LionBot):
        super().__init__(timeout=None)
        self.bot = bot

        self._button = Button(
            style=ButtonStyle.green,
            label="I'm still here!",
            emoji="\u2705",
            custom_id=f"{CUSTOM_ID_PREFIX}:0",
        )
        self._button.callback = self._on_confirm
        self.add_item(self._button)

    async def _on_confirm(self, interaction: discord.Interaction):
        user = interaction.user
        guildid = interaction.guild_id
        if not guildid:
            custom_id = interaction.data.get('custom_id', '') if interaction.data else ''
            parts = custom_id.split(':')
            if len(parts) >= 3:
                try:
                    guildid = int(parts[2])
                except ValueError:
                    pass

        if not guildid:
            await interaction.response.send_message(
                "Could not identify the server for this check.",
                ephemeral=True,
            )
            return

        cog = self.bot.get_cog('AntiAfkCog')
        if not cog:
            await interaction.response.send_message(
                "Anti AFK system is currently unavailable.",
                ephemeral=True,
            )
            return

        handled = await cog.handle_confirm(guildid, user.id)
        if handled:
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description="\u2705 Confirmed! Your check timer has been reset. Stay productive!",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                colour=discord.Colour.greyple(),
                description="No active check found for you. You're all good!",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
