import discord
from cmdClient.Context import Context

from meta import client

from .settings import greeting_message, greeting_channel, returning_message


@client.add_after_event('member_join')
async def send_greetings(client, member):
    guild = member.guild

    returning = bool(client.data.lions.fetch((guild.id, member.id)))

    # Handle greeting message
    channel = greeting_channel.get(guild.id).value
    if channel is not None:
        if channel == greeting_channel.DMCHANNEL:
            channel = member

        ctx = Context(client, guild=guild, author=member)
        if returning:
            args = returning_message.get(guild.id).args(ctx)
        else:
            args = greeting_message.get(guild.id).args(ctx)
        try:
            await channel.send(**args)
        except discord.HTTPException:
            pass
