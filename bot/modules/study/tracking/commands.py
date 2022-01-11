from cmdClient import Context
from cmdClient.checks import in_guild

from core import Lion

from ..module import module


MAX_TAG_LENGTH = 10


@module.cmd(
    "now",
    group="Statistics",
    desc="What are you working on?",
    aliases=('studying', 'workingon')
)
@in_guild()
async def cmd_now(ctx: Context):
    """
    Usage``:
        {prefix}now [tag]
        {prefix}now @mention
    Description:
        Describe the subject or goal you are working on this session with, for example, `{prefix}now Maths`.
        Mention someone else to view what they are working on!
    Examples:
        > {prefix}now Biology
        > {prefix}now {ctx.author.mention}
    """
    if ctx.args:
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
                    f"hardworking students currently studying across **{guild_count}** fun communities!\n"
                    f"{tail}"
                )

            lion = Lion.fetch(ctx.guild.id, target.id)
            if not lion.session:
                await ctx.embed_reply(
                    f"{target.mention} isn't studying right now!"
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
                        f"{target.mention} has been studying in <#{lion.session.data.channelid}> for **{dur_str}**!"
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
                    "You aren't studying right now! Join a study channel and try again!"
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
        lines = []
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
                    f"You have been studying in <#{session.data.channelid}> for **{dur_str}**!"
                )
                lines.append(
                    f"Describe what you are working on with "
                    "`{ctx.best_prefix}now <tag>`, e.g. `{ctx.best_prefix}now Maths`!"
                )
            else:
                await ctx.embed_reply(
                    f"You have been working on **{session.data.tag}**"
                    f" in <#{session.data.channelid}> for **{dur_str}**!"
                )
        else:
            await ctx.embed_reply(
                f"Join a study channel and describe what you are working on with e.g. `{ctx.best_prefix}now Maths!`"
            )

        # TODO: Favourite tags listing
        # Get tag history ranking top 5
        # If there are any, display top 5
        # Otherwise do nothing
        ...
