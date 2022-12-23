"""
System admin submodule providing an interface for managing the globally blacklisted guilds and users.

NOTE: Not shard-safe, and will not update across shards.
"""
import discord
from cmdClient.checks import is_owner
from cmdClient.lib import ResponseTimedOut

from meta.sharding import sharded

from .module import module


@module.cmd(
    "guildblacklist",
    desc="View/add/remove blacklisted guilds.",
    group="Bot Admin",
    flags=('remove',)
)
@is_owner()
async def cmd_guildblacklist(ctx, flags):
    """
    Usage``:
        {prefix}guildblacklist
        {prefix}guildblacklist guildid, guildid, guildid
        {prefix}guildblacklist --remove guildid, guildid, guildid
    Description:
        View, add, or remove guilds from the blacklist.
    """
    blacklist = ctx.client.guild_blacklist()

    if ctx.args:
        # guildid parsing
        items = [item.strip() for item in ctx.args.split(',')]
        if any(not item.isdigit() for item in items):
            return await ctx.error_reply(
                "Please provide guilds as comma separated guild ids."
            )

        guildids = set(int(item) for item in items)

        if flags['remove']:
            # Handle removing from the blacklist
            # First make sure that all the guildids are in the blacklist
            difference = [guildid for guildid in guildids if guildid not in blacklist]
            if difference:
                return await ctx.error_reply(
                    "The following guildids are not in the blacklist! No guilds were removed.\n`{}`".format(
                        '`, `'.join(str(guildid) for guildid in difference)
                    )
                )

            # Remove the guilds from the data blacklist
            ctx.client.data.global_guild_blacklist.delete_where(
                guildid=list(guildids)
            )

            # Ack removal
            await ctx.embed_reply(
                "You have removed the following guilds from the guild blacklist.\n`{}`".format(
                    "`, `".join(str(guildid) for guildid in guildids)
                )
            )
        else:
            # Handle adding to the blacklist
            to_add = [guildid for guildid in guildids if guildid not in blacklist]
            if not to_add:
                return await ctx.error_reply(
                    "All of the provided guilds are already blacklisted!"
                )

            # Prompt for reason
            try:
                reason = await ctx.input("Please enter the reasons these guild(s) are being blacklisted:")
            except ResponseTimedOut:
                raise ResponseTimedOut("Reason prompt timed out, no guilds were blacklisted.")

            # Add to the blacklist
            ctx.client.data.global_guild_blacklist.insert_many(
                *((guildid, ctx.author.id, reason) for guildid in to_add),
                insert_keys=('guildid', 'ownerid', 'reason')
            )

            # Leave freshly blacklisted guilds, accounting for shards
            to_leave = []
            for guildid in to_add:
                guild = ctx.client.get_guild(guildid)
                if not guild and sharded:
                    try:
                        guild = await ctx.client.fetch_guild(guildid)
                    except discord.HTTPException:
                        pass
                if guild:
                    to_leave.append(guild)

            for guild in to_leave:
                await guild.leave()

            if to_leave:
                left_str = "\nConsequently left the following guild(s):\n**{}**".format(
                    '**\n**'.join(guild.name for guild in to_leave)
                )
            else:
                left_str = ""

            # Ack the addition
            await ctx.embed_reply(
                "Added the following guild(s) to the blacklist:\n`{}`\n{}".format(
                    '`, `'.join(str(guildid) for guildid in to_add),
                    left_str
                )
            )

        # Refresh the cached blacklist after modification
        ctx.client.guild_blacklist.cache_clear()
        ctx.client.guild_blacklist()
    else:
        # Display the current blacklist
        # First fetch the full blacklist data
        rows = ctx.client.data.global_guild_blacklist.select_where()
        if not rows:
            await ctx.reply("There are no blacklisted guilds!")
        else:
            # Text blocks for each blacklisted guild
            lines = [
                "`{}` blacklisted by <@{}> at <t:{:.0f}>\n**Reason:** {}".format(
                    row['guildid'],
                    row['ownerid'],
                    row['created_at'].timestamp(),
                    row['reason']
                ) for row in sorted(rows, key=lambda row: row['created_at'].timestamp(), reverse=True)
            ]

            # Split lines across pages
            blocks = []
            block_len = 0
            block_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                line_len = len(line)

                if block_len + line_len > 2000:
                    if block_lines:
                        # Flush block, run line again on next page
                        blocks.append('\n'.join(block_lines))
                        block_lines = []
                        block_len = 0
                    else:
                        # Too long for the block, but empty block!
                        # Truncate
                        blocks.append(line[:2000])
                        i += 1
                else:
                    block_lines.append(line)
                    i += 1

            if block_lines:
                # Flush block
                blocks.append('\n'.join(block_lines))

            # Build embed pages
            pages = [
                discord.Embed(
                    title="Blacklisted Guilds",
                    description=block,
                    colour=discord.Colour.orange()
                ) for block in blocks
            ]
            page_count = len(blocks)
            if page_count > 1:
                for i, page in enumerate(pages):
                    page.set_footer(text="Page {}/{}".format(i + 1, page_count))

            # Finally, post
            await ctx.pager(pages)


