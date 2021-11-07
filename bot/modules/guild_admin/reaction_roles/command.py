import asyncio
import discord
from discord import PartialEmoji

from cmdClient.lib import ResponseTimedOut, UserCancelled
from wards import guild_admin
from settings import UserInputError
from utils.lib import tick, cross

from .module import module
from .tracker import ReactionRoleMessage
from .data import reaction_role_reactions, reaction_role_messages
from . import settings


example_emoji = "🧮"
example_str = "🧮 mathematics, 🫀 biology, 💻 computer science, 🖼️ design, 🩺 medicine"


def _parse_messageref(ctx):
    """
    Parse a message reference from the context message and return it.
    Removes the parsed string from `ctx.args` if applicable.
    Supports the following reference types, in precedence order:
        - A Discord message reply reference.
        - A message link.
        - A message id.

    Returns: (channelid, messageid)
        `messageid` will be `None` if a valid reference was not found.
        `channelid` will be `None` if the message was provided by pure id.
    """
    target_id = None
    target_chid = None

    if ctx.msg.reference:
        # True message reference extract message and return
        target_id = ctx.msg.reference.message_id
        target_chid = ctx.msg.reference.channel_id
    elif ctx.args:
        # Parse the first word of the message arguments
        splits = ctx.args.split(maxsplit=1)
        maybe_target = splits[0]

        # Expect a message id or message link
        if maybe_target.isdigit():
            # Assume it is a message id
            target_id = int(maybe_target)
        elif '/' in maybe_target:
            # Assume it is a link
            # Split out the channelid and messageid, if possible
            link_splits = maybe_target.rsplit('/', maxsplit=2)
            if len(link_splits) > 1 and link_splits[-1].isdigit() and link_splits[-2].isdigit():
                target_id = int(link_splits[-1])
                target_chid = int(link_splits[-2])

        # If we found a target id, truncate the arguments
        if target_id is not None:
            if len(splits) > 1:
                ctx.args = splits[1].strip()
            else:
                ctx.args = ""
        else:
            # Last-ditch attempt, see if the argument could be a stored reaction
            maybe_emoji = maybe_target.strip(',')
            guild_message_rows = reaction_role_messages.fetch_rows_where(guildid=ctx.guild.id)
            messages = [ReactionRoleMessage.fetch(row.messageid) for row in guild_message_rows]
            emojis = {reaction.emoji: message for message in messages for reaction in message.reactions}
            emoji_name_map = {emoji.name.lower(): emoji for emoji in emojis}
            emoji_id_map = {emoji.id: emoji for emoji in emojis if emoji.id}
            result = _parse_emoji(maybe_emoji, emoji_name_map, emoji_id_map)
            if result and result in emojis:
                message = emojis[result]
                target_id = message.messageid
                target_chid = message.data.channelid

    # Return the message reference
    return (target_chid, target_id)


def _parse_emoji(emoji_str, name_map, id_map):
    """
    Extract a PartialEmoji from a user provided emoji string, given the accepted raw names and ids.
    """
    emoji = None
    if len(emoji_str) < 10 and all(ord(char) >= 256 for char in emoji_str):
        # The string is pure unicode, we assume built in emoji
        emoji = PartialEmoji(name=emoji_str)
    elif emoji_str.lower() in name_map:
        emoji = name_map[emoji_str.lower()]
    elif emoji_str.isdigit() and int(emoji_str) in id_map:
        emoji = id_map[int(emoji_str)]
    else:
        # Attempt to parse as custom emoji
        # Accept custom emoji provided in the full form
        emoji_split = emoji_str.strip('<>:').split(':')
        if len(emoji_split) in (2, 3) and emoji_split[-1].isdigit():
            emoji_id = int(emoji_split[-1])
            emoji_name = emoji_split[-2]
            emoji_animated = emoji_split[0] == 'a'
            emoji = PartialEmoji(
                name=emoji_name,
                id=emoji_id,
                animated=emoji_animated
            )
    return emoji


