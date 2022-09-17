from data import Table, RowTable


reaction_role_messages = RowTable(
    'reaction_role_messages',
    ('messageid', 'guildid', 'channelid',
     'enabled',
     'required_role', 'allow_deselction',
     'max_obtainable', 'allow_refunds',
     'event_log'),
    'messageid'
)


reaction_role_reactions = RowTable(
    'reaction_role_reactions',
    ('reactionid', 'messageid', 'roleid', 'emoji_name', 'emoji_id', 'emoji_animated', 'price', 'timeout'),
    'reactionid'
)


reaction_role_expiring = Table('reaction_role_expiring')