@module.cmd(
    "userblacklist",
    desc="View/add/remove blacklisted users.",
    group="Bot Admin",
    flags=('remove',)
)
@is_owner()
async def cmd_userblacklist(ctx, flags):
    """
    Usage``:
        {prefix}userblacklist
        {prefix}userblacklist userid, userid, userid
        {prefix}userblacklist --remove userid, userid, userid
    Description:
        View, add, or remove users from the blacklist.
    """
    blacklist = ctx.client.user_blacklist()

    if ctx.args:
        # userid parsing
        items = [item.strip('<@!&> ') for item in ctx.args.split(',')]
        if any(not item.isdigit() for item in items):
            return await ctx.error_reply(
                "Please provide users as comma seprated user ids or mentions."
            )

        userids = set(int(item) for item in items)

        if flags['remove']:
            # Handle removing from the blacklist
            # First make sure that all the userids are in the blacklist
            difference = [userid for userid in userids if userid not in blacklist]
            if difference:
                return await ctx.error_reply(
                    "The following userids are not in the blacklist! No users were removed.\n`{}`".format(
                        '`, `'.join(str(userid) for userid in difference)
                    )
                )

            # Remove the users from the data blacklist
            ctx.client.data.global_user_blacklist.delete_where(
                userid=list(userids)
            )

            # Ack removal
            await ctx.embed_reply(
                "You have removed the following users from the user blacklist.\n{}".format(
                    ", ".join('<@{}>'.format(userid) for userid in userids)
                )
            )
        else:
            # Handle adding to the blacklist
            to_add = [userid for userid in userids if userid not in blacklist]
            if not to_add:
                return await ctx.error_reply(
                    "All of the provided users are already blacklisted!"
                )

            # Prompt for reason
            try:
                reason = await ctx.input("Please enter the reasons these user(s) are being blacklisted:")
            except ResponseTimedOut:
                raise ResponseTimedOut("Reason prompt timed out, no users were blacklisted.")

            # Add to the blacklist
            ctx.client.data.global_user_blacklist.insert_many(
                *((userid, ctx.author.id, reason) for userid in to_add),
                insert_keys=('userid', 'ownerid', 'reason')
            )

            # Ack the addition
            await ctx.embed_reply(
                "Added the following user(s) to the blacklist:\n{}".format(
                    ', '.join('<@{}>'.format(userid) for userid in to_add)
                )
            )

        # Refresh the cached blacklist after modification
        ctx.client.user_blacklist.cache_clear()
        ctx.client.user_blacklist()
    else:
        # Display the current blacklist
        # First fetch the full blacklist data
        rows = ctx.client.data.global_user_blacklist.select_where()
        if not rows:
            await ctx.reply("There are no blacklisted users!")
        else:
            # Text blocks for each blacklisted user
            lines = [
                "<@{}> blacklisted by <@{}> at <t:{:.0f}>\n**Reason:** {}".format(
                    row['userid'],
                    row['ownerid'],
                    row['created_at'].timestamp(),
                    row['reason']
                ) for row in sorted(rows, key=lambda row: row['created_at'].timestamp(), reverse=True)
            ]

            # Split lines across pages
            blocks = []
            block_len = 0
            block_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                line_len = len(line)

                if block_len + line_len > 2000:
                    if block_lines:
                        # Flush block, run line again on next page
                        blocks.append('\n'.join(block_lines))
                        block_lines = []
                        block_len = 0
                    else:
                        # Too long for the block, but empty block!
                        # Truncate
                        blocks.append(line[:2000])
                        i += 1
                else:
                    block_lines.append(line)
                    i += 1

            if block_lines:
                # Flush block
                blocks.append('\n'.join(block_lines))

            # Build embed pages
            pages = [
                discord.Embed(
                    title="Blacklisted Users",
                    description=block,
                    colour=discord.Colour.orange()
                ) for block in blocks
            ]
            page_count = len(blocks)
            if page_count > 1:
                for i, page in enumerate(pages):
                    page.set_footer(text="Page {}/{}".format(i + 1, page_count))

            # Finally, post
            await ctx.pager(pages)
