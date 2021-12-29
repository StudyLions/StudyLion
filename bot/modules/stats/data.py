from data import Table


profile_tags = Table('member_profile_tags', attach_as='profile_tags')


@profile_tags.save_query
def get_tags_for(guildid, userid):
    rows = profile_tags.select_where(
        guildid=guildid, userid=userid,
        _extra="ORDER BY tagid ASC"
    )
    return [row['tag'] for row in rows]
