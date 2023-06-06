from typing import Optional
import discord
from discord.ext.commands.errors import CheckFailure
import discord.ext.commands as cmds

from babel.translator import LocalBabel

from meta import conf, LionContext, LionBot

babel = LocalBabel('wards')
_p = babel._p


# Raw checks, return True/False depending on whether they pass
async def sys_admin(bot: LionBot, userid: int):
    """
    Checks whether the context author is listed in the configuration file as a bot admin.
    """
    admins = bot.config.bot.getintlist('admins')
    return userid in admins


async def high_management(bot: LionBot, member: discord.Member):
    if await sys_admin(bot, member.id):
        return True
    return member.guild_permissions.administrator


async def low_management(bot: LionBot, member: discord.Member):
    if await high_management(bot, member):
        return True
    return member.guild_permissions.manage_guild


# Interaction Wards, also return True/False

async def sys_admin_iward(interaction: discord.Interaction) -> bool:
    return await sys_admin(interaction.client, interaction.user.id)


async def high_management_iward(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    return await high_management(interaction.client, interaction.user)


async def low_management_iward(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    return await low_management(interaction.client, interaction.user)


# Command Wards, raise CheckFailure with localised error message

@cmds.check
async def sys_admin_ward(ctx: LionContext) -> bool:
    passed = await sys_admin(ctx.bot, ctx.author.id)
    if passed:
        return True
    else:
        raise CheckFailure(
            ctx.bot.translator.t(_p(
                'ward:sys_admin|failed',
                "You must be a bot owner to do this!"
            ))
        )


@cmds.check
async def high_management_ward(ctx: LionContext) -> bool:
    if not ctx.guild:
        return False
    passed = await high_management(ctx.bot, ctx.author)
    if passed:
        return True
    else:
        raise CheckFailure(
            ctx.bot.translator.t(_p(
                'ward:high_management|failed',
                "You must have the `ADMINISTRATOR` permission in this server to do this!"
            ))
        )


@cmds.check
async def low_management_ward(ctx: LionContext) -> bool:
    if not ctx.guild:
        return False
    passed = await low_management(ctx.bot, ctx.author)
    if passed:
        return True
    else:
        raise CheckFailure(
            ctx.bot.translator.t(_p(
                'ward:low_management|failed',
                "You must have the `MANAGE_GUILD` permission in this server to do this!"
            ))
        )
