from data import RowTable, Table


rented = RowTable(
    'rented',
    ('channelid', 'guildid', 'ownerid', 'expires_at', 'created_at'),
    'channelid'
)


rented_members = Table('rented_members')
