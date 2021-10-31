from data import Table, RowTable, tables

untracked_channels = Table('untracked_channels')

session_history = Table('session_history')
current_sessions = RowTable(
    'current_sessions',
    ('guildid', 'userid', 'channelid', 'channel_type',
     'start_time',
     'live_duration', 'live_start',
     'stream_duration', 'stream_start',
     'video_duration', 'video_start',
     'hourly_coins', 'hourly_live_coins'),
    ('guildid', 'userid'),
    cache={}  # Keep all current sessions in cache
)


@current_sessions.save_query
def close_study_session(guildid, userid):
    """
    Close a member's current session if it exists and update the member cache.
    """
    # Execute the `close_study_session` database function
    with current_sessions.conn as conn:
        cursor = conn.cursor()
        cursor.callproc('close_study_session', (guildid, userid))
        rows = cursor.fetchall()
    # The row has been deleted, remove the from current sessions cache
    current_sessions.row_cache.pop((guildid, userid), None)
    # Use the function output to update the member cache
    tables.lions._make_rows(*rows)
