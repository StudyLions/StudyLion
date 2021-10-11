import discord
from cmdClient.checks import in_guild

from .module import module
from .rooms import Room


@module.cmd(
    name="rent",
    desc="Rent a private study room with your friends!",
    group="Productivity",
    aliases=('add',)
)
@in_guild()
async def cmd_rent(ctx):
    """
    Usage``:
        {prefix}rent
        {prefix}rent @user1 @user2 @user3 ...
        {prefix}rent add @user1 @user2 @user3 ...
        {prefix}rent remove @user1 @user2 @user3 ...
    Description:
        Rent a private voice channel for 24 hours,\
            and invite up to `{ctx.guild_settings.rent_member_limit.value}` mentioned users.
        Use `{prefix}rent add` and `{prefix}rent remove` to give/revoke access to your room.

        *Renting a private channel costs `{ctx.guild_settings.rent_room_price.value} LC`.*
    """
    # TODO: More gracefully handle unexpected channel deletion

    # Check if the category is set up
    if not ctx.guild_settings.rent_category.value:
        return await ctx.error_reply(
            "The private study channel category has not been set up! Please come back later."
        )

    # Fetch the members' room, if it exists
    room = Room.fetch(ctx.guild.id, ctx.author.id)

    if room:
        # Show room status, or add/remove remebers
        lower = ctx.args.lower()
        if ctx.msg.mentions and lower and (lower.startswith('-') or lower.startswith('remove')):
            # Remove the mentioned members

            # Extract members to remove
            current_memberids = set(room.memberids)
            to_remove = (
                member for member in ctx.msg.mentions
                if member.id in current_memberids
            )
            to_remove = list(set(to_remove))  # Remove duplicates

            # Check if there are no members to remove
            if not to_remove:
                return await ctx.error_reply(
                    "None of these members have access to your study room!"
                )

            # Finally, remove the members from the room and ack
            await room.remove_members(*to_remove)

            await ctx.embed_reply(
                "The following members have been removed from your room:\n{}".format(
                    ', '.join(member.mention for member in to_remove)
                )
            )
        elif lower == 'delete':
            if await ctx.ask("Are you sure you want to delete your study room? No refunds given!"):
                # TODO: Better deletion log
                await room._execute()
                await ctx.embed_reply("Private study room deleted.")
        elif ctx.msg.mentions:
            # Add the mentioned members

            # Extract members to add
            current_memberids = set(room.memberids)
            to_add = (
                member for member in ctx.msg.mentions
                if member.id not in current_memberids and member.id != ctx.author
            )
            to_add = list(set(to_add))  # Remove duplicates

            # Check if there are no members to add
            if not to_add:
                return await ctx.error_reply(
                    "All of these members already have access to your room!"
                )

            # Check that they didn't provide too many members
            limit = ctx.guild_settings.rent_member_limit.value
            if len(to_add) + len(current_memberids) > limit:
                return await ctx.error_reply(
                    "Too many members! You can invite at most `{}` members to your room.".format(
                        limit
                    )
                )

            # Finally, add the members to the room and ack
            await room.add_members(*to_add)

            await ctx.embed_reply(
                "The following members have been given access to your room:\n{}".format(
                    ', '.join(member.mention for member in to_add)
                )
            )
        else:
            # Show room status with hints for adding and removing members
            # Ack command
            embed = discord.Embed(
                colour=discord.Colour.orange()
            ).set_author(
                name="{}'s private room".format(ctx.author.display_name),
                icon_url=ctx.author.avatar_url
            ).add_field(
                name="Channel",
                value=room.channel.mention
            ).add_field(
                name="Expires",
                value="<t:{}:R>".format(room.timestamp)
            ).add_field(
                name="Members",
                value=', '.join('<@{}>'.format(memberid) for memberid in room.memberids) or "None",
                inline=False
            ).set_footer(
                text=(
                    "Use '{prefix}rent add @mention' and '{prefix}rent remove @mention'\n"
                    "to add and remove members.".format(prefix=ctx.best_prefix)
                ),
                icon_url="https://projects.iamcal.com/emoji-data/img-apple-64/1f4a1.png"
            )
            await ctx.reply(embed=embed)
    else:
        if ctx.args:
            # Rent a new room

            to_add = (
                member for member in ctx.msg.mentions if member != ctx.author
            )
            to_add = list(set(to_add))

            # Check that they provided at least one member
            if not to_add:
                return await ctx.error_reply(
                    "Please mention at least one user to add to your new room."
                )

            # Check that they didn't provide too many members
            limit = ctx.guild_settings.rent_member_limit.value
            if len(ctx.msg.mentions) > limit:
                return await ctx.error_reply(
                    "Too many members! You can invite at most `{}` members to your room.".format(
                        limit
                    )
                )

            # Check that they have enough money for this
            cost = ctx.guild_settings.rent_room_price.value
            if ctx.alion.coins < cost:
                return await ctx.error_reply(
                    "Sorry, a private room costs `{}` coins, but you only have `{}`.".format(
                        cost,
                        ctx.alion.coins
                    )
                )

            # Create the room
            room = await Room.create(ctx.author, to_add)

            # Deduct cost
            ctx.alion.addCoins(-cost)

            # Ack command
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title="Private study room rented!",
            ).add_field(
                name="Channel",
                value=room.channel.mention
            ).add_field(
                name="Expires",
                value="<t:{}:R>".format(room.timestamp)
            ).add_field(
                name="Members",
                value=', '.join(member.mention for member in to_add),
                inline=False
            ).set_footer(
                text="See your room status at any time with {prefix}rent".format(prefix=ctx.best_prefix),
                icon_url="https://projects.iamcal.com/emoji-data/img-apple-64/1f4a1.png"
            )
            await ctx.reply(embed=embed)
        else:
            # Suggest they get a room
            await ctx.embed_reply(
                "Rent a private study room for 24 hours with up to `{}` "
                "friends by mentioning them with this command! (Rooms cost `{}` LionCoins.)\n"
                "`{}rent @user1 @user2 ...`".format(
                    ctx.guild_settings.rent_member_limit.value,
                    ctx.guild_settings.rent_room_price.value,
                    ctx.best_prefix,
                )
            )
