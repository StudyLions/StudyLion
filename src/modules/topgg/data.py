from data import Registry, Table, RowModel
from data.columns import Integer, Timestamp


class TopggData(Registry):
    class TopGG(RowModel):
        _tablename_ = 'topgg'

        voteid = Integer(primary=True)
        userid = Integer()
        boostedtimestamp = Timestamp()

    guild_whitelist = Table('topgg_guild_whitelist')
