from data import RowTable, Table

tasklist = RowTable(
    'tasklist',
    ('taskid', 'guildid', 'userid', 'content', 'complete', 'rewarded', 'created_at', 'last_updated_at'),
    'taskid'
)


@tasklist.save_query
def expire_old_tasks():
    with tasklist.conn:
        with tasklist.conn.cursor() as curs:
            curs.execute(
                "DELETE FROM tasklist WHERE "
                "last_updated_at < timezone('utc', NOW()) - INTERVAL '7d' "
                "RETURNING *"
            )
            return curs.fetchall()


tasklist_channels = Table('tasklist_channels')

tasklist_rewards = Table('tasklist_reward_history')


@tasklist_rewards.save_query
def count_recent_for(guildid, userid, interval='24h'):
    with tasklist_rewards.conn:
        with tasklist_rewards.conn.cursor() as curs:
            curs.execute(
                "SELECT SUM(reward_count) FROM tasklist_reward_history "
                "WHERE "
                "guildid = {} AND userid = {}"
                "AND reward_time > timezone('utc', NOW()) - INTERVAL '{}'".format(guildid, userid, interval)
            )
            return curs.fetchone()[0] or 0
