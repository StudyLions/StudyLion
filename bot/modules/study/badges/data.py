from cachetools import cached

from data import Table, RowTable

study_badges = RowTable(
    'study_badges',
    ('badgeid', 'guildid', 'roleid', 'required_time'),
    'badgeid'
)

current_study_badges = Table('current_study_badges')

new_study_badges = Table('new_study_badges')


# Cache of study role ids attached to each guild. Not automatically updated.
guild_role_cache = {}  # guildid -> set(roleids)


@study_badges.save_query
@cached(guild_role_cache)
def for_guild(guildid):
    rows = study_badges.fetch_rows_where(guildid=guildid)
    return set(row.roleid for row in rows)
