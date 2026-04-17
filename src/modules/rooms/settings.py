from settings import ModelData, ListData
from settings.groups import SettingGroup
from settings.setting_types import ChannelSetting, IntegerSetting, BoolSetting, RoleSetting, RoleListSetting

from meta import conf
from core.data import CoreData
from babel.translator import ctx_translator
from wards import low_management_iward, high_management_iward

from .data import RoomData
from . import babel

_p = babel._p


class RoomSettings(SettingGroup):
    class Category(ModelData, ChannelSetting):
        setting_id = 'rooms_category'
        _event = 'guildset_rooms_category'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p(
            'guildset:room_category', "rooms_category"
        )
        _desc = _p(
            'guildset:rooms_category|desc',
            "Category in which to create private voice channels."
        )
        _long_desc = _p(
            'guildset:room_category|long_desc',
            "When a member uses {cmds[room rent]} to rent a new private room, "
            "a private voice channel will be created under this category, "
            "manageable by the member. "
            "I must have permission to create new channels in this category, "
            "as well as to manage permissions."
        )
        _accepts = _p(
            'guildset:room_category|accepts',
            "Private room category name or id."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_category.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is None:
                # Shut down renting system
                resp = t(_p(
                    'guildset:rooms_category|set_response:unset',
                    "The private room category has been unset. Existing private rooms will not be affected. "
                    "Delete the channels manually to remove the private rooms."
                ))
            else:
                resp = t(_p(
                    'guildset:rooms_category|set_response:set',
                    "Private room category has been set to {channel}. Existing private rooms will be moved."
                )).format(channel=self.value.mention)
            return resp

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:room_category|set_using',
                "{cmd} or category selector below."
            )).format(cmd=cmdstr)

    class Rent(ModelData, IntegerSetting):
        setting_id = 'rooms_price'
        _event = 'guildset_rooms_price'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p(
            'guildset:rooms_price', "room_rent"
        )
        _desc = _p(
            'guildset:rooms_rent|desc',
            "Daily rent price for a private room."
        )
        _long_desc = _p(
            'guildset:rooms_rent|long_desc',
            "Members will be charged this many LionCoins for each day they rent a private room."
        )
        _accepts = _p(
            'guildset:rooms_rent|accepts',
            "Number of LionCoins charged per day for a private room."
        )
        _default = 1000

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_price.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:rooms_price|set_response',
                "Private rooms will now cost {coin}**{amount}** per 24 hours."
            )).format(
                coin=conf.emojis.coin,
                amount=self.value
            )
            return resp

    class MemberLimit(ModelData, IntegerSetting):
        setting_id = 'rooms_slots'
        _event = 'guildset_rooms_slots'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p('guildset:rooms_slots', "room_member_cap")
        _desc = _p(
            'guildset:rooms_slots|desc',
            "Maximum number of members in each private room."
        )
        _long_desc = _p(
            'guildset:rooms_slots|long_desc',
            "Private room owners may invite other members to their private room via the UI, "
            "or through the {cmds[room invite]} command. "
            "This setting limits the maximum number of members a private room may hold."
        )
        _accepts = _p(
            'guildset:rooms_slots|accepts',
            "Maximum number of members allowed per private room."
        )
        _default = 25

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_cap.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:rooms_slots|set_response',
                "Private rooms are now capped to **{amount}** members."
            )).format(amount=self.value)
            return resp

    class Visible(ModelData, BoolSetting):
        setting_id = 'rooms_visible'
        _event = 'guildset_rooms_visible'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:rooms_visible', "room_visibility")
        _desc = _p(
            'guildset:rooms_visible|desc',
            "Whether private rented rooms are visible to non-members."
        )
        _long_desc = _p(
            'guildset:rooms_visible|long_desc',
            "If enabled, new private rooms will be created with the `VIEW_CHANNEL` permission "
            "enabled for the `@everyone` role."
        )
        _default = False
        _accepts = _p('guildset:rooms_visible|accepts', "Visible/Invisible")
        _outputs = {
            True: _p('guildset:rooms_visible|output:true', "Visible"),
            False: _p('guildset:rooms_visible|output:false', "Invisible"),
        }
        _outputs[None] = _outputs[_default]

        _truthy = _p(
            'guildset:rooms_visible|parse:truthy_values',
            "visible|enabled|yes|true|on|enable|1"
        )
        _falsey = _p(
            'guildset:rooms_visible|parse:falsey_values',
            'invisible|disabled|no|false|off|disable|0'
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_visible.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                resp = t(_p(
                    'guildset:rooms_visible|set_response:enabled',
                    "Private rooms will now be visible to everyone."
                ))
            else:
                resp = t(_p(
                    'guildset:rooms_visible|set_response:disabled',
                    "Private rooms will now only be visible to their members (and admins)."
                ))
            return resp

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:rooms_visible|set_using',
                "{cmd} or toggle below."
            )).format(cmd=cmdstr)

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add RentingRole setting so admins can assign a mod role that auto-gets perms on private rooms
    class RentingRole(ModelData, RoleSetting):
        setting_id = 'rooms_role'
        _event = 'guildset_rooms_role'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p(
            'guildset:rooms_role', "room_moderator_role"
        )
        _desc = _p(
            'guildset:rooms_role|desc',
            "Role that automatically gets moderation permissions in private rooms."
        )
        _long_desc = _p(
            'guildset:rooms_role|long_desc',
            "When set, this role will automatically receive permissions to "
            "view, connect, and send messages in every private room. "
            "This allows moderators to oversee private channels without needing an invite. "
            "Changing this setting will update all existing active rooms."
        )
        _accepts = _p(
            'guildset:rooms_role|accepts',
            "Room moderator role name or id."
        )
        _default = None

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_role.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'guildset:rooms_role|set_response:set',
                    "{role} will now automatically have moderation access to all private rooms."
                )).format(role=value.mention)
            else:
                resp = t(_p(
                    'guildset:rooms_role|set_response:unset',
                    "No role will have automatic access to private rooms."
                ))
            return resp

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return super()._format_data(parent_id, data, **kwargs)
            else:
                return t(_p(
                    'guildset:rooms_role|formatted:unset',
                    "Not Set."
                ))
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add 6 missing room settings that existed in DB/dashboard but were not wired into bot
    class SyncPerms(ModelData, BoolSetting):
        setting_id = 'rooms_sync_perms'
        _event = 'guildset_rooms_sync_perms'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:rooms_sync_perms', "sync_permissions")
        _desc = _p(
            'guildset:rooms_sync_perms|desc',
            "Whether new rooms inherit the category's permission overwrites."
        )
        _long_desc = _p(
            'guildset:rooms_sync_perms|long_desc',
            "When enabled, new private rooms will copy the permission overwrites from the "
            "configured room category (e.g. role-specific view/connect overrides). "
            "The bot's own overwrites (owner, members, bot) take priority over category ones."
        )
        _default = False
        _accepts = _p('guildset:rooms_sync_perms|accepts', "Enabled/Disabled")
        _outputs = {
            True: _p('guildset:rooms_sync_perms|output:true', "Enabled"),
            False: _p('guildset:rooms_sync_perms|output:false', "Disabled"),
        }
        _outputs[None] = _outputs[_default]
        _truthy = _p('guildset:rooms_sync_perms|parse:truthy', "enabled|yes|true|on|1")
        _falsey = _p('guildset:rooms_sync_perms|parse:falsey', "disabled|no|false|off|0")

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_sync_perms.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_sync_perms|set_response:enabled',
                    "New private rooms will now inherit the category's permission overwrites."
                ))
            else:
                return t(_p(
                    'guildset:rooms_sync_perms|set_response:disabled',
                    "New private rooms will no longer inherit category permission overwrites."
                ))

    class MaxPerUser(ModelData, IntegerSetting):
        setting_id = 'rooms_max_per_user'
        _event = 'guildset_rooms_max_per_user'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p('guildset:rooms_max_per_user', "max_rooms_per_user")
        _desc = _p(
            'guildset:rooms_max_per_user|desc',
            "Maximum number of rooms a single user can own at once."
        )
        _long_desc = _p(
            'guildset:rooms_max_per_user|long_desc',
            "Limits how many private rooms a single member can own simultaneously. "
            "Set to 1 to allow only one room per user (default behavior)."
        )
        _accepts = _p('guildset:rooms_max_per_user|accepts', "Maximum rooms per user (integer).")
        _default = 1

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_max_per_user.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            return t(_p(
                'guildset:rooms_max_per_user|set_response',
                "Members can now own up to **{amount}** private room(s) at a time."
            )).format(amount=self.value)

    class NameLimit(ModelData, IntegerSetting):
        setting_id = 'rooms_name_limit'
        _event = 'guildset_rooms_name_limit'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p('guildset:rooms_name_limit', "room_name_limit")
        _desc = _p(
            'guildset:rooms_name_limit|desc',
            "Maximum character length for private room names."
        )
        _long_desc = _p(
            'guildset:rooms_name_limit|long_desc',
            "Limits the length of the name a member can give their private room. "
            "Discord's own limit is 100 characters."
        )
        _accepts = _p('guildset:rooms_name_limit|accepts', "Max name length (1-100).")
        _default = 100

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_name_limit.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            return t(_p(
                'guildset:rooms_name_limit|set_response',
                "Private room names are now limited to **{amount}** characters."
            )).format(amount=self.value)

    class MinDeposit(ModelData, IntegerSetting):
        setting_id = 'rooms_min_deposit'
        _event = 'guildset_rooms_min_deposit'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p('guildset:rooms_min_deposit', "min_deposit")
        _desc = _p(
            'guildset:rooms_min_deposit|desc',
            "Minimum number of LionCoins per deposit into a room bank."
        )
        _long_desc = _p(
            'guildset:rooms_min_deposit|long_desc',
            "Sets the minimum amount of LionCoins that can be deposited into a "
            "private room bank in a single transaction."
        )
        _accepts = _p('guildset:rooms_min_deposit|accepts', "Minimum deposit amount (integer).")
        _default = 0

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_min_deposit.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_min_deposit|set_response:set',
                    "Minimum room deposit is now {coin}**{amount}**."
                )).format(coin=conf.emojis.coin, amount=self.value)
            else:
                return t(_p(
                    'guildset:rooms_min_deposit|set_response:unset',
                    "There is no longer a minimum room deposit requirement."
                ))

    class AutoExtend(ModelData, BoolSetting):
        setting_id = 'rooms_auto_extend'
        _event = 'guildset_rooms_auto_extend'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:rooms_auto_extend', "auto_extend")
        _desc = _p(
            'guildset:rooms_auto_extend|desc',
            "Automatically charge the owner's wallet when the room bank is empty."
        )
        _long_desc = _p(
            'guildset:rooms_auto_extend|long_desc',
            "When enabled, if a room's bank runs out of coins at tick time, "
            "the daily rent will be deducted from the owner's personal LionCoin balance "
            "instead of destroying the room. If the owner also lacks funds, the room expires."
        )
        _default = False
        _accepts = _p('guildset:rooms_auto_extend|accepts', "Enabled/Disabled")
        _outputs = {
            True: _p('guildset:rooms_auto_extend|output:true', "Enabled"),
            False: _p('guildset:rooms_auto_extend|output:false', "Disabled"),
        }
        _outputs[None] = _outputs[_default]
        _truthy = _p('guildset:rooms_auto_extend|parse:truthy', "enabled|yes|true|on|1")
        _falsey = _p('guildset:rooms_auto_extend|parse:falsey', "disabled|no|false|off|0")

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_auto_extend.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_auto_extend|set_response:enabled',
                    "Rooms will now auto-extend by charging the owner's wallet when the room bank is empty."
                ))
            else:
                return t(_p(
                    'guildset:rooms_auto_extend|set_response:disabled',
                    "Rooms will no longer auto-extend. They will expire when the bank runs out."
                ))

    class Cooldown(ModelData, IntegerSetting):
        setting_id = 'rooms_cooldown'
        _event = 'guildset_rooms_cooldown'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p('guildset:rooms_cooldown', "creation_cooldown")
        _desc = _p(
            'guildset:rooms_cooldown|desc',
            "Minutes a user must wait after a room expires before renting again."
        )
        _long_desc = _p(
            'guildset:rooms_cooldown|long_desc',
            "After a private room is deleted or expires, the owner must wait this many minutes "
            "before they can rent a new one. Set to 0 for no cooldown."
        )
        _accepts = _p('guildset:rooms_cooldown|accepts', "Cooldown in minutes (integer).")
        _default = 0

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_cooldown.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_cooldown|set_response:set',
                    "Users must now wait **{amount}** minute(s) after a room expires before renting again."
                )).format(amount=self.value)
            else:
                return t(_p(
                    'guildset:rooms_cooldown|set_response:unset',
                    "There is no longer a cooldown between room rentals."
                ))
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Role gate settings -- admins can require specific roles to use /room rent
    class RentRequiredRoles(ListData, RoleListSetting):
        """
        Roles the user must have ALL of to rent a room (AND logic).
        """
        setting_id = 'room_rent_required_roles'
        _event = 'guildset_room_rent_required_roles'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:room_rent_required_roles', "rent_required_roles")
        _desc = _p(
            'guildset:room_rent_required_roles|desc',
            "Roles a member must have (ALL of them) to rent a room."
        )
        _long_desc = _p(
            'guildset:room_rent_required_roles|long_desc',
            "When set, a member must have **every** role in this list to use `/room rent` "
            "or purchase a room from the shop. "
            "If combined with the any-of roles setting, both conditions must be satisfied."
        )
        _accepts = _p(
            'guildset:room_rent_required_roles|accepts',
            "Comma separated list of role names or ids."
        )
        _default = None

        _table_interface = RoomData.room_rent_required_roles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'

        _cache = {}

        @property
        def set_str(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:room_rent_required_roles|set_using',
                "Role selector below."
            ))

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is not None:
                resp = t(_p(
                    'guildset:room_rent_required_roles|set_response|set',
                    "Members must now have **all** of the following roles to rent a room: {roles}"
                )).format(roles=self.formatted)
            else:
                resp = t(_p(
                    'guildset:room_rent_required_roles|set_response|unset',
                    "The required roles list for room renting has been cleared. "
                    "Anyone can rent (subject to other settings)."
                ))
            return resp

    class RentAnyOfRoles(ListData, RoleListSetting):
        """
        Roles the user must have at least ONE of to rent a room (OR logic).
        """
        setting_id = 'room_rent_anyof_roles'
        _event = 'guildset_room_rent_anyof_roles'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:room_rent_anyof_roles', "rent_anyof_roles")
        _desc = _p(
            'guildset:room_rent_anyof_roles|desc',
            "Roles a member needs at least ONE of to rent a room."
        )
        _long_desc = _p(
            'guildset:room_rent_anyof_roles|long_desc',
            "When set, a member must have **at least one** role from this list to use `/room rent` "
            "or purchase a room from the shop. "
            "If combined with the required roles setting, both conditions must be satisfied."
        )
        _accepts = _p(
            'guildset:room_rent_anyof_roles|accepts',
            "Comma separated list of role names or ids."
        )
        _default = None

        _table_interface = RoomData.room_rent_anyof_roles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'

        _cache = {}

        @property
        def set_str(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:room_rent_anyof_roles|set_using',
                "Role selector below."
            ))

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is not None:
                resp = t(_p(
                    'guildset:room_rent_anyof_roles|set_response|set',
                    "Members must now have **at least one** of the following roles to rent a room: {roles}"
                )).format(roles=self.formatted)
            else:
                resp = t(_p(
                    'guildset:room_rent_anyof_roles|set_response|unset',
                    "The any-of roles list for room renting has been cleared. "
                    "Anyone can rent (subject to other settings)."
                ))
            return resp
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-06) ---
    # Purpose: Admin toggle + days config for auto-deleting inactive private rooms
    class InactivityEnabled(ModelData, BoolSetting):
        setting_id = 'rooms_inactivity_enabled'
        _event = 'guildset_rooms_inactivity_enabled'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:rooms_inactivity_enabled', "inactivity_auto_delete")
        _desc = _p(
            'guildset:rooms_inactivity_enabled|desc',
            "Automatically delete private rooms after a period of inactivity."
        )
        _long_desc = _p(
            'guildset:rooms_inactivity_enabled|long_desc',
            "When enabled, private rooms that have had no voice joins and no messages "
            "for the configured number of days will be automatically deleted. "
            "Any remaining coin balance is refunded to the room owner. "
            "Frozen rooms are exempt from inactivity deletion."
        )
        _default = False
        _accepts = _p('guildset:rooms_inactivity_enabled|accepts', "Enabled/Disabled")
        _outputs = {
            True: _p('guildset:rooms_inactivity_enabled|output:true', "Enabled"),
            False: _p('guildset:rooms_inactivity_enabled|output:false', "Disabled"),
        }
        _outputs[None] = _outputs[_default]
        _truthy = _p('guildset:rooms_inactivity_enabled|parse:truthy', "enabled|yes|true|on|1")
        _falsey = _p('guildset:rooms_inactivity_enabled|parse:falsey', "disabled|no|false|off|0")

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_inactivity_enabled.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_inactivity_enabled|set_response:enabled',
                    "Inactive private rooms will now be automatically deleted."
                ))
            else:
                return t(_p(
                    'guildset:rooms_inactivity_enabled|set_response:disabled',
                    "Private rooms will no longer be automatically deleted for inactivity."
                ))

    class InactivityDays(ModelData, IntegerSetting):
        setting_id = 'rooms_inactivity_days'
        _event = 'guildset_rooms_inactivity_days'
        _set_cmd = 'admin config rooms'
        _write_ward = high_management_iward

        _display_name = _p('guildset:rooms_inactivity_days', "inactivity_period")
        _desc = _p(
            'guildset:rooms_inactivity_days|desc',
            "Days of inactivity before a private room is auto-deleted."
        )
        _long_desc = _p(
            'guildset:rooms_inactivity_days|long_desc',
            "If inactivity auto-delete is enabled, rooms with no voice joins and no messages "
            "for this many days will be deleted. The remaining balance is refunded to the owner."
        )
        _accepts = _p('guildset:rooms_inactivity_days|accepts', "Number of days (integer, minimum 1).")
        _default = None

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_inactivity_days.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_inactivity_days|set_response:set',
                    "Private rooms will be auto-deleted after **{days}** day(s) of inactivity."
                )).format(days=self.value)
            else:
                return t(_p(
                    'guildset:rooms_inactivity_days|set_response:unset',
                    "No inactivity period has been set. Configure this to enable inactivity auto-delete."
                ))
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-04) ---
    # Purpose: Toggle join/leave notification embeds in private room channels
    class Notifications(ModelData, BoolSetting):
        setting_id = 'rooms_notifications'
        _event = 'guildset_rooms_notifications'
        _set_cmd = 'admin config rooms'
        _write_ward = low_management_iward

        _display_name = _p('guildset:rooms_notifications', "room_notifications")
        _desc = _p(
            'guildset:rooms_notifications|desc',
            "Whether join/leave notification messages are posted in private rooms."
        )
        _long_desc = _p(
            'guildset:rooms_notifications|long_desc',
            "When enabled, the bot posts an embed in a private room channel whenever "
            "a member joins or leaves. Disable this to keep the room channel clean."
        )
        _default = True
        _accepts = _p('guildset:rooms_notifications|accepts', "Enabled/Disabled")
        _outputs = {
            True: _p('guildset:rooms_notifications|output:true', "Enabled"),
            False: _p('guildset:rooms_notifications|output:false', "Disabled"),
        }
        _outputs[None] = _outputs[_default]
        _truthy = _p('guildset:rooms_notifications|parse:truthy', "enabled|yes|true|on|1")
        _falsey = _p('guildset:rooms_notifications|parse:falsey', "disabled|no|false|off|0")

        _model = CoreData.Guild
        _column = CoreData.Guild.renting_notifications.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            if self.value:
                return t(_p(
                    'guildset:rooms_notifications|set_response:enabled',
                    "Join/leave notifications will now be posted in private rooms."
                ))
            else:
                return t(_p(
                    'guildset:rooms_notifications|set_response:disabled',
                    "Join/leave notifications will no longer be posted in private rooms."
                ))
    # --- END AI-MODIFIED ---

    model_settings = (
        Category,
        Rent,
        MemberLimit,
        Visible,
        RentingRole,
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Register the 6 newly-wired room settings
        SyncPerms,
        MaxPerUser,
        NameLimit,
        MinDeposit,
        AutoExtend,
        Cooldown,
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-04) ---
        # Purpose: Room join/leave notification toggle
        Notifications,
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-06) ---
        # Purpose: Inactivity auto-delete settings
        InactivityEnabled,
        InactivityDays,
        # --- END AI-MODIFIED ---
    )

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Separate tuple for ListData settings (registered via register_setting, not register_model_setting)
    list_settings = (
        RentRequiredRoles,
        RentAnyOfRoles,
    )
    # --- END AI-MODIFIED ---
