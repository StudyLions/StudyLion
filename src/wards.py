from typing import Optional
import discord
from discord.ext.commands.errors import CheckFailure
import discord.ext.commands as cmds

from babel.translator import LocalBabel

from meta import conf, LionContext, LionBot
from meta.errors import UserInputError

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


@cmds.check
async def moderator_ward(ctx: LionContext) -> bool:
    if not ctx.guild:
        return False
    passed = await low_management(ctx.bot, ctx.author)
    if passed:
        return True
    modrole = ctx.lguild.data.mod_role
    roleids = [role.id for role in ctx.author.roles]
    if not (modrole and modrole in roleids):
        raise CheckFailure(
            ctx.bot.translator.t(_p(
                'ward:moderator|failed',
                "You must have the configured moderator role, "
                "or `MANAGE_GUILD` permissions to do this."
            ))
        )
    return True

# ---- Assorted manual wards and checks ----


async def equippable_role(bot: LionBot, target_role: discord.Role, actor: discord.Member):
    """
    Validator for an 'actor' setting a given 'target_role' as obtainable.

    Checks that the 'target_role' is able to be given out,
    that I am able to give it out, and that the 'actor' is able to give it out.
    Raises UserInputError if any of these do not hold.
    """
    t = bot.translator.t
    guild = target_role.guild
    me = guild.me

    if target_role.is_bot_managed():
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:bot_managed',
                "I cannot manage {role} because it is managed by another bot!"
            )).format(role=target_role.mention)
        )
    elif target_role.is_integration():
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:integration',
                "I cannot manage {role} because it is managed by a server integration."
            )).format(role=target_role.mention)
        )
    elif target_role == guild.default_role:
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:default_role',
                "I cannot manage the server's default role."
            )).format(role=target_role.mention)
        )
    elif not me.guild_permissions.manage_roles:
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:no_perms',
                "I need the `MANAGE_ROLES` permission before I can manage roles!"
            )).format(role=target_role.mention)
        )
    elif me.top_role <= target_role:
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:my_top_role',
                "I cannot assign or remove {role} because it is above my top role!"
            )).format(role=target_role.mention)
        )
    elif not target_role.is_assignable():
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:not_assignable',
                "I don't have sufficient permissions to assign or remove {role}."
            )).format(role=target_role.mention)
        )

    if not actor.guild_permissions.manage_roles:
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:actor_perms',
                "You need the `MANAGE_ROLES` permission before you can configure roles!"
            )).format(role=target_role.mention)
        )
    elif actor.top_role <= target_role and not actor == guild.owner:
        raise UserInputError(
            t(_p(
                'ward:equippable_role|error:actor_top_role',
                "You cannot configure {role} because it is above your top role!"
            )).format(role=target_role.mention)
        )

    return True
