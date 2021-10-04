import asyncio
import discord

from cmdClient.lib import ResponseTimedOut
from wards import guild_admin
from settings import UserInputError

from ..module import module

from .tracker import ReactionRoleMessage
from .data import reaction_role_reactions
from . import settings


example_str = "🧮 mathematics, 🫀 biology, 💻 computer science, 🖼️ design, 🩺 medicine"


@module.cmd(
    "reactionroles",
    group="Guild Admin",
    desc="Create or configure reaction role messages.",
    aliases=('rroles',),
    flags=(
        'delete', 'remove',
        'enable', 'disable',
        'required_role==', 'removable=', 'maximum=', 'refunds=', 'log=', 'default_price=',
        'price=', 'timeout=='
    )
)
@guild_admin()
async def cmd_reactionroles(ctx, flags):
    """
    Usage``:
        {prefix}rroles messageid
        {prefix}rroles messageid emoji1 role1, emoji2 role2, emoji3 role3, ...
        {prefix}rroles messageid --message_setting value
        {prefix}rroles messageid emoji --emoji_setting value
        {prefix}rroles messageid --remove emoji1, emoji2, ...
        {prefix}rroles messageid --enable
        {prefix}rroles messageid --disable
        {prefix}rroles messageid --delete
    Description:
        Reaction roles are message reactions that give members specific roles when used.
        This commands allows you to create and configure messages with reaction roles.
    Getting started:
        To get started, choose the message you want to add reaction roles to, and copy the link to that message. \
            Then run the command `{prefix}rroles link` (replacing `link` with the link you copied), and \
            follow the prompts.
    Configuration:
        After creation, you can view the message configuration and reaction roles with `{prefix}rroles link` \
            (you can also use the message id instead of the link, or reply to the message).

        You can set one of the configuration options with `{prefix}rroles link --setting value`.\
        For example to make it impossible to remove the reaction roles,\
            run `{prefix}rroles link --removable off`.

        There are also some configurable per-reaction settings, such as the price of a role.\
            To see these, use `{prefix}rroles link emoji` (replacing `emoji` with the reaction emoji) \
            and set them with e.g. `{prefix}rroles link emoji --price 200`.
    Message Settings::
        maximum: Maximum number of roles obtainable from this message.
        log: Whether to log reaction role usage into the event log.
        removable: Whether the reactions roles can be remove by unreacting.
        refunds: Whether to refund the role price when removing the role.
        default_price: The default price of each role on this message.
        required_role: The role required to use these reactions roles.
    Reaction Settings::
        price: The price of this reaction role.
        timeout: The amount of time the role lasts. (TBD)
    Examples:
        ...
    """
    if not ctx.args and not ctx.msg.reference:
        # No target message provided, list the current reaction messages
        # Or give a brief guide if there are no current reaction messages
        ...

    target_id = None
    target_chid = None
    remaining = ""

    if ctx.msg.reference:
        target_id = ctx.msg.reference.message_id
        target_chid = ctx.msg.reference.channel_id
        remaining = ctx.args
    elif ctx.args:
        # Try to parse the target message
        # Expect a link or a messageid as the first argument
        splits = ctx.args.split(maxsplit=1)
        maybe_target = splits[0]
        if len(splits) > 1:
            remaining = splits[1]
        if maybe_target.isdigit():
            # Assume it is a message id
            target_id = int(maybe_target)
        elif maybe_target.contains('/'):
            # Assume it is a link
            # Try and parse it
            link_splits = maybe_target.rsplit('/', maxsplit=2)
            if len(link_splits) > 1 and link_splits[-1].isdigit() and link_splits[-2].isdigit():
                # Definitely a link
                target_id = int(link_splits[-1])
                target_chid = int(link_splits[-2])

    if not target_id:
        return await ctx.error_reply(
            "Please provide the message link or message id as the first argument."
        )

    # We have a target, fetch the ReactionMessage if it exists
    target = ReactionRoleMessage.fetch(target_id)
    if target:
        # View or edit target

        # Exclusive flags, delete and remove ignore all other flags
        if flags['delete']:
            # Handle deletion of the ReactionRoleMessage
            ...
        if flags['remove']:
            # Handle emoji removal
            ...

        # Check whether we are editing a particular reaction
        # TODO: We might be updating roles or adding reactions as well
        if remaining:
            emojistr = remaining
            # TODO....

        # Lines for edit output
        edit_lines = []  # (success_state, string)
        # Columns to update
        update = {}

        # Message edit flags
        # Gets and modifies the settings, but doesn't write
        if flags['disable']:
            update['enabled'] = False
            edit_lines.append((True, "Reaction role message disabled."))
        elif flags['enable']:
            update['enabled'] = True
            edit_lines.append((True, "Reaction role message enabled."))

        if flags['required_role']:
            try:
                setting = await settings.required_role.parse(target.messageid, ctx, flags['required_role'])
            except UserInputError as e:
                edit_lines.append((False, e.msg))
            else:
                edit_lines.append((True, setting.success_response))
            update[setting._data_column] = setting.data
        if flags['removable']:
            try:
                setting = await settings.removable.parse(target.messageid, ctx, flags['removable'])
            except UserInputError as e:
                edit_lines.append((False, e.msg))
            else:
                edit_lines.append((True, setting.success_response))
            update[setting._data_column] = setting.data
        if flags['maximum']:
            try:
                setting = await settings.maximum.parse(target.messageid, ctx, flags['maximum'])
            except UserInputError as e:
                edit_lines.append((False, e.msg))
            else:
                edit_lines.append((True, setting.success_response))
            update[setting._data_column] = setting.data
        if flags['refunds']:
            try:
                setting = await settings.refunds.parse(target.messageid, ctx, flags['refunds'])
            except UserInputError as e:
                edit_lines.append((False, e.msg))
            else:
                edit_lines.append((True, setting.success_response))
            update[setting._data_column] = setting.data
        if flags['log']:
            try:
                setting = await settings.log.parse(target.messageid, ctx, flags['log'])
            except UserInputError as e:
                edit_lines.append((False, e.msg))
            else:
                edit_lines.append((True, setting.success_response))
            update[setting._data_column] = setting.data
        if flags['default_price']:
            try:
                setting = await settings.default_price.parse(target.messageid, ctx, flags['default_price'])
            except UserInputError as e:
                edit_lines.append((False, e.msg))
            else:
                edit_lines.append((True, setting.success_response))
            update[setting._data_column] = setting.data

        # Update the data all at once
        target.data.update(**update)

        # Then format and respond with the edit message

        # TODO: Emoji edit flags
        ...
    else:
        # Start creation process
        # First find the target message
        message = None
        if target_chid:
            channel = ctx.guild.get_channel(target_chid)
            if channel:
                message = await channel.fetch_message(target_id)
        else:
            # We only have a messageid, need to search for it through all the guild channels
            message = await ctx.find_message(target_id)

        if message is None:
            return await ctx.error_reply(
                "Could not find the specified message!"
            )

        # Confirm that they want to create a new reaction role message.
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            description="Do you want to set up new reaction roles for [this message]({}) (`y(es)`/`n(o)`)?".format(
                message.jump_url
            )
        )
        out_msg = await ctx.reply(embed=embed)
        if not await ctx.ask(msg=None, use_msg=out_msg):
            return

        # Set up the message as a new ReactionRole message.
        # First obtain the initial emojis
        if not remaining:
            # Prompt for the initial emojis
            embed = discord.Embed(
                title="What reaction roles would you like to add?",
                description=(
                    "Please now enter the reaction roles you would like to associate, "
                    "in the form `emoji role`, where `role` is given by id or partial name. For example:"
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
                raise ResponseTimedOut("Prompt timed out, no reaction roles were added.")
            finally:
                try:
                    await out_msg.delete()
                except discord.HTTPException:
                    pass

            rolestrs = reply.content

            try:
                await reply.delete()
            except discord.HTTPException:
                pass
        else:
            rolestrs = remaining

        # Attempt to parse the emojis
        # First split based on newline and comma
        splits = (split.strip() for line in rolestrs.splitlines() for split in line.split(','))
        splits = [split for split in splits if split]

        # Do a quick check to make sure everything is in the correct format
        unsplit = next((split for split in splits if ' ' not in split), None)
        if unsplit:
            return await ctx.error_reply(
                "Couldn't parse the reaction role `{}` into the form `emoji role`.".format(unsplit)
            )

        # Now go through and extract the emojis and roles
        # TODO: Handle duplicate emojis?
        # TODO: Error handling on the roles, make sure we can actually add them
        reactions = {}
        for split in splits:
            emojistr, rolestr = split.split(maxsplit=1)
            # Parse emoji
            # TODO: Custom emoji handler, probably store in a PartialEmoji
            if ':' in emojistr:
                return ctx.error_reply(
                    "Sorry, at this time we only support built-in emojis! Custom emoji support coming soon."
                )
            emoji = emojistr

            # Parse role
            # TODO: More graceful error handling
            role = await ctx.find_role(rolestr, interactive=True, allow_notfound=False)

            reactions[emoji] = role

        # TODO: Parse any provided settings, and pass them to the data constructor

        # Create the ReactionRoleMessage
        rmsg = ReactionRoleMessage.create(
            message.id,
            message.guild.id,
            message.channel.id
        )

        # Insert the reaction data directly
        # TODO: Again consider emoji setting data here, for common settings?
        # TODO: Will need to be changed for custom emojis
        reaction_role_reactions.insert_many(
            *((message.id, role.id, emoji) for emoji, role in reactions.items()),
            insert_keys=('messageid', 'roleid', 'emoji_name')
        )

        # Refresh the ReactionRoleMessage to pick up the new reactions
        rmsg.refresh()

        # Ack the creation
        await ctx.embed_reply(
            (
                "Created `{}` new reaction roles.\n"
                "Please add the reactions to [the message]({}) to make them available for use!".format(
                    len(reactions), rmsg.message_link
                )
            )
        )
