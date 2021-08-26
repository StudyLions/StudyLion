from psycopg2.extras import execute_values

from cachetools import TTLCache
from data import RowTable, Table


users = RowTable(
    'lions',
    ('userid', 'tracked_time', 'coins'),
    'userid',
    cache=TTLCache(5000, ttl=60*5)
)


@users.save_query
def add_coins(userid_coins):
    with users.conn:
        cursor = users.conn.cursor()
        data = execute_values(
            cursor,
            """
            UPDATE lions
            SET coins = coins + t.diff
            FROM (VALUES %s) AS t (userid, diff)
            WHERE lions.userid = t.userid
            RETURNING *
            """,
            userid_coins,
            fetch=True
        )
        return users._make_rows(*data)
