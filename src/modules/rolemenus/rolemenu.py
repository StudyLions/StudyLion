from meta import LionBot


from .data import RoleMenuData as Data
from .menuoptions import RoleMenuConfig
from .roleoptions import RoleMenuRoleConfig


class RoleMenuRole:
    def __init__(self, bot: LionBot, data: Data.RoleMenuRole):
        self.bot = bot
        self.data = data
        self.config = RoleMenuRoleConfig(data.menuroleid, data)


class RoleMenu:
    def __init__(self, bot: LionBot, data: Data.RoleMenu, roles):
        self.bot = bot
        self.data = data
        self.config = RoleMenuConfig(data.menuid, data)
        self.roles: list[RoleMenuRole] = roles

        self._message = None

    @property
    def message(self):
        return self._message

    async def fetch_message(self):
        ...

    async def reload(self):
        await self.data.refresh()
        roledata = self.bot.get_cog('RoleMenuCog').data.RoleMenuRole
        role_rows = await roledata.fetch_where(menuid=self.data.menuid)
        self.roles = [RoleMenuRole(self.bot, row) for row in role_rows]

    async def make_view(self):
        ...

    async def make_args(self):
        ...
