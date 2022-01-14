import asyncio
import discord
from LionContext import LionContext
from cmdClient.lib import UserCancelled, ResponseTimedOut

import datetime
from cmdClient import lib
from .lib import paginate_list

# TODO: Interactive locks
cancel_emoji = '❌'
number_emojis = (
    '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣'
)


async def discord_shield(coro):
    try:
        await coro
    except discord.HTTPException:
        pass


@LionContext.util
async def cancellable(ctx, msg, add_reaction=True, cancel_message=None, timeout=300):
    """
    Add a cancellation reaction to the given message.
    Pressing the reaction triggers cancellation of the original context, and a UserCancelled-style error response.
    """
    # TODO: Not consistent with the exception driven flow, make a decision here?
    # Add reaction
    if add_reaction and cancel_emoji not in (str(r.emoji) for r in msg.reactions):
        try:
            await msg.add_reaction(cancel_emoji)
        except discord.HTTPException:
            return

    # Define cancellation function
    async def _cancel():
        try:
            await ctx.client.wait_for(
                'reaction_add',
                timeout=timeout,
                check=lambda r, u: (u == ctx.author
                                    and r.message == msg
                                    and str(r.emoji) == cancel_emoji)
            )
        except asyncio.TimeoutError:
            pass
        else:
            await ctx.client.active_command_response_cleaner(ctx)
            if cancel_message:
                await ctx.error_reply(cancel_message)
            else:
                try:
                    await ctx.msg.add_reaction(cancel_emoji)
                except discord.HTTPException:
                    pass
            [task.cancel() for task in ctx.tasks]

    # Launch cancellation task
    task = asyncio.create_task(_cancel())
    ctx.tasks.append(task)
    return task


@LionContext.util
async def listen_for(ctx, allowed_input=None, timeout=120, lower=True, check=None):
    """
    Listen for a one of a particular set of input strings,
    sent in the current channel by `ctx.author`.
    When found, return the message containing them.

    Parameters
    ----------
    allowed_input: Union(List(str), None)
        List of strings to listen for.
        Allowed to be `None` precisely when a `check` function is also supplied.
    timeout: int
        Number of seconds to wait before timing out.
    lower: bool
        Whether to shift the allowed and message strings to lowercase before checking.
    check: Function(message) -> bool
        Alternative custom check function.

    Returns: discord.Message
        The message that was matched.

    Raises
    ------
    cmdClient.lib.ResponseTimedOut:
        Raised when no messages matching the given criteria are detected in `timeout` seconds.
    """
    # Generate the check if it hasn't been provided
    if not check:
        # Quick check the arguments are sane
        if not allowed_input:
            raise ValueError("allowed_input and check cannot both be None")

        # Force a lower on the allowed inputs
        allowed_input = [s.lower() for s in allowed_input]

        # Create the check function
        def check(message):
            result = (message.author == ctx.author)
            result = result and (message.channel == ctx.ch)
            result = result and ((message.content.lower() if lower else message.content) in allowed_input)
            return result

    # Wait for a matching message, catch and transform the timeout
    try:
        message = await ctx.client.wait_for('message', check=check, timeout=timeout)
    except asyncio.TimeoutError:
        raise ResponseTimedOut("Session timed out waiting for user response.") from None

    return message


@LionContext.util
async def selector(ctx, header, select_from, timeout=120, max_len=20):
    """
    Interactive routine to prompt the `ctx.author` to select an item from a list.
    Returns the list index that was selected.

    Parameters
    ----------
    header: str
        String to put at the top of each page of selection options.
        Intended to be information about the list the user is selecting from.
    select_from: List(str)
        The list of strings to select from.
    timeout: int
        The number of seconds to wait before throwing `ResponseTimedOut`.
    max_len: int
        The maximum number of items to display on each page.
        Decrease this if the items are long, to avoid going over the char limit.

    Returns
    -------
    int:
        The index of the list entry selected by the user.

    Raises
    ------
    cmdClient.lib.UserCancelled:
        Raised if the user manually cancels the selection.
    cmdClient.lib.ResponseTimedOut:
        Raised if the user fails to respond to the selector within `timeout` seconds.
    """
    # Handle improper arguments
    if len(select_from) == 0:
        raise ValueError("Selection list passed to `selector` cannot be empty.")

    # Generate the selector pages
    footer = "Please reply with the number of your selection, or press {} to cancel.".format(cancel_emoji)
    list_pages = paginate_list(select_from, block_length=max_len)
    pages = ["\n".join([header, page, footer]) for page in list_pages]

    # Post the pages in a paged message
    out_msg = await ctx.pager(pages, add_cancel=True)
    cancel_task = await ctx.cancellable(out_msg, add_reaction=False, timeout=None)

    if len(select_from) <= 5:
        for i, _ in enumerate(select_from):
            asyncio.create_task(discord_shield(out_msg.add_reaction(number_emojis[i])))

    # Build response tasks
    valid_input = [str(i+1) for i in range(0, len(select_from))] + ['c', 'C']
    listen_task = asyncio.create_task(ctx.listen_for(valid_input, timeout=None))
    emoji_task = asyncio.create_task(ctx.client.wait_for(
        'reaction_add',
        check=lambda r, u: (u == ctx.author
                            and r.message == out_msg
                            and str(r.emoji) in number_emojis)
    ))
    # Wait for the response tasks
    done, pending = await asyncio.wait(
        (listen_task, emoji_task),
        timeout=timeout,
        return_when=asyncio.FIRST_COMPLETED
    )

    # Cleanup
    try:
        await out_msg.delete()
    except discord.HTTPException:
        pass

    # Handle different return cases
    if listen_task in done:
        emoji_task.cancel()

        result_msg = listen_task.result()
        try:
            await result_msg.delete()
        except discord.HTTPException:
            pass
        if result_msg.content.lower() == 'c':
            raise UserCancelled("Selection cancelled!")
        result = int(result_msg.content) - 1
    elif emoji_task in done:
        listen_task.cancel()

        reaction, _ = emoji_task.result()
        result = number_emojis.index(str(reaction.emoji))
    elif cancel_task in done:
        # Manually cancelled case.. the current task should have been cancelled
        # Raise UserCancelled in case the task wasn't cancelled for some reason
        raise UserCancelled("Selection cancelled!")
    elif not done:
        # Timeout case
        raise ResponseTimedOut("Selector timed out waiting for a response.")

    # Finally cancel the canceller and return the provided index
    cancel_task.cancel()
    return result


