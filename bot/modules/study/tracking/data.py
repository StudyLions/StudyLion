from data import Table, RowTable, tables
from utils.lib import FieldEnum


untracked_channels = Table('untracked_channels')


class SessionChannelType(FieldEnum):
    """
    The possible session channel types.
    """
    # NOTE: "None" stands for Unknown, and the STANDARD description should be replaced with the channel name
    STANDARD = 'STANDARD', "Standard"
    ACCOUNTABILITY = 'ACCOUNTABILITY', "Accountability Room"
    RENTED = 'RENTED', "Private Room"
    EXTERNAL = 'EXTERNAL', "Unknown"


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


@session_history.save_query
def study_time_since(guildid, userid, timestamp):
    """
    Retrieve the total member study time (in seconds) since the given timestamp.
    Includes the current session, if it exists.
    """
    with session_history.conn as conn:
        cursor = conn.cursor()
        cursor.callproc('study_time_since', (guildid, userid, timestamp))
        rows = cursor.fetchall()
    return (rows[0][0] if rows else None) or 0