async def reaction_ask(ctx, question, timeout=120, timeout_msg=None, cancel_msg=None):
    """
    Asks the author the provided question in an embed, and provides check/cross reactions for answering.
    """
    embed = discord.Embed(
        colour=discord.Colour.orange(),
        description=question
    )
    out_msg = await ctx.reply(embed=embed)

    # Wait for a tick/cross
    asyncio.create_task(out_msg.add_reaction(tick))
    asyncio.create_task(out_msg.add_reaction(cross))

    def check(reaction, user):
        result = True
        result = result and reaction.message == out_msg
        result = result and user == ctx.author
        result = result and (reaction.emoji == tick or reaction.emoji == cross)
        return result

    try:
        reaction, _ = await ctx.client.wait_for(
            'reaction_add',
            check=check,
            timeout=120
        )
    except asyncio.TimeoutError:
        try:
            await out_msg.edit(
                embed=discord.Embed(
                    colour=discord.Colour.red(),
                    description=timeout_msg or "Prompt timed out."
                )
            )
        except discord.HTTPException:
            pass
        raise ResponseTimedOut from None
    if reaction.emoji == cross:
        try:
            await out_msg.edit(
                embed=discord.Embed(
                    colour=discord.Colour.red(),
                    description=cancel_msg or "Cancelled."
                )
            )
        except discord.HTTPException:
            pass
        raise UserCancelled from None

    try:
        await out_msg.delete()
    except discord.HTTPException:
        pass

    return True


_message_setting_flags = {
    'removable': settings.removable,
    'maximum': settings.maximum,
    'required_role': settings.required_role,
    'log': settings.log,
    'refunds': settings.refunds,
    'default_price': settings.default_price,
}
_reaction_setting_flags = {
    'price': settings.price,
    'duration': settings.duration
}