@LionContext.util
async def pager(ctx, pages, locked=True, start_at=0, add_cancel=False, **kwargs):
    """
    Shows the user each page from the provided list `pages` one at a time,
    providing reactions to page back and forth between pages.
    This is done asynchronously, and returns after displaying the first page.

    Parameters
    ----------
    pages: List(Union(str, discord.Embed))
        A list of either strings or embeds to display as the pages.
    locked: bool
        Whether only the `ctx.author` should be able to use the paging reactions.
    kwargs: ...
        Remaining keyword arguments are transparently passed to the reply context method.

    Returns: discord.Message
        This is the output message, returned for easy deletion.
    """
    # Handle broken input
    if len(pages) == 0:
        raise ValueError("Pager cannot page with no pages!")

    # Post first page. Method depends on whether the page is an embed or not.
    if isinstance(pages[start_at], discord.Embed):
        out_msg = await ctx.reply(embed=pages[start_at], **kwargs)
    else:
        out_msg = await ctx.reply(pages[start_at], **kwargs)

    # Run the paging loop if required
    if len(pages) > 1:
        task = asyncio.create_task(_pager(ctx, out_msg, pages, locked, start_at, add_cancel, **kwargs))
        ctx.tasks.append(task)
    elif add_cancel:
        await out_msg.add_reaction(cancel_emoji)

    # Return the output message
    return out_msg


async def _pager(ctx, out_msg, pages, locked, start_at, add_cancel, **kwargs):
    """
    Asynchronous initialiser and loop for the `pager` utility above.
    """
    # Page number
    page = start_at

    # Add reactions to the output message
    next_emoji = "▶"
    prev_emoji = "◀"

    try:
        await out_msg.add_reaction(prev_emoji)
        if add_cancel:
            await out_msg.add_reaction(cancel_emoji)
        await out_msg.add_reaction(next_emoji)
    except discord.Forbidden:
        # We don't have permission to add paging emojis
        # Die as gracefully as we can
        if ctx.guild:
            perms = ctx.ch.permissions_for(ctx.guild.me)
            if not perms.add_reactions:
                await ctx.error_reply(
                    "Cannot page results because I do not have the `add_reactions` permission!"
                )
            elif not perms.read_message_history:
                await ctx.error_reply(
                    "Cannot page results because I do not have the `read_message_history` permission!"
                )
            else:
                await ctx.error_reply(
                    "Cannot page results due to insufficient permissions!"
                )
        else:
            await ctx.error_reply(
                "Cannot page results!"
            )
        return

    # Check function to determine whether a reaction is valid
    def reaction_check(reaction, user):
        result = reaction.message.id == out_msg.id
        result = result and str(reaction.emoji) in [next_emoji, prev_emoji]
        result = result and not (user.id == ctx.client.user.id)
        result = result and not (locked and user != ctx.author)
        return result

    # Check function to determine if message has a page number
    def message_check(message):
        result = message.channel.id == ctx.ch.id
        result = result and not (locked and message.author != ctx.author)
        result = result and message.content.lower().startswith('p')
        result = result and message.content[1:].isdigit()
        result = result and 1 <= int(message.content[1:]) <= len(pages)
        return result

    # Begin loop
    while True:
        # Wait for a valid reaction or message, break if we time out
        reaction_task = asyncio.create_task(
            ctx.client.wait_for('reaction_add', check=reaction_check)
        )
        message_task = asyncio.create_task(
            ctx.client.wait_for('message', check=message_check)
        )
        done, pending = await asyncio.wait(
            (reaction_task, message_task),
            timeout=300,
            return_when=asyncio.FIRST_COMPLETED
        )
        if done:
            if reaction_task in done:
                # Cancel the message task and collect the reaction result
                message_task.cancel()
                reaction, user = reaction_task.result()

                # Attempt to remove the user's reaction, silently ignore errors
                asyncio.ensure_future(out_msg.remove_reaction(reaction.emoji, user))

                # Change the page number
                page += 1 if reaction.emoji == next_emoji else -1
                page %= len(pages)
            elif message_task in done:
                # Cancel the reaction task and collect the message result
                reaction_task.cancel()
                message = message_task.result()

                # Attempt to delete the user's message, silently ignore errors
                asyncio.ensure_future(message.delete())

                # Move to the correct page
                page = int(message.content[1:]) - 1

            # Edit the message with the new page
            active_page = pages[page]
            if isinstance(active_page, discord.Embed):
                await out_msg.edit(embed=active_page, **kwargs)
            else:
                await out_msg.edit(content=active_page, **kwargs)
        else:
            # No tasks finished, so we must have timed out, or had an exception.
            # Break the loop and clean up
            break

    # Clean up by removing the reactions
    try:
        await out_msg.clear_reactions()
    except discord.Forbidden:
        try:
            await out_msg.remove_reaction(next_emoji, ctx.client.user)
            await out_msg.remove_reaction(prev_emoji, ctx.client.user)
        except discord.NotFound:
            pass
    except discord.NotFound:
        pass


