import asyncio
import discord
from cmdClient import Context
from cmdClient.lib import SafeCancellation

from data import tables
from core import Lion
from . import lib
from settings import GuildSettings, UserSettings


@Context.util
async def embed_reply(ctx, desc, colour=discord.Colour.orange(), **kwargs):
    """
    Simple helper to embed replies.
    All arguments are passed to the embed constructor.
    `desc` is passed as the `description` kwarg.
    """
    embed = discord.Embed(description=desc, colour=colour, **kwargs)
    try:
        return await ctx.reply(embed=embed, reference=ctx.msg.to_reference(fail_if_not_exists=False))
    except discord.Forbidden:
        if not ctx.guild or ctx.ch.permissions_for(ctx.guild.me).send_mssages:
            await ctx.reply("Command failed, I don't have permission to send embeds in this channel!")
        raise SafeCancellation


@Context.util
async def error_reply(ctx, error_str, send_args={}, **kwargs):
    """
    Notify the user of a user level error.
    Typically, this will occur in a red embed, posted in the command channel.
    """
    embed = discord.Embed(
        colour=discord.Colour.red(),
        description=error_str,
        **kwargs
    )
    message = None
    try:
        message = await ctx.ch.send(
            embed=embed,
            reference=ctx.msg.to_reference(fail_if_not_exists=False),
            **send_args
        )
        ctx.sent_messages.append(message)
        return message
    except discord.Forbidden:
        if not ctx.guild or ctx.ch.permissions_for(ctx.guild.me).send_mssages:
            await ctx.reply("Command failed, I don't have permission to send embeds in this channel!")
        raise SafeCancellation


@Context.util
async def offer_delete(ctx: Context, *to_delete, timeout=300):
    """
    Offers to delete the provided messages via a reaction on the last message.
    Removes the reaction if the offer times out.

    If any exceptions occur, handles them silently and returns.

    Parameters
    ----------
    to_delete: List[Message]
        The messages to delete.

    timeout: int
        Time in seconds after which to remove the delete offer reaction.
    """
    # Get the delete emoji from the config
    emoji = lib.cross

    # Return if there are no messages to delete
    if not to_delete:
        return

    # The message to add the reaction to
    react_msg = to_delete[-1]

    # Build the reaction check function
    if ctx.guild:
        modrole = ctx.guild_settings.mod_role.value if ctx.guild else None

        def check(reaction, user):
            if not (reaction.message.id == react_msg.id and reaction.emoji == emoji):
                return False
            if user == ctx.guild.me:
                return False
            return ((user == ctx.author)
                    or (user.permissions_in(ctx.ch).manage_messages)
                    or (modrole and modrole in user.roles))
    else:
        def check(reaction, user):
            return user == ctx.author and reaction.message.id == react_msg.id and reaction.emoji == emoji

    try:
        # Add the reaction to the message
        await react_msg.add_reaction(emoji)

        # Wait for the user to press the reaction
        reaction, user = await ctx.client.wait_for("reaction_add", check=check, timeout=timeout)

        # Since the check was satisfied, the reaction is correct. Delete the messages, ignoring any exceptions
        deleted = False
        # First try to bulk delete if we have the permissions
        if ctx.guild and ctx.ch.permissions_for(ctx.guild.me).manage_messages:
            try:
                await ctx.ch.delete_messages(to_delete)
                deleted = True
            except Exception:
                deleted = False

        # If we couldn't bulk delete, delete them one by one
        if not deleted:
            try:
                asyncio.gather(*[message.delete() for message in to_delete], return_exceptions=True)
            except Exception:
                pass
    except (asyncio.TimeoutError, asyncio.CancelledError):
        # Timed out waiting for the reaction, attempt to remove the delete reaction
        try:
            await react_msg.remove_reaction(emoji, ctx.client.user)
        except Exception:
            pass
    except discord.Forbidden:
        pass
    except discord.NotFound:
        pass
    except discord.HTTPException:
        pass


def context_property(func):
    setattr(Context, func.__name__, property(func))
    return func


@context_property
def best_prefix(ctx):
    return ctx.client.prefix


@context_property
def guild_settings(ctx):
    if ctx.guild:
        tables.guild_config.fetch_or_create(ctx.guild.id)
    return GuildSettings(ctx.guild.id if ctx.guild else 0)


@context_property
def author_settings(ctx):
    return UserSettings(ctx.author.id)


@context_property
def alion(ctx):
    return Lion.fetch(ctx.guild.id if ctx.guild else 0, ctx.author.id)