@module.cmd(
    "reactionroles",
    group="Guild Configuration",
    desc="Create and configure reaction role messages.",
    aliases=('rroles',),
    flags=(
        'delete', 'remove==',
        'enable', 'disable',
        'required_role==', 'removable=', 'maximum=', 'refunds=', 'log=', 'default_price=',
        'price=', 'duration=='
    )
)
@guild_admin()
async def cmd_reactionroles(ctx, flags):
    """
    Usage``:
        {prefix}rroles
        {prefix}rroles [enable|disable|delete] msglink
        {prefix}rroles msglink [emoji1 role1, emoji2 role2, ...]
        {prefix}rroles msglink --remove emoji1, emoji2, ...
        {prefix}rroles msglink --message_setting [value]
        {prefix}rroles msglink emoji --reaction_setting [value]
    Description:
        Create and configure "reaction roles", i.e. roles obtainable by \
            clicking reactions on a particular message.
        `msglink` is the link or message id of the message with reactions.
        `emoji` should be given as the emoji itself, or the name or id.
        `role` may be given by name, mention, or id.
    Getting started:
        First choose the message you want to add reaction roles to, \
            and copy the link or message id for that message. \
            Then run the command `{prefix}rroles link`, replacing `link` with the copied link, \
            and follow the prompts.
        For faster setup, use `{prefix}rroles link emoji1 role1, emoji2 role2` instead.
    Editing reaction roles:
        Remove roles with `{prefix}rroles link --remove emoji1, emoji2, ...`
        Add/edit roles with `{prefix}rroles link emoji1 role1, emoji2 role2, ...`
    Examples``:
        {prefix}rroles {ctx.msg.id} 🧮 mathematics, 🫀 biology, 🩺 medicine
        {prefix}rroles disable {ctx.msg.id}
    PAGEBREAK:
        Page 2
    Advanced configuration:
        Type `{prefix}rroles link` again to view the advanced setting window, \
            and use `{prefix}rroles link --setting value` to modify the settings. \
            See below for descriptions of each message setting.
        For example to disable event logging, run `{prefix}rroles link --log off`.

        For per-reaction settings, instead use `{prefix}rroles link emoji --setting value`.
    Message Settings::
        maximum: Maximum number of roles obtainable from this message.
        log: Whether to log reaction role usage into the event log.
        removable: Whether the reactions roles can be remove by unreacting.
        refunds: Whether to refund the role price when removing the role.
        default_price: The default price of each role on this message.
        required_role: The role required to use these reactions roles.
    Reaction Settings::
        price: The price of this reaction role.
        tduration: How long this role will last after being selected or bought.
    Configuration Examples``:
        {prefix}rroles {ctx.msg.id} --maximum 5
        {prefix}rroles {ctx.msg.id} --default_price 20
        {prefix}rroles {ctx.msg.id} --required_role None
        {prefix}rroles {ctx.msg.id} 🧮 --price 1024
        {prefix}rroles {ctx.msg.id} 🧮 --duration 7 days
    """
    if not ctx.args:
        # No target message provided, list the current reaction messages
        # Or give a brief guide if there are no current reaction messages
        guild_message_rows = reaction_role_messages.fetch_rows_where(guildid=ctx.guild.id)
        if guild_message_rows:
            # List messages

            # First get the list of reaction role messages in the guild
            messages = [ReactionRoleMessage.fetch(row.messageid) for row in guild_message_rows]

            # Sort them by channelid and messageid
            messages.sort(key=lambda m: (m.data.channelid, m.messageid))

            # Build the message description strings
            message_strings = []
            for message in messages:
                header = (
                    "`{}` in <#{}> ([Click to jump]({})){}".format(
                        message.messageid,
                        message.data.channelid,
                        message.message_link,
                        " (disabled)" if not message.enabled else ""
                    )
                )
                role_strings = [
                    "{} <@&{}>".format(reaction.emoji, reaction.data.roleid)
                    for reaction in message.reactions
                ]
                role_string = '\n'.join(role_strings) or "No reaction roles!"

                message_strings.append("{}\n{}".format(header, role_string))

            pages = []
            page = []
            page_len = 0
            page_chars = 0
            i = 0
            while i < len(message_strings):
                message_string = message_strings[i]
                chars = len(message_string)
                lines = len(message_string.splitlines())
                if (page and lines + page_len > 20) or (chars + page_chars > 2000):
                    pages.append('\n\n'.join(page))
                    page = []
                    page_len = 0
                    page_chars = 0
                else:
                    page.append(message_string)
                    page_len += lines
                    page_chars += chars
                    i += 1
            if page:
                pages.append('\n\n'.join(page))

            page_count = len(pages)
            title = "Reaction Roles in {}".format(ctx.guild.name)
            embeds = [
                discord.Embed(
                    colour=discord.Colour.orange(),
                    description=page,
                    title=title
                )
                for page in pages
            ]
            if page_count > 1:
                [embed.set_footer(text="Page {} of {}".format(i + 1, page_count)) for i, embed in enumerate(embeds)]
            await ctx.pager(embeds)
        else:
            # Send a setup guide
            embed = discord.Embed(
                title="No Reaction Roles set up!",
                description=(
                    "To setup reaction roles, first copy the link or message id of the message you want to "
                    "add the roles to. Then run `{prefix}rroles link`, replacing `link` with the link you copied, "
                    "and follow the prompts.\n"
                    "See `{prefix}help rroles` for more information.".format(prefix=ctx.best_prefix)
                ),
                colour=discord.Colour.orange()
            )
            await ctx.reply(embed=embed)
        return

    # Extract first word, look for a subcommand
    splits = ctx.args.split(maxsplit=1)
    subcmd = splits[0].lower()

    if subcmd in ('enable', 'disable', 'delete'):
        # Truncate arguments and extract target
        if len(splits) > 1:
            ctx.args = splits[1]
            target_chid, target_id = _parse_messageref(ctx)
        else:
            target_chid = None
            target_id = None
            ctx.args = ''

        # Handle subcommand special cases
        if subcmd == 'enable':
            if ctx.args and not target_id:
                await ctx.error_reply(
                    "Couldn't find the message to enable!\n"
                    "**Usage:** `{}rroles enable [message link or id]`.".format(ctx.best_prefix)
                )
            elif not target_id:
                # Confirm enabling of all reaction messages
                await reaction_ask(
                    "Are you sure you want to enable all reaction role messages in this server?",
                    timeout_msg="Prompt timed out, no reaction roles enabled.",
                    cancel_msg="User cancelled, no reaction roles enabled."
                )
                reaction_role_messages.update_where(
                    {'enabled': True},
                    guildid=ctx.guild.id
                )
                await ctx.embed_reply(
                    "All reaction role messages have been enabled.",
                    colour=discord.Colour.green(),
                )
            else:
                # Fetch the target
                target = ReactionRoleMessage.fetch(target_id)
                if target is None:
                    await ctx.error_reply(
                        "This message doesn't have any reaction roles!\n"
                        "Run the command again without `enable` to assign reaction roles."
                    )
                else:
                    # We have a valid target
                    if target.enabled:
                        await ctx.error_reply(
                            "This message is already enabled!"
                        )
                    else:
                        target.enabled = True
                        await ctx.embed_reply(
                            "The message has been enabled!"
                        )
        elif subcmd == 'disable':
            if ctx.args and not target_id:
                await ctx.error_reply(
                    "Couldn't find the message to disable!\n"
                    "**Usage:** `{}rroles disable [message link or id]`.".format(ctx.best_prefix)
                )
            elif not target_id:
                # Confirm disabling of all reaction messages
                await reaction_ask(
                    "Are you sure you want to disable all reaction role messages in this server?",
                    timeout_msg="Prompt timed out, no reaction roles disabled.",
                    cancel_msg="User cancelled, no reaction roles disabled."
                )
                reaction_role_messages.update_where(
                    {'enabled': False},
                    guildid=ctx.guild.id
                )
                await ctx.embed_reply(
                    "All reaction role messages have been disabled.",
                    colour=discord.Colour.green(),
                )
            else:
                # Fetch the target
                target = ReactionRoleMessage.fetch(target_id)
                if target is None:
                    await ctx.error_reply(
                        "This message doesn't have any reaction roles! Nothing to disable."
                    )
                else:
                    # We have a valid target
                    if not target.enabled:
                        await ctx.error_reply(
                            "This message is already disabled!"
                        )
                    else:
                        target.enabled = False
                        await ctx.embed_reply(
                            "The message has been disabled!"
                        )
        elif subcmd == 'delete':
            if ctx.args and not target_id:
                await ctx.error_reply(
                    "Couldn't find the message to remove!\n"
                    "**Usage:** `{}rroles remove [message link or id]`.".format(ctx.best_prefix)
                )
            elif not target_id:
                # Confirm disabling of all reaction messages
                await reaction_ask(
                    "Are you sure you want to remove all reaction role messages in this server?",
                    timeout_msg="Prompt timed out, no messages removed.",
                    cancel_msg="User cancelled, no messages removed."
                )
                reaction_role_messages.delete_where(
                    guildid=ctx.guild.id
                )
                await ctx.embed_reply(
                    "All reaction role messages have been removed.",
                    colour=discord.Colour.green(),
                )
            else:
                # Fetch the target
                target = ReactionRoleMessage.fetch(target_id)
                if target is None:
                    await ctx.error_reply(
                        "This message doesn't have any reaction roles! Nothing to remove."
                    )
                else:
                    # We have a valid target
                    target.delete()
                    await ctx.embed_reply(
                        "The message has been removed and is no longer a reaction role message."
                    )
        return
    else:
        # Just extract target
        target_chid, target_id = _parse_messageref(ctx)

    # Handle target parsing issue
    if target_id is None:
        return await ctx.error_reply(
            "Couldn't parse `{}` as a message id or message link!\n"
            "See `{}help rroles` for detailed usage information.".format(ctx.args.split()[0], ctx.best_prefix)
        )

    # Get the associated ReactionRoleMessage, if it exists
    target = ReactionRoleMessage.fetch(target_id)

    # Get the target message
    if target:
        message = await target.fetch_message()
        if not message:
            # TODO: Consider offering some sort of `move` option here.
            await ctx.error_reply(
                "This reaction role message no longer exists!\n"
                "Use `{}rroles delete {}` to remove it from the list.".format(ctx.best_prefix, target.messageid)
            )
    else:
        message = None
        if target_chid:
            channel = ctx.guild.get_channel(target_chid)
            if not channel:
                await ctx.error_reply(
                    "The provided channel no longer exists!"
                )
            elif channel.type != discord.ChannelType.text:
                await ctx.error_reply(
                    "The provided channel is not a text channel!"
                )
            else:
                message = await channel.fetch_message(target_id)
                if not message:
                    await ctx.error_reply(
                        "Couldn't find the specified message in {}!".format(channel.mention)
                    )
        else:
            out_msg = await ctx.embed_reply("Searching for `{}`".format(target_id))
            message = await ctx.find_message(target_id)
            try:
                await out_msg.delete()
            except discord.HTTPException:
                pass
            if not message:
                await ctx.error_reply(
                    "Couldn't find the message `{}`!".format(target_id)
                )
    if not message:
        return

    # Handle the `remove` flag specially
    # In particular, all other flags are ignored
    if flags['remove']:
        if not target:
            await ctx.error_reply(
                "The specified message has no reaction roles! Nothing to remove."
            )
        else:
            # Parse emojis and remove from target
            target_emojis = {reaction.emoji: reaction for reaction in target.reactions}
            emoji_name_map = {emoji.name.lower(): emoji for emoji in target_emojis}
            emoji_id_map = {emoji.id: emoji for emoji in target_emojis}

            items = [item.strip() for item in flags['remove'].split(',')]
            to_remove = []  # List of reactions to remove
            for emoji_str in items:
                emoji = _parse_emoji(emoji_str, emoji_name_map, emoji_id_map)
                if emoji is None:
                    return await ctx.error_reply(
                        "Couldn't parse `{}` as an emoji! No reactions were removed.".format(emoji_str)
                    )
                if emoji not in target_emojis:
                    return await ctx.error_reply(
                        "{} is not a reaction role for this message!".format(emoji)
                    )
                to_remove.append(target_emojis[emoji])

            # Delete reactions from data
            description = '\n'.join("{} <@&{}>".format(reaction.emoji, reaction.data.roleid) for reaction in to_remove)
            reaction_role_reactions.delete_where(reactionid=[reaction.reactionid for reaction in to_remove])
            target.refresh()

            # Ack
            embed = discord.Embed(
                colour=discord.Colour.green(),
                title="Reaction Roles deactivated",
                description=description
            )
            await ctx.reply(embed=embed)
        return

    # Any remaining arguments should be emoji specifications with optional role
    # Parse these now
    given_emojis = {}  # Map PartialEmoji -> Optional[Role]
    existing_emojis = set()  # Set of existing reaction emoji identifiers

    if ctx.args:
        # First build the list of custom emojis we can accept by name
        # We do this by reverse precedence, so the highest priority emojis are added last
        custom_emojis = []
        custom_emojis.extend(ctx.guild.emojis)  # Custom emojis in the guild
        if target:
            custom_emojis.extend([r.emoji for r in target.reactions])  # Configured reaction roles on the target
        custom_emojis.extend([r.emoji for r in message.reactions if r.custom_emoji])  # Actual reactions on the message

        # Filter out the built in emojis and those without a name
        custom_emojis = (emoji for emoji in custom_emojis if emoji.name and emoji.id)

        # Build the maps to lookup provided custom emojis
        emoji_name_map = {emoji.name.lower(): emoji for emoji in custom_emojis}
        emoji_id_map = {emoji.id: emoji for emoji in custom_emojis}

        # Now parse the provided emojis
        # Assume that all-unicode strings are built-in emojis
        # We can't assume much else unless we have a list of such emojis
        splits = (split.strip() for line in ctx.args.splitlines() for split in line.split(',') if split)
        splits = (split.split(maxsplit=1) for split in splits if split)
        arg_emoji_strings = {
            split[0]: split[1] if len(split) > 1 else None
            for split in splits
        }  # emoji_str -> Optional[role_str]

        arg_emoji_map = {}
        for emoji_str, role_str in arg_emoji_strings.items():
            emoji = _parse_emoji(emoji_str, emoji_name_map, emoji_id_map)
            if emoji is None:
                return await ctx.error_reply(
                    "Couldn't parse `{}` as an emoji!".format(emoji_str)
                )
            else:
                arg_emoji_map[emoji] = role_str

        # Final pass extracts roles
        # If any new emojis were provided, their roles should be specified, we enforce this during role parsing
        # First collect the existing emoji strings
        if target:
            for reaction in target.reactions:
                emoji_id = reaction.emoji.name if reaction.emoji.id is None else reaction.emoji.id
                existing_emojis.add(emoji_id)

        # Now parse and assign the roles, building the final map
        for emoji, role_str in arg_emoji_map.items():
            emoji_id = emoji.name if emoji.id is None else emoji.id
            role = None
            if role_str:
                role = await ctx.find_role(role_str, create=True, interactive=True, allow_notfound=False)
            elif emoji_id not in existing_emojis:
                return await ctx.error_reply(
                    "New emoji {} was given without an associated role!".format(emoji)
                )
            given_emojis[emoji] = role

    # Next manage target creation or emoji editing, if required
    if target is None:
        # Reaction message creation wizard
        # Confirm that they want to create a new reaction role message.
        await reaction_ask(
            ctx,
            question="Do you want to set up new reaction roles for [this message]({})?".format(
                message.jump_url
            ),
            timeout_msg="Prompt timed out, no reaction roles created.",
            cancel_msg="Reaction Role creation cancelled."
        )

        # Continue with creation
        # Obtain emojis if not already provided
        if not given_emojis:
            # Prompt for the initial emojis
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title="What reaction roles would you like to add?",
                description=(
                    "Please now type the reaction roles you would like to add "
                    "in the form `emoji role`, where `role` is given by partial name or id. For example:"
                    "```{}```".format(example_str)
                )
            )
            out_msg = await ctx.reply(embed=embed)

            # Wait for a response
            def check(msg):
                return msg.author == ctx.author and msg.channel == ctx.ch and msg.content

            try:
                reply = await ctx.client.wait_for('message', check=check, timeout=300)
            except asyncio.TimeoutError:
                try:
                    await out_msg.edit(
                        embed=discord.Embed(
                            colour=discord.Colour.red(),
                            description="Prompt timed out, no reaction roles created."
                        )
                    )
                except discord.HTTPException:
                    pass
                return

            rolestrs = reply.content

            try:
                await reply.delete()
            except discord.HTTPException:
                pass

            # Attempt to parse the emojis
            # First build the list of custom emojis we can accept by name
            custom_emojis = []
            custom_emojis.extend(ctx.guild.emojis)  # Custom emojis in the guild
            custom_emojis.extend(
                r.emoji for r in message.reactions if r.custom_emoji
            )  # Actual reactions on the message

            # Filter out the built in emojis and those without a name
            custom_emojis = (emoji for emoji in custom_emojis if emoji.name and emoji.id)

            # Build the maps to lookup provided custom emojis
            emoji_name_map = {emoji.name.lower(): emoji for emoji in custom_emojis}
            emoji_id_map = {emoji.id: emoji for emoji in custom_emojis}

            # Now parse the provided emojis
            # Assume that all-unicode strings are built-in emojis
            # We can't assume much else unless we have a list of such emojis
            splits = (split.strip() for line in rolestrs.splitlines() for split in line.split(',') if split)
            splits = (split.split(maxsplit=1) for split in splits if split)
            arg_emoji_strings = {
                split[0]: split[1] if len(split) > 1 else None
                for split in splits
            }  # emoji_str -> Optional[role_str]

            # Check all the emojis have roles associated
            for emoji_str, role_str in arg_emoji_strings.items():
                if role_str is None:
                    return await ctx.error_reply(
                        "No role provided for `{}`! Reaction role creation cancelled.".format(emoji_str)
                    )

            # Parse the provided roles and emojis
            for emoji_str, role_str in arg_emoji_strings.items():
                emoji = _parse_emoji(emoji_str, emoji_name_map, emoji_id_map)
                if emoji is None:
                    return await ctx.error_reply(
                        "Couldn't parse `{}` as an emoji!".format(emoji_str)
                    )
                else:
                    given_emojis[emoji] = await ctx.find_role(
                        role_str,
                        create=True,
                        interactive=True,
                        allow_notfound=False
                    )

        if len(given_emojis) > 20:
            return await ctx.error_reply("A maximum of 20 reactions are possible per message! Cancelling creation.")

        # Create the ReactionRoleMessage
        target = ReactionRoleMessage.create(
            message.id,
            message.guild.id,
            message.channel.id
        )

        # Insert the reaction data directly
        reaction_role_reactions.insert_many(
            *((message.id, role.id, emoji.name, emoji.id, emoji.animated) for emoji, role in given_emojis.items()),
            insert_keys=('messageid', 'roleid', 'emoji_name', 'emoji_id', 'emoji_animated')
        )

        # Refresh the message to pick up the new reactions
        target.refresh()

        # Add the reactions to the message, if possible
        existing_reactions = set(
            reaction.emoji if not reaction.custom_emoji else
            (reaction.emoji.name if reaction.emoji.id is None else reaction.emoji.id)
            for reaction in message.reactions
        )
        missing = [
            reaction.emoji for reaction in target.reactions
            if (reaction.emoji.name if reaction.emoji.id is None else reaction.emoji.id) not in existing_reactions
        ]
        if not any(emoji.id not in set(cemoji.id for cemoji in ctx.guild.emojis) for emoji in missing if emoji.id):
            # We can add the missing emojis
            for emoji in missing:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    break
            else:
                missing = []

        # Ack the creation
        ack_msg = "Created `{}` new reaction roles on [this message]({})!".format(
            len(target.reactions),
            target.message_link
        )
        if missing:
            ack_msg += "\nPlease add the missing reactions to the message!"
        await ctx.embed_reply(
            ack_msg
        )
    elif given_emojis:
        # Update the target reactions
        # Create a map of the emojis that need to be added or updated
        needs_update = {
            emoji: role for emoji, role in given_emojis.items() if role
        }

        # Fetch the existing target emojis to split the roles into inserts and updates
        target_emojis = {reaction.emoji: reaction for reaction in target.reactions}

        # Handle the new roles
        insert_targets = {
            emoji: role for emoji, role in needs_update.items() if emoji not in target_emojis
        }
        if insert_targets:
            if len(insert_targets) + len(target_emojis) > 20:
                return await ctx.error_reply("Too many reactions! A maximum of 20 reactions are possible per message!")
            reaction_role_reactions.insert_many(
                *(
                    (message.id, role.id, emoji.name, emoji.id, emoji.animated)
                    for emoji, role in insert_targets.items()
                ),
                insert_keys=('messageid', 'roleid', 'emoji_name', 'emoji_id', 'emoji_animated')
            )
        # Handle the updated roles
        update_targets = {
            target_emojis[emoji]: role for emoji, role in needs_update.items() if emoji in target_emojis
        }
        if update_targets:
            reaction_role_reactions.update_many(
                *((role.id, reaction.reactionid) for reaction, role in update_targets.items()),
                set_keys=('roleid',),
                where_keys=('reactionid',),
            )

        # Finally, refresh to load the new reactions
        target.refresh()

    # Now that the target is created/updated, all the provided emojis should be reactions
    given_reactions = []
    if given_emojis:
        # Make a map of the existing reactions
        existing_reactions = {
            reaction.emoji.name if reaction.emoji.id is None else reaction.emoji.id: reaction
            for reaction in target.reactions
        }
        given_reactions = [
            existing_reactions[emoji.name if emoji.id is None else emoji.id]
            for emoji in given_emojis
        ]

    # Handle message setting updates
    update_lines = []  # Setting update lines to display
    update_columns = {}  # Message data columns to update
    for flag in _message_setting_flags:
        if flags[flag]:
            setting_class = _message_setting_flags[flag]
            try:
                setting = await setting_class.parse(target.messageid, ctx, flags[flag])
            except UserInputError as e:
                return await ctx.error_reply(
                    "{} {}\nNo settings were modified.".format(cross, e.msg),
                    title="Couldn't save settings!"
                )
            else:
                update_lines.append(
                    "{} {}".format(tick, setting.success_response)
                )
                update_columns[setting._data_column] = setting.data
    if update_columns:
        # First write the data
        reaction_role_messages.update_where(
            update_columns,
            messageid=target.messageid
        )
        # Then ack the setting update
        if len(update_lines) > 1:
            embed = discord.Embed(
                colour=discord.Colour.green(),
                title="Reaction Role message settings updated!",
                description='\n'.join(update_lines)
            )
        else:
            embed = discord.Embed(
                colour=discord.Colour.green(),
                description=update_lines[0]
            )
        await ctx.reply(embed=embed)

    # Handle reaction setting updates
    update_lines = []  # Setting update lines to display
    update_columns = {}  # Message data columns to update, for all given reactions
    reactions = given_reactions or target.reactions
    for flag in _reaction_setting_flags:
        for reaction in reactions:
            if flags[flag]:
                setting_class = _reaction_setting_flags[flag]
                try:
                    setting = await setting_class.parse(reaction.reactionid, ctx, flags[flag])
                except UserInputError as e:
                    return await ctx.error_reply(
                        "{} {}\nNo reaction roles were modified.".format(cross, e.msg),
                        title="Couldn't save reaction role settings!",
                    )
                else:
                    update_lines.append(
                        setting.success_response.format(reaction=reaction)
                    )
                    update_columns[setting._data_column] = setting.data
    if update_columns:
        # First write the data
        reaction_role_reactions.update_where(
            update_columns,
            reactionid=[reaction.reactionid for reaction in reactions]
        )
        # Then ack the setting update
        if len(update_lines) > 1:
            blocks = ['\n'.join(update_lines[i:i+20]) for i in range(0, len(update_lines), 20)]
            embeds = [
                discord.Embed(
                    colour=discord.Colour.green(),
                    title="Reaction Role settings updated!",
                    description=block
                ) for block in blocks
            ]
            await ctx.pager(embeds)
        else:
            embed = discord.Embed(
                colour=discord.Colour.green(),
                description=update_lines[0]
            )
            await ctx.reply(embed=embed)

    # Show the reaction role message summary
    # Build the reaction fields
    reaction_fields = []  # List of tuples (name, value)
    for reaction in target.reactions:
        reaction_fields.append(
            (
                "{} {}".format(reaction.emoji.name, reaction.emoji if reaction.emoji.id else ''),
                "<@&{}>\n{}".format(reaction.data.roleid, reaction.settings.tabulated())
            )
        )

    # Build the final setting pages
    description = (
        "{settings_table}\n"
        "To update a message setting: `{prefix}rroles messageid --setting value`\n"
        "To update an emoji setting: `{prefix}rroles messageid emoji --setting value`\n"
        "See examples and more usage information with `{prefix}help rroles`."
    ).format(
        prefix=ctx.best_prefix,
        settings_table=target.settings.tabulated()
    )

    field_blocks = [reaction_fields[i:i+6] for i in range(0, len(reaction_fields), 6)]
    page_count = len(field_blocks)
    embeds = []
    for i, block in enumerate(field_blocks):
        title = "Reaction role settings for message id `{}`".format(target.messageid)
        embed = discord.Embed(
            title=title,
            description=description
        ).set_author(
            name="Click to jump to message",
            url=target.message_link
        )
        for name, value in block:
            embed.add_field(name=name, value=value)
        if page_count > 1:
            embed.set_footer(text="Page {} of {}".format(i+1, page_count))
        embeds.append(embed)

    # Finally, send the reaction role information
    await ctx.pager(embeds)
