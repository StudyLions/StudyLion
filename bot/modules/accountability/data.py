from data import Table, RowTable

from cachetools import TTLCache


accountability_rooms = RowTable(
    'accountability_slots',
    ('slotid', 'channelid', 'guildid', 'start_at', 'messageid', 'closed_at'),
    'slotid',
    cache=TTLCache(5000, ttl=60*70),
    attach_as='accountability_rooms'
)


accountability_members = RowTable(
    'accountability_members',
    ('slotid', 'userid', 'paid', 'duration', 'last_joined_at'),
    ('slotid', 'userid'),
    cache=TTLCache(5000, ttl=60*70)
)

accountability_member_info = Table('accountability_member_info')
accountability_open_slots = Table('accountability_open_slots')
