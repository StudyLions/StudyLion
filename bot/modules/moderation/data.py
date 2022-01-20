from data import Table, RowTable


studyban_durations = Table('studyban_durations')

ticket_info = RowTable(
    'ticket_info',
    ('ticketid', 'guild_ticketid',
     'guildid', 'targetid', 'ticket_type', 'ticket_state', 'moderator_id', 'auto',
     'log_msg_id', 'created_at',
     'content', 'context', 'addendum', 'duration',
     'file_name', 'file_data',
     'expiry',
     'pardoned_by', 'pardoned_at', 'pardoned_reason'),
    'ticketid',
    cache_size=20000
)

tickets = Table('tickets')
