from data import RowTable, Table

tasklist = RowTable(
    'tasklist',
    ('taskid', 'userid', 'content', 'rewarded', 'created_at', 'completed_at', 'deleted_at', 'last_updated_at'),
    'taskid'
)


tasklist_channels = Table('tasklist_channels')

tasklist_rewards = Table('tasklist_reward_history')


@tasklist_rewards.save_query
def count_recent_for(userid, interval='24h'):
    with tasklist_rewards.conn:
        with tasklist_rewards.conn.cursor() as curs:
            curs.execute(
                "SELECT SUM(reward_count) FROM tasklist_reward_history "
                "WHERE "
                "userid = {}"
                "AND reward_time > timezone('utc', NOW()) - INTERVAL '{}'".format(userid, interval)
            )
            return curs.fetchone()[0] or 0
