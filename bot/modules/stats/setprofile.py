"""
Provides a command to update a member's profile badges.
"""
import string
import discord

from cmdClient.lib import SafeCancellation
from cmdClient.checks import in_guild
from wards import guild_moderator

from .data import profile_tags
from .module import module


MAX_TAGS = 10
MAX_LENGTH = 30


@module.cmd(
    "setprofile",
    group="Personal Settings",
    desc="Set or update your study profile tags.",
    aliases=('editprofile', 'mytags'),
    flags=('clear', 'for')
)
@in_guild()
async def cmd_setprofile(ctx, flags):
    """
    Usage``:
        {prefix}setprofile <tag>, <tag>, <tag>, ...
        {prefix}setprofile <id> <new tag>
        {prefix}setprofile --clear [--for @user]
    Description:
        Set or update the tags appearing in your study server profile.

        Moderators can clear a user's tags with `--clear --for @user`.
    Examples``:
        {prefix}setprofile Mathematics, Bioloyg, Medicine, Undergraduate, Europe
        {prefix}setprofile 2 Biology
        {prefix}setprofile --clear
    """
    if flags['clear']:
        if flags['for']:
            # Moderator-clearing a user's tags
            # First check moderator permissions
            if not await guild_moderator.run(ctx):
                return await ctx.error_reply(
                    "You need to be a server moderator to use this!"
                )

            # Check input and extract users to clear for
            if not (users := ctx.msg.mentions):
                # Show moderator usage
                return await ctx.error_reply(
                    f"**Usage:** `{ctx.best_prefix}setprofile --clear --for @user`\n"
                    f"**Example:** {ctx.best_prefix}setprofile --clear --for {ctx.author.mention}"
                )

            # Clear the tags
            profile_tags.delete_where(
                guildid=ctx.guild.id,
                userid=[user.id for user in users]
            )

            # Ack the moderator
            await ctx.embed_reply(
                "Profile tags cleared!"
            )
        else:
            # The author wants to clear their own tags

            # First delete the tags, save the rows for reporting
            rows = profile_tags.delete_where(
                guildid=ctx.guild.id,
                userid=ctx.author.id
            )

            # Ack the user
            if not rows:
                await ctx.embed_reply(
                    "You don't have any profile tags to clear!"
                )
            else:
                embed = discord.Embed(
                    colour=discord.Colour.green(),
                    description="Successfully cleared your profile!"
                )
                embed.add_field(
                    name="Removed tags",
                    value='\n'.join(row['tag'].upper() for row in rows)
                )
                await ctx.reply(embed=embed)
    elif ctx.args:
        if len(splits := ctx.args.split(maxsplit=1)) > 1 and splits[0].isdigit():
            # Assume we are editing the provided id
            tagid = int(splits[0])
            if tagid > MAX_TAGS:
                return await ctx.error_reply(
                    f"Sorry, you can have a maximum of `{MAX_TAGS}` tags!"
                )
            if tagid == 0:
                return await ctx.error_reply("Tags start at `1`!")

            # Retrieve the user's current taglist
            rows = profile_tags.select_where(
                guildid=ctx.guild.id,
                userid=ctx.author.id,
                _extra="ORDER BY tagid ASC"
            )

            # Parse and validate provided new content
            content = splits[1].strip().upper()
            validate_tag(content)

            if tagid > len(rows):
                # Trying to edit a tag that doesn't exist yet
                # Just create it instead
                profile_tags.insert(
                    guildid=ctx.guild.id,
                    userid=ctx.author.id,
                    tag=content
                )

                # Ack user
                await ctx.reply(
                    embed=discord.Embed(title="Tag created!", colour=discord.Colour.green())
                )
            else:
                # Get the row id to update
                to_edit = rows[tagid - 1]['tagid']

                # Update the tag
                profile_tags.update_where(
                    {'tag': content},
                    tagid=to_edit
                )

                # Ack user
                embed = discord.Embed(
                    colour=discord.Colour.green(),
                    title="Tag updated!"
                )
                await ctx.reply(embed=embed)
        else:
            # Assume the arguments are a comma separated list of badges
            # Parse and validate
            to_add = [split.strip().upper() for line in ctx.args.splitlines() for split in line.split(',')]
            to_add = [split.replace('<3', '❤️') for split in to_add if split]
            if not to_add:
                return await ctx.error_reply("No valid tags given, nothing to do!")

            validate_tag(*to_add)

            if len(to_add) > MAX_TAGS:
                return await ctx.error_reply(f"You can have a maximum of {MAX_TAGS} tags!")

            # Remove the existing badges
            deleted_rows = profile_tags.delete_where(
                guildid=ctx.guild.id,
                userid=ctx.author.id
            )

            # Insert the new tags
            profile_tags.insert_many(
                *((ctx.guild.id, ctx.author.id, tag) for tag in to_add),
                insert_keys=('guildid', 'userid', 'tag')
            )

            # Ack with user
            embed = discord.Embed(
                colour=discord.Colour.green(),
                title="Profile tags updated!"
            )
            embed.add_field(
                name="New tags",
                value='\n'.join(to_add)
            )
            if deleted_rows:
                embed.add_field(
                    name="Replaced tags",
                    value='\n'.join(row['tag'].upper() for row in deleted_rows),
                    inline=False
                )
            if len(to_add) == 1:
                embed.set_footer(
                    text=f"TIP: Add multiple tags with {ctx.best_prefix}setprofile tag1, tag2, ..."
                )
            await ctx.reply(embed=embed)
    else:
        # No input was provided
        # Show usage and exit
        embed = discord.Embed(
            colour=discord.Colour.red(),
            description=(
                "Edit your study profile "
                "tags so other people can see what you do!"
            )
        )
        embed.add_field(
            name="Usage",
            value=(
                f"`{ctx.best_prefix}setprofile <tag>, <tag>, <tag>, ...`\n"
                f"`{ctx.best_prefix}setprofile <id> <new tag>`"
            )
        )
        embed.add_field(
            name="Examples",
            value=(
                f"`{ctx.best_prefix}setprofile Mathematics, Bioloyg, Medicine, Undergraduate, Europe`\n"
                f"`{ctx.best_prefix}setprofile 2 Biology`"
            ),
            inline=False
        )
        await ctx.reply(embed=embed)


def validate_tag(*content):
    for content in content:
        if not set(content.replace('❤️', '')).issubset(string.printable):
            raise SafeCancellation(
                f"Invalid tag `{content}`!\n"
                "Tags may only contain alphanumeric and punctuation characters."
            )
        if len(content) > MAX_LENGTH:
            raise SafeCancellation(
                f"Provided tag is too long! Please keep your tags shorter than {MAX_LENGTH} characters."
            )
