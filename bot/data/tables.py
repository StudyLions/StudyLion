from .data import RowTable, Table

raw_users = Table('Users')
users = RowTable(
    'users',
    ('userid', 'tracked_time', 'coins'),
    'userid',
)
