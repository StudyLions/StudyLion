from data import Table, RowTable


workout_channels = Table('workout_channels')

workout_sessions = RowTable(
    'workout_sessions',
    ('sessionid', 'guildid', 'userid', 'start_time', 'duration', 'channelid'),
    'sessionid'
)
