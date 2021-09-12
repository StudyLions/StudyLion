from cmdClient import check
from cmdClient.checks import in_guild

from data import tables


def is_guild_admin(member):
    # First check guild admin permissions
    admin = member.guild_permissions.administrator

    # Then check the admin role, if it is set
    if not admin:
        admin_role_id = tables.guild_config.fetch_or_create(member.guild.id).admin_role
        admin = admin_role_id and (admin_role_id in (r.id for r in member.roles))
    return admin


@check(
    name="ADMIN",
    msg=("You need to be a server admin to do this!"),
    requires=[in_guild]
)
async def guild_admin(ctx, *args, **kwargs):
    return is_guild_admin(ctx.author)
