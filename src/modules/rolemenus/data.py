from enum import Enum

from data import Registry, RowModel, RegisterEnum, Column, NULL
from data.columns import Integer, Timestamp, String, Bool


class MenuType(Enum):
    REACTION = 'REACTION',
    BUTTON = 'BUTTON',
    DROPDOWN = 'DROPDOWN',


class RoleMenuData(Registry):
    MenuType = RegisterEnum(MenuType, name='RoleMenuType')

    class RoleMenu(RowModel):
        _tablename_ = 'role_menus'
        _cache_ = {}

        menuid = Integer(primary=True)
        guildid = Integer()

        channelid = Integer()
        messageid = Integer()

        name = String()
        enabled = Bool()

        required_roleid = Integer()
        sticky = Bool()
        refunds = Bool()
        obtainable = Integer()

        menutype: Column[MenuType] = Column()
        templateid = Integer()
        rawmessage = String()

        default_price = Integer()
        event_log = Bool()

    class RoleMenuRole(RowModel):
        _tablename_ = 'role_menu_roles'
        _cache_ = {}

        menuroleid = Integer(primary=True)

        menuid = Integer()
        roleid = Integer()

        label = String()
        emoji = String()
        description = String()

        price = Integer()
        duration = Integer()

        rawreply = String()

    class RoleMenuHistory(RowModel):
        _tablename_ = 'role_menu_history'
        _cache_ = None

        equipid = Integer(primary=True)

        menuid = Integer()
        roleid = Integer()
        userid = Integer()

        obtained_at = Timestamp()
        transactionid = Integer()
        expires_at = Timestamp()
        removed_at = Timestamp()

        @classmethod
        def fetch_expiring_where(cls, *args, **kwargs):
            """
            Fetch expiring equip rows.

            This returns an awaitable and chainable Select Query.
            """
            return cls.fetch_where(
                (cls.expires_at != NULL),
                (cls.removed_at == NULL),
                *args, **kwargs
            )
