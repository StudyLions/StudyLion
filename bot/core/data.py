from psycopg2.extras import execute_values

from cachetools import TTLCache
from data import RowTable, Table


meta = RowTable(
    'AppData',
    ('appid', 'last_study_badge_scan'),
    'appid',
    attach_as='meta',
)

# TODO: Consider converting to RowTable for per-shard config caching
app_config = Table('AppConfig')


user_config = RowTable(
    'user_config',
    ('userid', 'timezone', 'topgg_vote_reminder', 'avatar_hash', 'gems'),
    'userid',
    cache=TTLCache(5000, ttl=60*5)
)


guild_config = RowTable(
    'guild_config',
    ('guildid', 'admin_role', 'mod_role', 'event_log_channel', 'mod_log_channel', 'alert_channel',
     'studyban_role', 'max_study_bans',
     'min_workout_length', 'workout_reward',
     'max_tasks', 'task_reward', 'task_reward_limit',
     'study_hourly_reward', 'study_hourly_live_bonus', 'daily_study_cap',
     'renting_price', 'renting_category', 'renting_cap', 'renting_role', 'renting_sync_perms',
     'accountability_category', 'accountability_lobby', 'accountability_bonus',
     'accountability_reward', 'accountability_price',
     'video_studyban', 'video_grace_period',
     'greeting_channel', 'greeting_message', 'returning_message',
     'starting_funds', 'persist_roles',
     'pomodoro_channel',
     'name'),
    'guildid',
    cache=TTLCache(2500, ttl=60*5)
)

unranked_roles = Table('unranked_roles')

donator_roles = Table('donator_roles')


lions = RowTable(
    'members',
    ('guildid', 'userid',
     'tracked_time', 'coins',
     'workout_count', 'last_workout_start',
     'revision_mute_count',
     'last_study_badgeid',
     'video_warned',
     'display_name',
     '_timestamp'
     ),
    ('guildid', 'userid'),
    cache=TTLCache(5000, ttl=60*5),
    attach_as='lions'
)


@lions.save_query
def add_pending(pending):
    """
    pending:
        List of tuples of the form `(guildid, userid, pending_coins)`.
    """
    with lions.conn:
        cursor = lions.conn.cursor()
        data = execute_values(
            cursor,
            """
            UPDATE members
            SET
            coins = LEAST(coins::bigint + t.coin_diff::bigint, 2147483647)
            FROM
                (VALUES %s)
            AS
                t (guildid, userid, coin_diff)
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


lion_ranks = Table('member_ranks', attach_as='lion_ranks')


@lions.save_query
def get_member_rank(guildid, userid, untracked):
    """
    Get the time and coin ranking for the given member, ignoring the provided untracked members.
    """
    with lions.conn as conn:
        with conn.cursor() as curs:
            curs.execute(
                """
                SELECT
                  time_rank, coin_rank
                FROM (
                  SELECT
                    userid,
                    row_number() OVER (ORDER BY total_tracked_time DESC, userid ASC) AS time_rank,
                    row_number() OVER (ORDER BY total_coins DESC, userid ASC) AS coin_rank
                  FROM members_totals
                  WHERE
                    guildid=%s AND userid NOT IN %s
                ) AS guild_ranks WHERE userid=%s
                """,
                (guildid, tuple(untracked), userid)
            )
            return curs.fetchone() or (None, None)


global_guild_blacklist = Table('global_guild_blacklist')
global_user_blacklist = Table('global_user_blacklist')
ignored_members = Table('ignored_members')
