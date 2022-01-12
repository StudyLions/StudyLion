from cmdClient import Context
from cmdClient.checks import in_guild

from core import Lion
from wards import is_guild_admin

from ..module import module


MAX_TAG_LENGTH = 10


@module.cmd(
    "now",
    group="Statistics",
    desc="What are you working on?",
    aliases=('studying', 'workingon'),
    flags=('clear', 'new')
)
@in_guild()
async def cmd_now(ctx: Context, flags):
    """
    Usage``:
        {prefix}now [tag]
        {prefix}now @mention
        {prefix}now --clear
    Description:
        Describe the subject or goal you are working on this session with, for example, `{prefix}now Maths`.
        Mention someone else to view what they are working on!
    Flags::
        clear: Remove your current tag.
    Examples:
        > {prefix}now Biology
        > {prefix}now {ctx.author.mention}
    """
    if flags['clear']:
        if ctx.msg.mentions and is_guild_admin(ctx.author):
            # Assume an admin is trying to clear another user's tag
            for target in ctx.msg.mentions:
                lion = Lion.fetch(ctx.guild.id, target.id)
                if lion.session:
                    lion.session.data.tag = None

            if len(ctx.msg.mentions) == 1:
                await ctx.embed_reply(
                    f"Cleared session tags for {ctx.msg.mentions[0].mention}."
                )
            else:
                await ctx.embed_reply(
                    f"Cleared session tags for:\n{', '.join(target.mention for target in ctx.msg.mentions)}."
                )
        else:
            # Assume the user is clearing their own session tag
            if (session := ctx.alion.session):
                session.data.tag = None
                await ctx.embed_reply(
                    "Removed your session study tag!"
                )
            else:
                await ctx.embed_reply(
                    "You aren't studying right now, so there is nothing to clear!"
                )
    elif ctx.args:
        if ctx.msg.mentions:
            # Assume peeking at user's current session

            # Smoll easter egg
            target = ctx.msg.mentions[0]
            if target == ctx.guild.me:
                student_count, guild_count = ctx.client.data.current_sessions.select_one_where(
                    select_columns=("COUNT(*) AS studying_count", "COUNT(DISTINCT(guildid)) AS guild_count"),
                )
                if ctx.alion.session:
                    if (tag := ctx.alion.session.data.tag):
                        tail = f"Good luck with your **{tag}**!"
                    else:
                        tail = "Good luck with your study, I believe in you!"
                else:
                    tail = "Do you want to join? Hop in a study channel and let's get to work!"
                return await ctx.embed_reply(
                    "Thanks for asking!\n"
                    f"I'm just helping out the **{student_count}** "
                    f"dedicated people currently working across **{guild_count}** fun communities!\n"
                    f"{tail}"
                )

            lion = Lion.fetch(ctx.guild.id, target.id)
            if not lion.session:
                await ctx.embed_reply(
                    f"{target.mention} isn't working right now!"
                )
            else:
                duration = lion.session.duration
                if duration > 3600:
                    dur_str = "{}h {}m".format(
                        int(duration // 3600),
                        int((duration % 3600) // 60)
                    )
                else:
                    dur_str = "{} minutes".format(int((duration % 3600) // 60))

                if not lion.session.data.tag:
                    await ctx.embed_reply(
                        f"{target.mention} has been working in <#{lion.session.data.channelid}> for **{dur_str}**!"
                    )
                else:
                    await ctx.embed_reply(
                        f"{target.mention} has been working on **{lion.session.data.tag}**"
                        f" in <#{lion.session.data.channelid}> for **{dur_str}**!"
                    )
        else:
            # Assume setting tag
            tag = ctx.args

            if not (session := ctx.alion.session):
                return await ctx.error_reply(
                    "You aren't working right now! Join a study channel and try again!"
                )

            if len(tag) > MAX_TAG_LENGTH:
                return await ctx.error_reply(
                    f"Please keep your tag under `{MAX_TAG_LENGTH}` characters long!"
                )

            old_tag = session.data.tag
            session.data.tag = tag
            if old_tag:
                await ctx.embed_reply(
                    f"You have updated your session study tag. Good luck with **{tag}**!"
                )
            else:
                await ctx.embed_reply(
                    "You have set your session study tag!\nIt will be reset when you leave, or join another channel.\n"
                    f"Good luck with **{tag}**!"
                )
    else:
        # View current session, stats, and guide.
        if (session := ctx.alion.session):
            duration = session.duration
            if duration > 3600:
                dur_str = "{}h {}m".format(
                    int(duration // 3600),
                    int((duration % 3600) // 60)
                )
            else:
                dur_str = "{} minutes".format(int((duration % 3600) / 60))
            if not session.data.tag:
                await ctx.embed_reply(
                    f"You have been working in <#{session.data.channelid}> for **{dur_str}**!\n"
                    f"Describe what you are working on with "
                    f"`{ctx.best_prefix}now <tag>`, e.g. `{ctx.best_prefix}now Maths`"
                )
            else:
                await ctx.embed_reply(
                    f"You have been working on **{session.data.tag}**"
                    f" in <#{session.data.channelid}> for **{dur_str}**!"
                )
        else:
            await ctx.embed_reply(
                f"Join a study channel and describe what you are working on with e.g. `{ctx.best_prefix}now Maths`"
            )

        # TODO: Favourite tags listing
        # Get tag history ranking top 5
        # If there are any, display top 5
        # Otherwise do nothing
        ...
