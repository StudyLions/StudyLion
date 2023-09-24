from typing import NamedTuple

from meta.context import ctx_bot


class ShardSnapshot(NamedTuple):
    guild_count: int
    voice_count: int
    member_count: int
    user_count: int


async def shard_snapshot():
    """
    Take a snapshot of the current shard.
    """
    bot = ctx_bot.get()
    if bot is None or not bot.is_ready():
        # We cannot take a snapshot without Bot
        # Just quietly fail
        return None
    snap = ShardSnapshot(
        guild_count=len(bot.guilds),
        voice_count=sum(len(channel.members) for guild in bot.guilds for channel in guild.voice_channels),
        member_count=sum(guild.member_count for guild in bot.guilds),
        user_count=len(set(m.id for guild in bot.guilds for m in guild.members))
    )
    return snap
