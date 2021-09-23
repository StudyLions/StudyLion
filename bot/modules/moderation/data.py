from data import Table, RowTable


video_channels = Table('video_channels')
studyban_durations = Table('studyban_durations')

ticket_info = RowTable(
    'ticket_info',
    ('ticketid', 'guild_ticketid',
     'guildid', 'targetid', 'ticket_type', 'moderator_id', 'auto',
     'log_msg_id', 'created_at',
     'content', 'context', 'duration'
     'expiry',
     'pardoned', 'pardoned_by', 'pardoned_at', 'pardoned_reason'),
    'ticketid',
)

tickets = Table('tickets')
