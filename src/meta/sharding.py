from .args import args
from .config import conf

from psycopg import sql
from data.conditions import Condition, Joiner


shard_number = args.shard or 0

shard_count = conf.bot.getint('shard_count', 1)

sharded = (shard_count > 0)


def SHARDID(shard_id: int, guild_column: str = 'guildid', shard_count: int = shard_count) -> Condition:
    """
    Condition constructor for filtering by shard id.

    Example Usage
    -------------
    Query.where(_shard_condition('guildid', 10, 1))
    """
    return Condition(
        sql.SQL("({guildid} >> 22) %% {shard_count}").format(
            guildid=sql.Identifier(guild_column),
            shard_count=sql.Literal(shard_count)
        ),
        Joiner.EQUALS,
        sql.Placeholder(),
        (shard_id,)
    )


# Pre-built Condition for filtering by current shard.
THIS_SHARD = SHARDID(shard_number)
