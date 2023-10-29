from data import Registry, Table


class MemberAdminData(Registry):
    autoroles = Table('autoroles')
    bot_autoroles = Table('bot_autoroles')
    past_roles = Table('past_member_roles')
