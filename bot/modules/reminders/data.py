from data.interfaces import RowTable


reminders = RowTable(
    'reminders',
    ('reminderid', 'userid', 'remind_at', 'content', 'message_link', 'interval', 'created_at'),
    'reminderid'
)
