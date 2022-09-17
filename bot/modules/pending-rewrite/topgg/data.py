from data.interfaces import RowTable, Table

topggvotes = RowTable(
    'topgg',
    ('voteid', 'userid', 'boostedTimestamp'),
    'voteid'
)

guild_whitelist = Table('topgg_guild_whitelist')
