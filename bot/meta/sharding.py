from .args import args
from .config import conf


shard_number = args.shard or 0

shard_count = conf.bot.getint('shard_count', 1)

sharded = (shard_count > 0)
