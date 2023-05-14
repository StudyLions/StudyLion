import discord

from meta.LionContext import LionContext
from meta import conf


# Interaction Wards

async def i_sys_admin(interaction: discord.Interaction) -> bool:
    """
    Checks whether the context author is listed in the configuration file as a bot admin.
    """
    admins = conf.bot.getintlist('admins')
    return interaction.user.id in admins


async def i_high_management(interaction: discord.Interaction) -> bool:
    if await i_sys_admin(interaction):
        return True
    if not interaction.guild:
        return False
    return interaction.user.guild_permissions.administrator


async def i_low_management(interaction: discord.Interaction) -> bool:
    if await i_high_management(interaction):
        return True
    if not interaction.guild:
        return False
    return interaction.user.guild_permissions.manage_guild


async def sys_admin(ctx: LionContext) -> bool:
    admins = ctx.bot.config.bot.getintlist('admins')
    return ctx.author.id in admins


async def high_management(ctx: LionContext) -> bool:
    if await sys_admin(ctx):
        return True
    if not ctx.guild:
        return False
    return ctx.author.guild_permissions.administrator


async def low_management(ctx: LionContext) -> bool:
    return (await high_management(ctx)) or ctx.author.guild_permissions.manage_guild