@LionContext.util
async def input(ctx, msg="", timeout=120):
    """
    Listen for a response in the current channel, from ctx.author.
    Returns the response from ctx.author, if it is provided.
    Parameters
    ----------
    msg: string
        Allows a custom input message to be provided.
        Will use default message if not provided.
    timeout: int
        Number of seconds to wait before timing out.
    Raises
    ------
    cmdClient.lib.ResponseTimedOut:
        Raised when ctx.author does not provide a response before the function times out.
    """
    # Deliver prompt
    offer_msg = await ctx.reply(msg or "Please enter your input.")

    # Criteria for the input message
    def checks(m):
        return m.author == ctx.author and m.channel == ctx.ch

    # Listen for the reply
    try:
        result_msg = await ctx.client.wait_for("message", check=checks, timeout=timeout)
    except asyncio.TimeoutError:
        raise ResponseTimedOut("Session timed out waiting for user response.") from None

    result = result_msg.content

    # Attempt to delete the prompt and reply messages
    try:
        await offer_msg.delete()
        await result_msg.delete()
    except Exception:
        pass

    return result


@LionContext.util
async def ask(ctx, msg, timeout=30, use_msg=None, del_on_timeout=False):
    """
    Ask ctx.author a yes/no question.
    Returns 0 if ctx.author answers no
    Returns 1 if ctx.author answers yes
    Parameters
    ----------
    msg: string
        Adds the question to the message string.
        Requires an input.
    timeout: int
        Number of seconds to wait before timing out.
    use_msg: string
        A completely custom string to use instead of the default string.
    del_on_timeout: bool
        Whether to delete the question if it times out.
    Raises
    ------
    Nothing
    """
    out = "{} {}".format(msg, "`y(es)`/`n(o)`")

    offer_msg = use_msg or await ctx.reply(out)
    if use_msg and msg:
        await use_msg.edit(content=msg)

    result_msg = await ctx.listen_for(["y", "yes", "n", "no"], timeout=timeout)

    if result_msg is None:
        if del_on_timeout:
            try:
                await offer_msg.delete()
            except Exception:
                pass
        return None
    result = result_msg.content.lower()
    try:
        if not use_msg:
            await offer_msg.delete()
        await result_msg.delete()
    except Exception:
        pass
    if result in ["n", "no"]:
        return 0
    return 1

# this reply() will be overide baseContext's reply with LionContext's, whcih can 
# hook pre_execution of any util.
# Using this system, Module now have much power to change Context's utils
@LionContext.util
async def reply(ctx, content=None, allow_everyone=False, **kwargs):
    """
    Helper function to reply in the current channel.
    """
    if not allow_everyone:
        if content:
            content = lib.sterilise_content(content)
        
    message = await ctx.ch.send(content=content, **kwargs)
    ctx.sent_messages.append(message)
    return message


# this reply() will be overide baseContext's reply
@LionContext.util
async def error_reply(ctx, error_str):
    """
    Notify the user of a user level error.
    Typically, this will occur in a red embed, posted in the command channel.
    """
    embed = discord.Embed(
        colour=discord.Colour.red(),
        description=error_str,
        timestamp=datetime.datetime.utcnow()
    )
    try:
        message = await ctx.ch.send(embed=embed)
        ctx.sent_messages.append(message)
        return message
    except discord.Forbidden:
        message = await ctx.reply(error_str)
        ctx.sent_messages.append(message)
        return message