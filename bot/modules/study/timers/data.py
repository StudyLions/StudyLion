from data import RowTable


timers = RowTable(
    'timers',
    ('channelid', 'guildid',
     'focus_length', 'break_length',
     'inactivity_threshold',
     'last_started',
     'text_channelid',
     'channel_name', 'pretty_name'),
    'channelid',
    cache={}
)
