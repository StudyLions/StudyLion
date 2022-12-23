from cachetools import TTLCache

from data import Table, RowTable


profile_tags = Table('member_profile_tags', attach_as='profile_tags')


@profile_tags.save_query
def get_tags_for(guildid, userid):
    rows = profile_tags.select_where(
        guildid=guildid, userid=userid,
        _extra="ORDER BY tagid ASC"
    )
    return [row['tag'] for row in rows]


weekly_goals = RowTable(
    'member_weekly_goals',
    ('guildid', 'userid', 'weekid', 'study_goal', 'task_goal'),
    ('guildid', 'userid', 'weekid'),
    cache=TTLCache(5000, 60 * 60 * 24),
    attach_as='weekly_goals'
)


# NOTE: Not using a RowTable here since these will almost always be mass-selected
weekly_tasks = Table('member_weekly_goal_tasks')


monthly_goals = RowTable(
    'member_monthly_goals',
    ('guildid', 'userid', 'monthid', 'study_goal', 'task_goal'),
    ('guildid', 'userid', 'monthid'),
    cache=TTLCache(5000, 60 * 60 * 24),
    attach_as='monthly_goals'
)

monthly_tasks = Table('member_monthly_goal_tasks')
