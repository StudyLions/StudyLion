from psycopg2.extras import execute_values

from cachetools import TTLCache
from data import RowTable, Table


meta = RowTable(
    'AppData',
    ('appid', 'last_study_badge_scan'),
    'appid',
    attach_as='meta',
)


user_config = RowTable(
    'user_config',
    ('userid', 'timezone'),
    'userid',
    cache=TTLCache(5000, ttl=60*5)
)


guild_config = RowTable(
    'guild_config',
    ('guildid', 'admin_role', 'mod_role', 'event_log_channel', 'alert_channel',
     'min_workout_length', 'workout_reward',
     'max_tasks', 'task_reward', 'task_reward_limit',
     'study_hourly_reward', 'study_hourly_live_bonus',
     'study_ban_role', 'max_study_bans'),
    'guildid',
    cache=TTLCache(1000, ttl=60*5)
)

unranked_roles = Table('unranked_roles')

donator_roles = Table('donator_roles')


lions = RowTable(
    'members',
    ('guildid', 'userid',
     'tracked_time', 'coins',
     'workout_count', 'last_workout_start',
     'last_study_badgeid',
     'video_warned',
     '_timestamp'
     ),
    ('guildid', 'userid'),
    cache=TTLCache(5000, ttl=60*5),
    attach_as='lions'
)

lion_ranks = Table('member_ranks', attach_as='lion_ranks')


@lions.save_query
def add_pending(pending):
    """
    pending:
        List of tuples of the form `(userid, pending_coins, pending_time)`.
    """
    with lions.conn:
        cursor = lions.conn.cursor()
        data = execute_values(
            cursor,
            """
            UPDATE members
            SET
                coins = coins + t.coin_diff,
                tracked_time = tracked_time + t.time_diff
            FROM
                (VALUES %s)
            AS
                t (guildid, userid, coin_diff, time_diff)
            WHERE
                members.guildid = t.guildid
                AND
                members.userid = t.userid
            RETURNING *
            """,
            pending,
            fetch=True
        )
        return lions._make_rows(*data)


global_guild_blacklist = Table('global_guild_blacklist')
global_user_blacklist = Table('global_user_blacklist')
ignored_members = Table('ignored_members')
